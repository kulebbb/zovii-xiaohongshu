#!/usr/bin/env python3
"""行间并发调度：多行小红书图片组并行生成 + 回填。

用法:
    python3 run_rows.py --url <URL> --sheet-id <SID> --rows "2,3,5" \
        --project <PID> --model <M> --ratio 3:4 \
        [--max-workers 10] [--out <dir>] [--size 2K] [--timeout 300] [--retry 1]

并发策略:
    - 行间并发（默认 10 行），行内模式由 judge_mode 按拆图提示词判断
    - 数据预取：main 串行批量读取所有行输入（避免多 worker 并发读表格触发飞书 API 限流）
    - 参考图下载串行化（lark-cli api 每 token 一次调用）
    - lark-cli 调用遇限流(99991400)自动退避重试

每行流程:
    行锚点校验（防错行）→ 生成图片（行内按模式并发）→ 下载回填单元格图片 → 更新状态+耗时列

行锚点校验（防错行，重要）:
    预取阶段对每行用绝对行号直读「图片数量」单元格，与 csv-get 批量映射值比对；
    不一致 = 行号映射疑似错位 → 该行立即判失败并跳过，不生成、不回填、不写状态，
    把「静默错装」变成「响亮报警」。

参考图临时目录（重要）:
    - 参考图统一下载到 <cwd>/tmp/zovii-refs/<任务ID>/refs/<行号>/（--tmp-dir 可覆盖）
    - 任务结束（无论成败）自动删除整个任务临时目录；--keep-tmp 可调试保留
    - 启动时自动清扫 tmp/zovii-refs/ 下超过 3 天的残留目录

输出: JSON {"2": {"status":"completed","mode":"parallel","elapsed":..}, ...}
清理信息走 stderr，不污染 stdout 的 JSON。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEP_WORDS = ["作为参考图", "作为参考", "以封面为", "以图1为", "以首图为",
             "基于图", "在图1基础上", "在图2基础上", "在图3基础上",
             "延续", "承接", "参照", "跟随", "锚点", "保持一致",
             "使用图1", "使用封面", "封面作为", "图1作为", "风格统一"]
INDEP_WORDS = ["每张图独立", "各图独立", "互不相关", "单独设计", "独立构图"]


def judge_mode(decompose_text):
    """根据拆图提示词判断行内模式。返回 'sequential' / 'parallel'"""
    if not decompose_text:
        return "parallel"
    if any(w in decompose_text for w in INDEP_WORDS):
        return "parallel"
    if any(w in decompose_text for w in DEP_WORDS):
        return "sequential"
    return "parallel"  # 默认并发


def run_cli(cmd, cwd=None, retries=4):
    """执行命令；遇飞书限流(99991400)自动退避重试"""
    last_err = ""
    for attempt in range(retries):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        if r.returncode == 0:
            return r.stdout
        err = (r.stderr or r.stdout) or ""
        for esc in ("\x1b[31m", "\x1b[0m", "\x1b[1m", "\x1b[36m"):
            err = err.replace(esc, "")
        last_err = err.strip() or "调用失败"
        if "99991400" in err and attempt < retries - 1:
            time.sleep(3 * (attempt + 1))
            continue
        raise RuntimeError(last_err)
    raise RuntimeError(last_err)


def csv_get(url, sid, rng):
    return json.loads(run_cli(["lark-cli", "sheets", "+csv-get",
                               "--url", url, "--sheet-id", sid,
                               "--range", rng, "--as", "user", "--rows-json"]))


def cells_get(url, sid, rng, include="value,rich_text"):
    return json.loads(run_cli(["lark-cli", "sheets", "+cells-get",
                               "--url", url, "--sheet-id", sid,
                               "--range", rng, "--as", "user",
                               "--include", include]))


def find_header_cols(url, sid):
    d = cells_get(url, sid, "A1:ZZ1", include="value")
    cells = d["data"]["ranges"][0]["cells"][0]
    cols = d["data"]["ranges"][0]["col_indices"]
    return {str(c.get("value")): letter
            for letter, c in zip(cols, cells) if c.get("value") not in (None, "")}


def col_letter(idx):
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def col_index(letter):
    n = 0
    for ch in letter.upper():
        n = n * 26 + (ord(ch) - 65 + 1)
    return n - 1


def rows_matrix(d, ncols):
    """csv-get rows-json → {row_number: [col1..colN]}（按字母序）"""
    result = {}
    for r in d.get("data", {}).get("rows", []):
        vals = r.get("values", {})
        keys = sorted(vals.keys(), key=col_index)
        cells = [vals[k] for k in keys]
        result[r["row_number"]] = cells + [""] * (ncols - len(cells))
    return result


def sweep_stale_tmp(tmp_root, max_age_days=3):
    """清扫 tmp/zovii-refs/ 下超过 max_age_days 的残留任务目录（异常中断遗留）"""
    try:
        now = time.time()
        for name in os.listdir(tmp_root):
            p = os.path.join(tmp_root, name)
            if os.path.isdir(p) and now - os.path.getmtime(p) > max_age_days * 86400:
                shutil.rmtree(p, ignore_errors=True)
    except OSError:
        pass


def cleanup_tmp(tmp_dir, keep):
    """任务结束清理参考图临时目录（成败都删；--keep-tmp 调试保留）"""
    if keep:
        sys.stderr.write(f"[tmp] 已保留参考图临时目录（调试用，可手动删除）: {tmp_dir}\n")
        return
    shutil.rmtree(tmp_dir, ignore_errors=True)
    sys.stderr.write(f"[tmp] 已清理参考图临时目录: {tmp_dir}\n")


def norm_cell(v):
    return "" if v is None else str(v).strip()


def verify_row_anchor(url, sid, row, ncol, batch_val):
    """行锚点校验：以绝对行号直读单元格，与 csv-get 批量映射值比对。

    两条读取路径独立：批量读按 csv-get 的 row_number 映射取值，直读按 A1 地址取值。
    若映射错位（如相对/绝对行号语义不符、隐藏行偏移），两者必然不一致 → 响亮失败。
    返回 (ok, 错误信息)。
    """
    try:
        d = cells_get(url, sid, f"{ncol}{row}", include="value")
        direct = d["data"]["ranges"][0]["cells"][0][0].get("value")
    except Exception as e:
        return False, f"行{row} 锚点校验读取失败: {e}"
    if norm_cell(direct) != norm_cell(batch_val):
        return False, (f"行{row} 行锚点校验失败: 绝对寻址读到的图片数量="
                       f"{norm_cell(direct)!r}，批量读取={norm_cell(batch_val)!r}，"
                       f"行号映射疑似错位，已跳过该行（未做任何写入）")
    return True, ""


def fetch_ref_images(url, sid, ref_cols, ref_names, row, out_dir):
    """下载该行参考图（单元格图片 / URL 文本）到 out_dir。返回 {1: [路径]}"""
    if not ref_cols:
        return {}
    rng = f"{ref_cols[0]}{row}:{ref_cols[-1]}{row}"
    d = cells_get(url, sid, rng)
    ranges = d.get("data", {}).get("ranges", [])
    refs = {}
    if not ranges:
        return refs
    cells = ranges[0]["cells"][0]
    for letter, name, cell in zip(ref_cols, ref_names, cells):
        embeds = [seg for seg in cell.get("rich_text", [])
                  if seg.get("type") == "embed-image"]
        if embeds:
            token = embeds[0].get("image_token")
            fname = f"{row}-{name}-{token[:8]}.png"
            dst = os.path.join(out_dir, fname)
            run_cli(["lark-cli", "api", "GET",
                     f"/open-apis/drive/v1/medias/{token}/download",
                     "--as", "user", "--output", f"./{fname}"], cwd=out_dir)
            refs.setdefault(1, []).append(dst)
            continue
        v = cell.get("value")
        if v and str(v).startswith(("http://", "https://")):
            path = os.path.join(out_dir, f"{row}-{name}.jpg")
            urllib.request.urlretrieve(str(v), path)
            refs.setdefault(1, []).append(path)
    return refs


def process_row(row, inp, url, sid, project, model, ratio, size, timeout,
                retry, out_root, dry_run):
    """单行：生成 → 回填 → 状态+耗时。inp 为 main 预取的数据"""
    t0 = time.time()
    try:
        n, decompose, prompts, ref_map = (inp["n"], inp["decompose"],
                                          inp["prompts"], inp["refs"])
        icol, scol, tcol = inp["icol"], inp["scol"], inp["tcol"]
        mode = judge_mode(decompose)

        # 1. 写 prompts 临时文件并生成
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write("\n".join(prompts))
            pf = f.name
        cmd = [sys.executable, os.path.join(SCRIPT_DIR, "generate_row_images.py"),
               "--project", project, "--model", model, "--ratio", ratio,
               "--prompts", pf, "--mode", mode,
               "--size", size, "--timeout", str(timeout), "--retry", str(retry)]
        refs_arg = ";".join(f"{k}:{','.join(v)}" for k, v in ref_map.items())
        if refs_arg:
            cmd += ["--refs", refs_arg]
        if dry_run:
            return {"status": "dry-run", "mode": mode, "cmd": " ".join(cmd)}
        out = run_cli(cmd)
        images = json.loads(out)
        os.unlink(pf)

        # 2. 下载回填（fillback_images 内部处理相对路径）
        assets = ";".join(
            f"{im['assetId']}:{row}-图{im['n']}.png"
            for im in images if im.get("status") == "completed")
        if assets:
            run_cli([sys.executable, os.path.join(SCRIPT_DIR, "fillback_images.py"),
                     "--url", url, "--sheet-id", sid, "--row", str(row),
                     "--start-col", icol, "--assets", assets,
                     "--out", os.path.join(out_root, "images")])

        # 3. 状态 + 耗时
        failed = [im["n"] for im in images if im.get("status") != "completed"]
        status = "已完成" if not failed else "图片已生成"
        elapsed = int(time.time() - t0)
        run_cli(["lark-cli", "sheets", "+cells-set",
                 "--url", url, "--sheet-id", sid,
                 "--range", f"{scol}{row}:{tcol}{row}", "--as", "user",
                 "--cells", json.dumps([[{"value": status}, {"value": elapsed}]],
                                       ensure_ascii=False)])
        return {"status": status, "mode": mode, "images": images,
                "failed": failed, "elapsed": elapsed}
    except Exception as e:
        return {"status": "failed", "error": str(e),
                "elapsed": int(time.time() - t0)}


def ensure_time_col(url, sid, headers):
    scol = headers.get("状态", "Q")
    tcol = col_letter(col_index(scol) + 1)
    if "耗时(秒)" not in headers:
        run_cli(["lark-cli", "sheets", "+cells-set",
                 "--url", url, "--sheet-id", sid,
                 "--range", f"{tcol}1", "--as", "user",
                 "--cells", json.dumps([[{"value": "耗时(秒)"}]],
                                       ensure_ascii=False)])
    return tcol


def main():
    ap = argparse.ArgumentParser(description="行间并发调度：多行并发生成+回填")
    ap.add_argument("--url", required=True)
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--rows", required=True, help="行号列表，逗号分隔")
    ap.add_argument("--project", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--ratio", required=True)
    ap.add_argument("--max-workers", type=int, default=10)
    ap.add_argument("--out", default=None, help="生成图（交付物）输出目录")
    ap.add_argument("--tmp-dir", default=None,
                    help="参考图临时目录，默认 <cwd>/tmp/zovii-refs/<任务ID>/，任务结束自动删除")
    ap.add_argument("--keep-tmp", action="store_true",
                    help="结束后保留参考图临时目录（调试用，默认删除）")
    ap.add_argument("--size", default="2K")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--retry", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rows = [int(r.strip()) for r in a.rows.split(",") if r.strip()]
    out_root = a.out or os.path.join(os.getcwd(), "xiaohongshu",
                                     __import__("datetime").date.today().isoformat(),
                                     ",".join(map(str, rows)))
    os.makedirs(out_root, exist_ok=True)
    rmin, rmax = min(rows), max(rows)

    # ===== 参考图临时目录：统一放 tmp/，任务结束自动清理 =====
    tmp_root = os.path.abspath(os.path.join(os.getcwd(), "tmp", "zovii-refs"))
    job_id = time.strftime("%Y%m%d-%H%M%S") + f"-p{os.getpid()}"
    tmp_dir = os.path.abspath(a.tmp_dir) if a.tmp_dir else os.path.join(tmp_root, job_id)
    os.makedirs(tmp_dir, exist_ok=True)
    sweep_stale_tmp(tmp_root)

    results = {}
    try:
        # ===== 串行预取（避免并发读表格触发限流），参考图下载进 tmp/ =====
        headers = find_header_cols(a.url, a.sheet_id)
        tcol = ensure_time_col(a.url, a.sheet_id, headers)
        ncol = headers.get("图片数量", "E")
        dcol = headers.get("拆图提示词", "D")
        pcol = headers.get("图1提示词", "I")
        icol = headers.get("图1图片", "M")
        scol = headers.get("状态", "Q")

        # 图片数量 / 拆图提示词（批量读列）
        n_map = rows_matrix(csv_get(a.url, a.sheet_id, f"{ncol}{rmin}:{ncol}{rmax}"), 1)
        d_map = rows_matrix(csv_get(a.url, a.sheet_id, f"{dcol}{rmin}:{dcol}{rmax}"), 1)
        # 提示词矩阵（最多读 12 列，覆盖常见最大图数）
        p_end = col_letter(col_index(pcol) + 11)
        p_map = rows_matrix(csv_get(a.url, a.sheet_id, f"{pcol}{rmin}:{p_end}{rmax}"), 12)

        # 参考图列定位
        ref_cols, ref_names = [], []
        for key, letter in headers.items():
            if key in ("产品图", "封面参考图") or key.startswith("其他参考图"):
                ref_cols.append(letter)
                ref_names.append(key)

        # 预取每个输入行的输入 + 行锚点校验 + 串行下载参考图（到 tmp/）
        inputs = {}
        anchor_errors = {}  # row -> 报错信息；命中行不进入执行池，不产生任何写入
        for row in rows:
            batch_n = (n_map.get(row) or [""])[0]
            ok, msg = verify_row_anchor(a.url, a.sheet_id, row, ncol, batch_n)
            if not ok:
                anchor_errors[row] = msg
                continue
            n = int(batch_n or 0)
            if n < 1:
                inputs[row] = {"n": 0, "decompose": "", "prompts": [],
                               "refs": {}, "icol": icol, "scol": scol, "tcol": tcol}
                continue
            prompts = [(p_map.get(row) or [""] * 12)[i] or "" for i in range(n)]
            row_ref_dir = os.path.join(tmp_dir, "refs", str(row))
            os.makedirs(row_ref_dir, exist_ok=True)
            ref_map = fetch_ref_images(a.url, a.sheet_id, ref_cols, ref_names,
                                       row, row_ref_dir)
            inputs[row] = {"n": n, "decompose": (d_map.get(row) or [""])[0],
                           "prompts": prompts, "refs": ref_map,
                           "icol": icol, "scol": scol, "tcol": tcol}

        # ===== 行间并发执行（仅锚点校验通过的行）=====
        runnable = [r for r in rows if r not in anchor_errors]
        if runnable:
            with ThreadPoolExecutor(max_workers=min(a.max_workers,
                                                    len(runnable))) as ex:
                futs = {ex.submit(process_row, r, inputs[r], a.url, a.sheet_id,
                                  a.project, a.model, a.ratio, a.size, a.timeout,
                                  a.retry, out_root, a.dry_run): r
                        for r in runnable}
                for fut in as_completed(futs):
                    results[str(futs[fut])] = fut.result()
        # 锚点校验失败的行：响亮计入失败清单
        for r, msg in anchor_errors.items():
            results[str(r)] = {"status": "failed", "error": msg}
    finally:
        # 无论成败，参考图临时目录一律清理（--keep-tmp 可保留调试）
        cleanup_tmp(tmp_dir, a.keep_tmp)

    ordered = {str(r): results[str(r)] for r in rows if str(r) in results}
    print(json.dumps(ordered, ensure_ascii=False, indent=2))
    failed_rows = [r for r, v in ordered.items() if v.get("status") == "failed"]
    if failed_rows:
        sys.stderr.write(f"失败行: {failed_rows}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()

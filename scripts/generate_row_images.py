#!/usr/bin/env python3
"""单行图片生成（支持行内并发，按依赖模式）。

模式:
    sequential: 图1(封面)先生成 → 封面 assetId 作锚点 → 图2..N 并发生成
    parallel:   图1..N 全部并发生成（无封面锚点，各图用各自明示的参考图）

用法:
    python3 generate_row_images.py --project <PID> --model <M> --ratio 3:4 \
        --prompts <file> --mode <sequential|parallel> \
        [--cover-ref <本地路径>] \
        [--refs "1:路径A,路径B;2:路径C"] \
        [--size 2K] [--timeout 300] [--retry 1] \
        [--manifest <path>]

参数:
    --prompts   提示词文件，每行一条（第 1 行 = 图1）
    --mode       sequential(默认) / parallel；auto 时由调用方先判断再传入
    --cover-ref 封面参考图（本地路径/assetId；多张用 --refs "1:路径A,路径B"）
    --refs      各图参考图，格式 "图号:路径[,路径...];图号:路径..."（图1的参考图即封面参考图）
    --retry     单张失败重试次数（默认 1）
    --manifest  断点续跑清单（JSONL）：每张完成立即追加 {n,status,assetId,...}；
                启动时读取，已完成图号直接复用 assetId 跳过生成（不重复消耗 credit）

输出: JSON [{"n":1,"status":"completed","assetId":"...","fileUrl":"..."}, ...]
     失败项 status="failed" 并带 error 字段（不中断后续）；有失败退出码 2

参考图风格锁定（重要）:
     凡带参考图的图，提示词前自动注入 STYLE_LOCK 引导句。复盘教训：ws-gpt-image-2
     对 --image-input 默认语义是弱视觉参考，提示词不显式要求「遵循参考图风格」时，
     模型会跑向领域先验模板（实测相似度仅 5%~8%）；显式锚定后 ~93%。
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

STYLE_LOCK = ("严格遵循所提供参考图的视觉风格与关键元素："
              "画风媒介、主色配色、构图、字体、装饰元素均与参考图保持一致。")

_manifest_lock = threading.Lock()


def load_manifest(path):
    """读断点清单 → {n: item}；半行/坏行忽略（异常中断残留不致命）"""
    done = {}
    if not path or not os.path.exists(path):
        return done
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("status") == "completed" and r.get("assetId"):
                    done[r["n"]] = r
    except OSError:
        pass
    return done


def append_manifest(path, item):
    """每张完成立即落盘；写失败只告警（退化为无断点，不影响主流程）。
    追加前若文件末尾不是换行（上次写一半崩溃的残行），先补换行，
    避免本次记录被拼进坏行而丢失。"""
    if not path:
        return
    try:
        with _manifest_lock:
            needs_nl = False
            try:
                if os.path.exists(path) and os.path.getsize(path):
                    with open(path, "rb") as f:
                        f.seek(-1, os.SEEK_END)
                        needs_nl = f.read(1) != b"\n"
            except OSError:
                pass
            with open(path, "a", encoding="utf-8") as f:
                if needs_nl:
                    f.write("\n")
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except OSError as e:
        sys.stderr.write(f"[manifest] 写入失败（忽略，退化为无断点）: {e}\n")


def zovii(args):
    r = subprocess.run(["zovii"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        err = r.stderr or r.stdout
        for esc in ("\x1b[31m", "\x1b[0m", "\x1b[1m", "\x1b[36m"):
            err = err.replace(esc, "")
        raise RuntimeError(err.strip() or "zovii 调用失败")
    return json.loads(r.stdout)


def parse_refs(spec):
    """'1:a,b;3:c' -> {1: ["a","b"], 3: ["c"]}"""
    refs = {}
    if not spec:
        return refs
    for part in spec.split(";"):
        if not part.strip():
            continue
        n, _, paths = part.partition(":")
        refs[int(n.strip())] = [p.strip() for p in paths.split(",") if p.strip()]
    return refs


def gen_one(project, prompt, image_input, model, ratio, size, timeout, retry):
    """生成单张图，失败重试；返回 zovii item dict（含 status/assetId/fileUrl）"""
    if image_input:
        prompt = f"{STYLE_LOCK}{prompt}"  # 传图≠风格锁定：显式锚定参考图风格
    last_err = None
    for attempt in range(retry + 1):
        try:
            cmd = ["generate-image", project,
                   "--prompt", prompt,
                   "--model", model,
                   "--aspect-ratio", ratio,
                   "--size", size,
                   "--timeout", str(timeout),
                   "-f", "json"]
            if image_input:
                cmd += ["--image-input", ",".join(image_input)]
            out = zovii(cmd)
            item = out[0]
            if item.get("status") == "completed":
                return item
            last_err = f"status={item.get('status')}"
        except RuntimeError as e:
            last_err = str(e)
        if attempt < retry:
            time.sleep(3)
    return {"status": "failed", "error": last_err}


def main():
    ap = argparse.ArgumentParser(description="单行图片生成（行内并发）")
    ap.add_argument("--project", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--ratio", required=True, help="如 3:4")
    ap.add_argument("--prompts", required=True, help="提示词文件，每行一条")
    ap.add_argument("--mode", choices=["sequential", "parallel"], default="sequential")
    ap.add_argument("--cover-ref", default=None, help="封面参考图（本地路径或 assetId）")
    ap.add_argument("--refs", default=None, help='各图参考图，如 "1:a,b;2:c"')
    ap.add_argument("--size", default="2K")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--retry", type=int, default=1)
    ap.add_argument("--manifest", default=None,
                    help="断点续跑清单（JSONL）；已完成图号复用 assetId 跳过生成")
    a = ap.parse_args()

    with open(a.prompts, encoding="utf-8") as f:
        prompts = [ln.rstrip("\n") for ln in f if ln.strip()]
    if not prompts:
        sys.stderr.write("prompts 文件为空\n")
        sys.exit(1)
    extra_refs = parse_refs(a.refs)
    done = load_manifest(a.manifest)
    if done:
        sys.stderr.write(f"[manifest] 断点续跑：已完成的图号 "
                         f"{sorted(done)} 将直接复用，不重复生成\n")
    results = []

    def run_job(n, prompt, image_input):
        if n in done:
            r = dict(done[n])
            r["n"] = n
            r["resumed"] = True
            return r
        r = gen_one(a.project, prompt, image_input, a.model, a.ratio, a.size,
                    a.timeout, a.retry)
        r["n"] = n
        if r.get("status") == "completed":
            append_manifest(a.manifest, r)  # 生成即落盘，中断不丢 assetId
        return r

    if a.mode == "parallel":
        # 全部并发：各图只用自己明示的参考图
        jobs = []
        for n, prompt in enumerate(prompts, start=1):
            image_input = extra_refs.get(n) or None
            jobs.append((n, prompt, image_input))
        with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
            futs = [ex.submit(run_job, n, p, i) for n, p, i in jobs]
            results = [f.result() for f in as_completed(futs)]
        results.sort(key=lambda r: r["n"])
    else:
        # sequential：图1(封面)先生成，封面 assetId 作锚点；图2..N 并发生成
        cover_input = extra_refs.get(1) or ([a.cover_ref] if a.cover_ref else None)
        r1 = run_job(1, prompts[0], cover_input)
        results.append(r1)
        cover_id = r1.get("assetId")
        rest = prompts[1:]
        if rest:
            def rest_job(n, prompt):
                image_input = []
                if cover_id:
                    image_input.append(cover_id)   # 封面锚点
                image_input += extra_refs.get(n, [])
                return run_job(n, prompt, image_input or None)
            with ThreadPoolExecutor(max_workers=len(rest)) as ex:
                futs = [ex.submit(rest_job, n, p) for n, p in enumerate(rest, start=2)]
                results += [f.result() for f in as_completed(futs)]
            results.sort(key=lambda r: r["n"])

    print(json.dumps(results, ensure_ascii=False, indent=2))
    failed = [r["n"] for r in results if r.get("status") != "completed"]
    if failed:
        sys.stderr.write(f"失败图号: {failed}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()

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
        [--size 2K] [--timeout 300] [--retry 1]

参数:
    --prompts   提示词文件，每行一条（第 1 行 = 图1）
    --mode       sequential(默认) / parallel；auto 时由调用方先判断再传入
    --cover-ref 封面参考图（本地路径/assetId；多张用 --refs "1:路径A,路径B"）
    --refs      各图参考图，格式 "图号:路径[,路径...];图号:路径..."（图1的参考图即封面参考图）
    --retry     单张失败重试次数（默认 1）

输出: JSON [{"n":1,"status":"completed","assetId":"...","fileUrl":"..."}, ...]
     失败项 status="failed" 并带 error 字段（不中断后续）；有失败退出码 2
"""
import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


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
    a = ap.parse_args()

    with open(a.prompts, encoding="utf-8") as f:
        prompts = [ln.rstrip("\n") for ln in f if ln.strip()]
    if not prompts:
        sys.stderr.write("prompts 文件为空\n")
        sys.exit(1)
    extra_refs = parse_refs(a.refs)
    results = []

    def run_job(n, prompt, image_input):
        r = gen_one(a.project, prompt, image_input, a.model, a.ratio, a.size,
                    a.timeout, a.retry)
        r["n"] = n
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

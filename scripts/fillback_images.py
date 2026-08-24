#!/usr/bin/env python3
"""下载 zovii 资产并回填为飞书单元格图片（固化「相对路径」约束，内部自动 cd）。

用法:
    python3 fillback_images.py --url <URL> --sheet-id <SID> --row 2 --start-col M \
        --assets "assetId1:图1-封面.png;assetId2:图2-避雷.png" \
        --out <本地目录> [--dry-run]

参数:
    --assets      "assetId:文件名;assetId:文件名"（顺序 = 回填列顺序）
    --start-col   起始回填列字母（M -> 图1图片, N -> 图2图片 ...）
    --out         图片保存目录（脚本内部 cd 后回填，规避绝对路径被拒）

输出: JSON [{"n":1,"assetId":"...","localPath":"...","filled":true}, ...]
"""
import argparse
import json
import os
import subprocess
import sys


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        err = r.stderr or r.stdout
        for esc in ("\x1b[31m", "\x1b[0m", "\x1b[1m", "\x1b[36m"):
            err = err.replace(esc, "")
        raise RuntimeError(err.strip() or "调用失败")
    return json.loads(r.stdout)


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


def main():
    ap = argparse.ArgumentParser(description="下载资产并回填单元格图片")
    ap.add_argument("--url", required=True)
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--row", required=True, help="数据行号，如 2")
    ap.add_argument("--start-col", required=True, help="起始回填列字母，如 M")
    ap.add_argument("--assets", required=True,
                    help="assetId:文件名;assetId:文件名（顺序=回填列顺序）")
    ap.add_argument("--out", required=True, help="图片保存目录")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    pairs = []
    for part in a.assets.split(";"):
        if not part.strip():
            continue
        asset_id, _, fname = part.partition(":")
        pairs.append((asset_id.strip(), fname.strip() or f"{asset_id}.png"))

    os.makedirs(a.out, exist_ok=True)
    results = []
    start_idx = col_index(a.start_col)

    for i, (asset_id, fname) in enumerate(pairs):
        cell = f"{col_letter(start_idx + i)}{a.row}"
        # 1. 下载（绝对路径 OK）
        dl = ["zovii", "download-asset", asset_id, "--out",
              os.path.join(a.out, fname), "-f", "json"]
        if a.dry_run:
            print("DRY-RUN:", " ".join(dl))
            results.append({"n": i + 1, "assetId": asset_id, "filled": False,
                            "dry_run": True})
            continue
        try:
            d = run(dl)
            local = d[0]["localPath"]
        except RuntimeError as e:
            results.append({"n": i + 1, "assetId": asset_id,
                            "filled": False, "error": str(e)})
            continue

        # 2. 回填（必须相对路径：cd 到 out 目录）
        rel = os.path.relpath(local, a.out)
        fb = ["lark-cli", "sheets", "+cells-set-image",
              "--url", a.url, "--sheet-id", a.sheet_id,
              "--range", cell, "--as", "user",
              "--image", f"./{rel}"]
        try:
            run(fb, cwd=a.out)
            results.append({"n": i + 1, "assetId": asset_id,
                            "localPath": local, "cell": cell, "filled": True})
        except RuntimeError as e:
            results.append({"n": i + 1, "assetId": asset_id,
                            "localPath": local, "cell": cell,
                            "filled": False, "error": str(e)})

    print(json.dumps(results, ensure_ascii=False, indent=2))
    failed = [r["n"] for r in results if not r.get("filled", False)
              and not r.get("dry_run", False)]
    if failed:
        sys.stderr.write(f"回填失败图号: {failed}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()

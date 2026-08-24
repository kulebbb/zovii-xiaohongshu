#!/usr/bin/env python3
"""读取飞书表格单元格纯文本（无引号包裹，便于传给 zovii / 展示）。

用法:
    python3 read_cell.py --url <URL> --sheet-id <SID> --range I2

依赖: lark-cli 已登录 (--as user)
输出: 单元格纯文本; 空单元格输出空行
"""
import argparse
import json
import subprocess
import sys


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit(1)
    return json.loads(r.stdout)


def main():
    ap = argparse.ArgumentParser(description="读取飞书表格单元格纯文本")
    ap.add_argument("--url", required=True)
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--range", required=True, help="A1 格式，如 I2")
    a = ap.parse_args()

    d = run(["lark-cli", "sheets", "+csv-get",
             "--url", a.url, "--sheet-id", a.sheet_id,
             "--range", a.range, "--as", "user", "--rows-json"])
    rows = d.get("data", {}).get("rows", [])
    if not rows:
        print("")
        return
    vals = rows[0].get("values", {})
    for v in vals.values():
        if v not in (None, ""):
            print(v)
            return
    print("")


if __name__ == "__main__":
    main()

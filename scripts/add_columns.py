#!/usr/bin/env python3
"""按最大图片数量自动追加列：图1..N提示词、图1..N图片、状态；并把指定行状态初始化为「待处理」。

用法:
    python3 add_columns.py --url <URL> --sheet-id <SID> --max-n 4 --row 2 [--dry-run]

逻辑:
    1. 读表头(A1:ZZ1)找最后一个非空列 -> 起始列
    2. 追加 2N+1 列: 图1..N提示词 | 图1..N图片 | 状态
    3. 把 --row 行(可多个, 逗号分隔)的状态列写为「待处理」

输出: JSON {"start_col": "I", "end_col": "Q", "columns": {"图1提示词": "I", ...}}
"""
import argparse
import json
import subprocess
import sys

COL_A = ord("A")


def col_letter(idx):
    """0 -> A, 25 -> Z, 26 -> AA"""
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(COL_A + rem) + s
    return s


def col_index(letter):
    n = 0
    for ch in letter.upper():
        n = n * 26 + (ord(ch) - COL_A + 1)
    return n - 1


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit(1)
    return json.loads(r.stdout)


def main():
    ap = argparse.ArgumentParser(description="自动追加提示词/图片/状态列")
    ap.add_argument("--url", required=True)
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--max-n", type=int, required=True, help="最大图片数量")
    ap.add_argument("--row", default=None, help="要初始化状态的数据行号，多个用逗号分隔")
    ap.add_argument("--dry-run", action="store_true", help="只打印将执行的命令，不真正写入")
    a = ap.parse_args()
    if a.max_n < 1:
        sys.stderr.write("--max-n 必须 >= 1\n")
        sys.exit(1)

    # 1. 读表头，找最后一个非空列
    d = run(["lark-cli", "sheets", "+csv-get",
             "--url", a.url, "--sheet-id", a.sheet_id,
             "--range", "A1:ZZ1", "--as", "user", "--rows-json"])
    headers = d.get("data", {}).get("rows", [{}])[0].get("values", {})
    start_idx = 0
    for col, val in headers.items():
        if val not in (None, ""):
            start_idx = max(start_idx, col_index(col) + 1)

    # 2. 构造表头
    titles = []
    for i in range(1, a.max_n + 1):
        titles.append(f"图{i}提示词")
    for i in range(1, a.max_n + 1):
        titles.append(f"图{i}图片")
    titles.append("状态")
    n_cols = len(titles)
    start_col, end_col = col_letter(start_idx), col_letter(start_idx + n_cols - 1)

    header_cells = [[{"value": t} for t in titles]]
    cmd1 = ["lark-cli", "sheets", "+cells-set",
            "--url", a.url, "--sheet-id", a.sheet_id,
            "--range", f"{start_col}1:{end_col}1", "--as", "user",
            "--cells", json.dumps(header_cells, ensure_ascii=False)]
    if a.dry_run:
        print("DRY-RUN:", " ".join(cmd1))
    else:
        run(cmd1)

    # 3. 初始化状态列
    status_col = col_letter(start_idx + n_cols - 1)
    rows = []
    if a.row:
        rows = [r.strip() for r in a.row.split(",") if r.strip()]
    for r in rows:
        cmd2 = ["lark-cli", "sheets", "+cells-set",
                "--url", a.url, "--sheet-id", a.sheet_id,
                "--range", f"{status_col}{r}", "--as", "user",
                "--cells", json.dumps([[{"value": "待处理"}]], ensure_ascii=False)]
        if a.dry_run:
            print("DRY-RUN:", " ".join(cmd2))
        else:
            run(cmd2)

    columns = {t: col_letter(start_idx + i) for i, t in enumerate(titles)}
    print(json.dumps({"start_col": start_col, "end_col": end_col,
                      "status_col": status_col, "columns": columns},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

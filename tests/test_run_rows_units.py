#!/usr/bin/env python3
"""run_rows.py 纯函数单测（零依赖，python3 直接运行）。

覆盖：
    - judge_mode 默认 sequential / 显式整组独立才 parallel
    - parse_ref_assignments 拆图提示词 参考图→图号 解析
    - assign_ref_images 参考图分配（显式声明 > 列类型默认；未声明不猜测）
    - 两份副本（scripts/ 与 tests/.agents 运行现场）run_rows.py 一致性

用法: python3 tests/test_run_rows_units.py
"""
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from run_rows import judge_mode, parse_ref_assignments, assign_ref_images  # noqa: E402

REF_NAMES = ["封面参考图", "产品图", "其他参考图1"]
FAILED = []


def check(name, actual, expected):
    if actual == expected:
        print(f"  ✅ {name}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}\n     期望 {expected!r}\n     实际 {actual!r}")


print("[1] judge_mode：默认 sequential，仅显式整组独立才 parallel")
check("空文本 → sequential", judge_mode(""), "sequential")
check("None → sequential", judge_mode(None), "sequential")
check("正常文本 → sequential",
      judge_mode("产品图仅用于图片3，配图以封面为基准保持风格统一"), "sequential")
check("每张图独立 → parallel", judge_mode("每张图独立，各自发挥"), "parallel")
check("各图互不相关 → parallel", judge_mode("各图互不相关"), "parallel")
check("相互独立 → parallel", judge_mode("三张图相互独立"), "parallel")
check("单图层描述词「单独设计构图」不再误触 parallel",
      judge_mode("图片2单独设计产品特写构图"), "sequential")

print("[2] parse_ref_assignments：参考图→图号 显式声明解析")
check("产品图仅用于图片3",
      parse_ref_assignments("产品图仅用于图片3（产品页），只允许出现1次", REF_NAMES),
      {"产品图": {3}})
check("其他参考图1用于图片2",
      parse_ref_assignments("其他参考图1用于图片2", REF_NAMES),
      {"其他参考图1": {2}})
check("一图多号：产品图用于图片3和图片4",
      parse_ref_assignments("产品图用于图片3和图片4", REF_NAMES),
      {"产品图": {3, 4}})
check("「图片3突出产品卖点」不含列名 → 不识别",
      parse_ref_assignments("图片3突出产品卖点，禁止修改产品形态", REF_NAMES), {})
check("「严格按照产品参考图还原」非精确列名 → 不识别",
      parse_ref_assignments("严格按照产品参考图还原，背景干净", REF_NAMES), {})
check("「图片3为产品页」反述不自动关联 → 不识别",
      parse_ref_assignments("图片1为封面图，图片3为产品页", REF_NAMES), {})
check("序号防串：其他参考图10 与 其他参考图1 互不误匹配",
      parse_ref_assignments("其他参考图10用于图片2，其他参考图1用于图片3",
                            ["其他参考图10", "其他参考图1"]),
      {"其他参考图10": {2}, "其他参考图1": {3}})
check("参考图自身序号不被当成目标图号",
      parse_ref_assignments("其他参考图1用于图片2", ["其他参考图1"]),
      {"其他参考图1": {2}})
check("空文本 → 空", parse_ref_assignments("", REF_NAMES), {})

print("[3] assign_ref_images：显式声明 > 列类型默认，未声明不猜测")
check("封面默认图1 + 产品图按声明进图3 + 未声明其他参考图不出现",
      assign_ref_images({"封面参考图": ["c.jpg"], "产品图": ["p.jpg"],
                         "其他参考图1": ["o.jpg"]},
                        "产品图仅用于图片3", 3),
      {1: ["c.jpg"], 3: ["p.jpg"]})
check("全部未声明 → 仅封面参考图进图1",
      assign_ref_images({"封面参考图": ["c.jpg"], "产品图": ["p.jpg"],
                         "其他参考图1": ["o.jpg"]}, "", 3),
      {1: ["c.jpg"]})
check("无任何参考图列内容 → 空",
      assign_ref_images({}, "产品图仅用于图片3", 3), {})
check("显式声明优先于列类型默认（封面参考图被声明到图2）",
      assign_ref_images({"封面参考图": ["c.jpg"]}, "封面参考图用于图片2", 3),
      {2: ["c.jpg"]})
check("声明图号越界（图5 > n=3）→ 忽略该图号（stderr 有警告）",
      assign_ref_images({"产品图": ["p.jpg"]}, "产品图仅用于图片5", 3), {})
check("n=1 时封面参考图仍进图1",
      assign_ref_images({"封面参考图": ["c.jpg"], "产品图": ["p.jpg"]}, "", 1),
      {1: ["c.jpg"]})

print("[4] 两份副本一致性（防止代码类修改漏同步运行现场）")
RUNTIME = os.path.join(ROOT, "tests/.agents/skills/zovii-xiaohongshu/scripts")
if not os.path.isdir(RUNTIME):
    print("  ⏭️ 运行现场副本不存在（未安装现场），跳过")
else:
    for f in ("run_rows.py", "generate_row_images.py"):
        a = open(os.path.join(ROOT, "scripts", f), "rb").read()
        b = open(os.path.join(RUNTIME, f), "rb").read()
        check(f"{f} 双副本 md5 一致",
              (hashlib.md5(a).hexdigest(), hashlib.md5(b).hexdigest())[0],
              hashlib.md5(b).hexdigest())

if FAILED:
    print(f"\n失败 {len(FAILED)} 项: {FAILED}")
    sys.exit(1)
print("\n全部通过 ✅")

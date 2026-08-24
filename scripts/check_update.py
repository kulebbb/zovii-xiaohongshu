#!/usr/bin/env python3
"""skill 自更新检查：对比本地 VERSION 与 GitHub 远端 VERSION。

用法:
    python3 check_update.py [--repo kulebbb/zovii-xiaohongshu] [--timeout 5]

行为:
    - 读本 skill 根目录的 VERSION 作为本地版本
    - 请求 raw.githubusercontent.com/<repo>/main/VERSION 作为最新版本
    - 网络失败 / 文件缺失 → 警告写入 stderr，退出码 0（绝不阻塞主流程）

输出(JSON，stdout):
    {"current":"1.0.0","latest":"1.1.0","update_available":true,
     "update_cmd":"npx skills update zovii-xiaohongshu"}

退出码: 0 = 无需更新或无法判断；1 = 有新版本（调用方应提示用户是否更新）
"""
import argparse
import json
import os
import sys
import urllib.request

DEFAULT_REPO = "kulebbb/zovii-xiaohongshu"
SKILL_NAME = "zovii-xiaohongshu"
BRANCH = "main"


def read_local_version(skill_root):
    try:
        with open(os.path.join(skill_root, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def fetch_latest(repo, timeout):
    url = f"https://raw.githubusercontent.com/{repo}/{BRANCH}/VERSION"
    req = urllib.request.Request(
        url, headers={"User-Agent": f"{SKILL_NAME}-update-check"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8").strip()


def main():
    ap = argparse.ArgumentParser(description="skill 自更新检查")
    ap.add_argument("--repo", default=DEFAULT_REPO, help="GitHub 仓库 owner/repo")
    ap.add_argument("--timeout", type=float, default=5, help="网络超时秒数")
    a = ap.parse_args()

    # 兼容软链安装（npx skills 默认 symlink）：__file__ 所在目录即 skill 根
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = {"current": None, "latest": None, "update_available": False,
              "update_cmd": f"npx skills update {SKILL_NAME}"}

    current = read_local_version(skill_root)
    result["current"] = current
    if not current:
        sys.stderr.write("[update-check] 本地 VERSION 缺失，跳过检查\n")
        print(json.dumps(result, ensure_ascii=False))
        return

    try:
        latest = fetch_latest(a.repo, a.timeout)
    except Exception as e:  # 网络不通等任何异常都不阻塞主流程
        sys.stderr.write(f"[update-check] 检查失败（忽略，继续执行）: {e}\n")
        print(json.dumps(result, ensure_ascii=False))
        return

    result["latest"] = latest
    if latest and latest != current:
        result["update_available"] = True
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

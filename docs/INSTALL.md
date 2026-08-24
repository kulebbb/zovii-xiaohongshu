# 安装指导

## 方式一：一句话让 AI 帮你装（推荐）

把下面这句话发给你的 AI（Claude Code / Codex 等）：

```text
帮我安装小红书批量生图 skill：https://github.com/kulebbb/zovii-xiaohongshu
```

AI 会自动执行安装命令、检查前置依赖并验证，全程无需你动手。

## 方式二：终端一条命令

```bash
npx skills add kulebbb/zovii-xiaohongshu -g
```

- `-g`：全局安装（所有项目可用）；去掉则只安装到当前项目
- 默认以软链方式安装到各 agent 的 skills 目录，后续更新一处生效
- 想只装给特定 agent：`npx skills add kulebbb/zovii-xiaohongshu -g -a claude-code`
- 非交互安装（CI 友好）：末尾加 `-y --all`

## 方式三：手动 clone

适合不想用 skills CLI 的用户，直接把仓库放进所用 agent 的 skills 目录：

```bash
# Claude Code 示例
git clone https://github.com/kulebbb/zovii-xiaohongshu ~/.claude/skills/zovii-xiaohongshu
```

其他 agent 的 skills 目录路径以其自身文档为准。

---

## 前置依赖

### 1. zovii CLI（AI 生图引擎）

```bash
npm install -g zovii
```

登录（手机号 + 验证码）：

```bash
zovii login
```

验证：`cat ~/.config/zovii/auth.json` 中含 `access_token` 即成功。
更多方式见官方文档：<https://zovii.studio/agent-install.md>。

### 2. 飞书 CLI（lark-cli）

按官方指引安装：<https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide.md>

验证登录态：任意执行一条 `lark-cli sheets ...` 命令；报权限错时按 lark-shared skill 处理认证。

---

## 验证安装

```bash
# 1. skill 已就位
npx skills list | grep zovii-xiaohongshu

# 2. 自检脚本可运行（应输出 JSON，update_available 为 false 或网络警告）
python3 ~/.claude/skills/zovii-xiaohongshu/scripts/check_update.py
```

最后对 AI 说一句实战检验：

```text
帮我用这个表格批量生成小红书图片：<你的飞书表格链接>
```

AI 开始向你确认「处理哪些行 / 用哪个项目 / 模型 / 比例」即说明一切正常。

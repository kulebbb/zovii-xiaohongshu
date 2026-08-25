# zovii-xiaohongshu

> 飞书表格 → 小红书图片组，一句话让 AI 全自动完成。

把飞书表格里「每行一组」的小红书图片需求（标题正文、图片数量、拆解思路、参考图），批量变成真实图片并自动回填表格——提示词生成、AI 生图、图片回填、状态跟踪全部自动化。

```
飞书表格（每行一组需求）
   │  ① 读表识别列结构
   ▼
逐行生成提示词 ──► 回填「图1~N提示词」列（可人工把关后再出图）
   │  ② zovii AI 生图（封面锚定风格 / 全图并发）
   ▼
下载图片 ──► 回填为飞书单元格图片 ──► 更新状态与耗时
```

## ✨ 特性

- **一行 = 一组图**：图 1 为封面，图 2~N 为配图；支持封面先行锚定整组风格，也支持全图独立并发
- **提示词先行**：每张图的提示词自动生成并回填表格，不满意可改完再出图
- **行间并发**：默认 10 行同时处理，失败自动重试，中断可按状态列续跑
- **全程可追踪**：每行维护「状态」「耗时(秒)」列，失败不静默、最后统一汇报
- **临时文件自管理**：参考图统一下载到本地 `tmp/` 使用，任务结束自动清理，不留垃圾

## 📦 一句话安装

把下面这句话发给你正在使用的 AI（Claude Code / Codex 等）：

```text
帮我安装小红书批量生图 skill：https://github.com/kulebbb/zovii-xiaohongshu
```

或者在终端自己执行：

```bash
npx skills add kulebbb/zovii-xiaohongshu -g
```

> 支持 Claude Code、Codex、Cursor、OpenCode 等 70+ agent。更多安装方式见 [docs/INSTALL.md](docs/INSTALL.md)。

## 前置依赖

| 依赖 | 用途 | 检查命令 |
|---|---|---|
| [zovii CLI](https://zovii.studio/agent-install.md) | AI 生图引擎 | `zovii --version` |
| 飞书 CLI（lark-cli） | 读写飞书表格 | `lark-cli --version` |

两者都需要完成登录，详细步骤见 [docs/INSTALL.md](docs/INSTALL.md)。

## 🚀 快速开始

装好后对 AI 说一句：

```text
帮我用这个表格批量生成小红书图片：<你的飞书表格链接>
```

AI 会依次和你确认：处理哪些行、用哪个 zovii 项目、生图模型、图片比例，然后自动跑完全部流程并回填表格。

表格里每行建议包含：标题+正文（小红书文案）、图片数量 N、图片拆解提示词（可选）、参考图若干列（列名含「参考图」，如 参考图1/参考图2…，可选；用在哪张图在拆图提示词里声明）。缺的列 skill 会自动补建。

## 🔄 更新

skill 每次运行会自动检查 GitHub 上的最新版本，有新版会**自动更新**（更新失败会停下告知你）。**更新后需重启 Agent 客户端（或开新会话），新版规则才会生效。**也可以随时手动更新：

```bash
npx skills update zovii-xiaohongshu
```

详见 [docs/UPDATE.md](docs/UPDATE.md)。

## 🧠 工作原理

完整工作流（列结构识别、依赖判断、并发策略、兜底命令）见 [`SKILL.md`](SKILL.md)；辅助脚本在 [`scripts/`](scripts/)，零第三方依赖，仅调用 lark-cli 与 zovii CLI。

## License

[MIT](LICENSE)

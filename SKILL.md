---
name: zovii-xiaohongshu
description: 基于飞书表格批量生成小红书图片组。读取飞书表格（每行=一组图片需求：标题正文、图片数量、图片拆解提示词、产品图/封面参考图/其他参考图），为每张图生成提示词并回填表格，再用 zovii CLI 逐张生成图片（先封面、再以封面为参考图生成配图），最后下载图片并回填为飞书单元格图片。Use when user mentions 小红书图片 / 小红书封面 / 小红书配图 / 批量生成图片 / 飞书表格生图 / 表格生成小红书图 / zovii 小红书 / 图片拆解, or provides a Feishu sheet URL with image-generation requirements.
---

# 飞书表格 → 小红书图片组（zovii 生图）

把「飞书表格里每行一组的小红书图片需求」批量变成「小红书图片组」，并回填到表格。

## 核心概念

- **一行 = 一组图片需求**：标题+正文（小红书文案）、图片需求数量 N、图片拆解提示词、产品图、封面参考图、其他参考图（0~n 张）
- **图 1 = 封面图**，图 2~N = 配图
- **两段式生成**：先用图 1 提示词生成封面 → 再把封面图作为参考图（风格锚点）逐张生成配图，保证整组风格一致
- **只用单图生成**（`zovii generate-image`），**禁止** `batch-generate-image`
- **参考图使用**：以「拆解提示词 / 正文中明示的参考图要求」为准；没明示就不用

---

## Layer 1 — 初始化检查（每次使用前必须执行，按顺序）

### 1.0 skill 自更新检查（最先执行）
```bash
python3 <skill>/scripts/check_update.py
```
- 输出 `"update_available": true`（退出码 1）→ 告知用户有新版本，询问是否更新；同意 → 执行 `npx skills update zovii-xiaohongshu` 后继续；拒绝 → 继续
- 输出 `false` 或网络失败（stderr 有警告）→ **不阻塞，直接继续**

### 1.1 zovii CLI
```bash
which zovii && zovii --version
```
- ❌ 未安装 → 告诉用户，请其运行：`帮我安装 zovii CLI：https://zovii.studio/agent-install.md`
  （或自行执行 `npm install -g zovii`，装完再继续）
- ✅ 已安装 → 检查是否最新版本：
  ```bash
  zovii --version          # 本地版本
  npm view zovii version   # npm 最新版本（若 npm 安装）
  ```
  本地版本落后 → 告知用户有新版，询问是否更新（`npm install -g zovii`）；用户不更新则继续。

### 1.2 飞书 CLI
```bash
which lark-cli && lark-cli --version
```
- ❌ 未安装 → 告诉用户，请其运行：`帮我安装飞书 CLI：https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide.md`
- ✅ 已安装 → 检查版本，有新版则提示用户更新

### 1.3 登录态
- zovii：`cat ~/.config/zovii/auth.json` 确认含 `access_token`；缺失 → 引导 `zovii login`（手机号+验证码）
- 飞书：`lark-cli` 调用报权限错时，按 lark-shared skill 处理认证

---

## Layer 2 — 必问信息（AskUserQuestion，按顺序，别猜）

1. **飞书表格 URL**
   - 优先从用户消息提取 `https://...feishu.cn/(wiki|sheets)/...` 链接；没有就问
2. **处理颗粒度**（用户确认的第 5 点，必须问）
   - 全部行 / 指定行号列表（如 `2-10` 或 `2,5,8`）/ 指定状态的行（如「待处理」行）/ 只处理新追加行
3. **zovii 项目**（projectId）
   - 先 `zovii list-projects` 让用户挑；没有合适项目 → `zovii create-project "<名称>"` 新建
4. **模型**（用户确认的第 6 点，必须问）
   - 选项：`doubao-seedream-4-5-251128` / `doubao-seedream-5-0-260128` / `doubao-seedream-5-0-pro-260628` / `midjourney-fast` / `ws-nano-banana-pro`（默认 `doubao-seedream-5-0-pro-260628`，小红书风格建议豆包系列）
5. **图片比例**（用户确认的第 6 点，必须问）
   - 小红书封面/配图默认 `3:4`；选项：`1:1` / `3:4` / `4:5` / `2:3` / `9:16` / `4:3` / `16:9`
6. **本地工作目录**
   - 参考图（**临时文件**）：`<cwd>/tmp/zovii-refs/<任务ID>/refs/<行号>/`，任务结束必须删除
   - 生成图（交付物）：默认 `<cwd>/xiaohongshu/<YYYY-MM-DD>/images/`

---

## Layer 3 — 工作流

### Step 1 — 读取表格、识别列结构

```bash
# 若 URL 是 wiki 链接，先解析成 sheet token（见 lark-wiki skill）
lark-cli sheets +workbook-info --url "<URL>"          # 拿 sheet 列表
lark-cli sheets +csv-get --url "<URL>" --sheet-name "<sheet>" --range "A1:Z10"   # 读表头+样例数据
```

**识别列**（表头含义不明确时与用户确认）：
- 标题列、正文列（小红书文案）
- 图片数量列（N，决定图 1~N）
- 图片拆解提示词列（用户对整组的拆解说明）
- 产品图列、封面参考图列、其他参考图列（0~n 列，注意列名可能带序号）

> ⚠️ 表头可能是中文/英文/口语化，**不要猜**；读出来逐列与用户核对一次。

### Step 2 — 新增列（自行添加，不依赖用户预设）

在数据右侧追加，列头按实际最大图片数动态生成（先算所有目标行中 N 的最大值 `MAXN`）：

| 新增列 | 说明 |
|---|---|
| `图1提示词` ~ `图{MAXN}提示词` | 每张图的生成提示词（文本） |
| `图1图片` ~ `图{MAXN}图片` | 生成结果回填（单元格图片） |
| `状态` | `待处理` / `提示词已生成` / `图片已生成` / `已完成`（默认给所有目标行写 `待处理`） |

加列方式：`lark-cli sheets +cells-set` 写表头（或先插入列再写，视表格现状）；表头样式参照 lark-sheets-visual-standards 与全表风格保持一致。

> **推荐用脚本**（自动算列字母 + 生成 JSON，避免维度错误）：
> ```bash
> python3 <skill>/scripts/add_columns.py --url "<URL>" --sheet-id "<SID>" --max-n <MAXN> --row <行号,可逗号分隔> [--dry-run]
> ```
> 输出 `columns` 映射（列字母 → 含义），后续回填直接用；脚本已把指定行状态初始化为 `待处理`。

### Step 3 — 准备参考图（先下载到本地 tmp/，再上传给 zovii）

> 铁律：参考图是**临时文件**，一律先下载到本地 tmp 目录（`--image-input` 只吃本地路径/assetId），任务结束（无论成败）必须删除。

逐行提取该行用到的参考图（产品图 / 封面参考图 / 其他参考图），按单元格内容形态处理。目标目录：`<cwd>/tmp/zovii-refs/<任务ID>/refs/<行号>/`：

| 单元格内容形态 | 处理方式 |
|---|---|
| URL 文本（http/https） | `curl -L -o <tmp_refs>/<row>-<name>.jpg "<URL>"` 直接下载 |
| 单元格图片（embed-image） | `+cells-get --include rich_text` 拿 `image_token` → `lark-cli api GET "/open-apis/drive/v1/medias/<token>/download" --as user --output ./<文件名>` 下载；**`--output` 只接受相对路径**（先 `cd` 到目标目录），且二进制文件名不可预测，必须显式 `--output` |
| 浮动图片 | `lark-cli sheets +float-image-list` 拿 image_token，下载后使用 |
| 飞书云盘/文档链接 | 用 lark-drive skill 下载 |

- 文件名规范：`<行号>-<类型>-<序号>.jpg`（如 `3-产品图-1.jpg`、`3-封面参考图.jpg`、`3-其他参考图-2.jpg`）
- 未明确使用的行可不下载；全部下载更稳妥（体积可控时）
- 下载后记录「行号 → 本地参考图路径」的映射，供 Step 4/5 使用
- **收尾清理**：全部图片生成并回填完成后，删除整个任务临时目录：`rm -rf <cwd>/tmp/zovii-refs/<任务ID>`

### Step 4 — 生成每张图的提示词并回填（核心智能环节）

对每个目标行，基于「拆解提示词 + 正文 + 图片数量 N」为图 1~N 各生成一条提示词：

**图 1（封面）**：小红书封面要点——吸睛主视觉、强对比、产品主体突出、可叠加主标题文字（字号大、居左/居中）、情绪钩子。
**图 2~N（配图）**：按拆解提示词的节奏展开——使用场景、成分/卖点细节、对比展示、步骤演示、用户证言、效果前后等。

**每条提示词的结构**（生成时按此组织，保证 zovii 可用）：
1. 主体与场景（产品/人物/环境）
2. 画面内容（构图、景别、动作）
3. 风格与氛围（光影、色调、质感、材质）
4. 画面文字（如需包含文案，给出具体字句与排版位置）
5. **参考图声明**：本图是否使用参考图、用哪张（产品图 / 封面参考图 / 其他参考图-序号）——只依据拆解提示词与正文中的**明示**；未明示则不写此条
6. 画质后缀（`8k, high detail` 等，统一追加）

**回填**：把每条提示词写入对应行的「图N提示词」列，并将该行「状态」置为 `提示词已生成`。
（逐行生成并回填，完成后向用户展示几条样例确认风格，用户不满意可调整后再批量。）

> **推荐用脚本取值**（避免手写 JSON 解析）：
> ```bash
> python3 <skill>/scripts/read_cell.py --url "<URL>" --sheet-id "<SID>" --range I2   # 输出纯文本提示词
> ```

### Step 5 — 生成图片（并发版，行内按依赖判断）

对目标行，确认项目、模型、比例后执行：

**依赖判断（行内模式）**：解析拆图提示词/特殊要求——出现图间引用词（`作为参考图`/`以封面为基准`/`基于图N`/`延续`/`承接`/`参照`/`跟随`/`锚点`/`保持一致`/`在图N基础上`/`使用图1`等）→ `sequential`（封面→配图并发）；明确独立（`每张图独立`/`各图互不相关`等）或**无依赖表述** → `parallel`（全图并发，默认）。

> **推荐用脚本**（固化并发 + 失败重试 + 参考图链路）：
> ```bash
> # 行内并发（单行）：--mode sequential=封面→配图并发 / parallel=全图并发
> python3 <skill>/scripts/read_cell.py --url "<URL>" --sheet-id "<SID>" --range I2 > prompts.txt
> python3 <skill>/scripts/read_cell.py --url "<URL>" --sheet-id "<SID>" --range J2 >> prompts.txt
> # ...
> python3 <skill>/scripts/generate_row_images.py --project <projectId> \
>   --model <模型> --ratio <比例> --prompts prompts.txt --mode <sequential|parallel> \
>   [--refs "1:产品图路径,封面参考图路径"] --size 2K
> ```
> 输出 JSON：`[{"n":1,"assetId":"..."}, ...]`，失败项 status=failed 带 error、不中断后续；有失败退出码 2。

> **推荐用脚本（行间并发）**：多行同时处理，默认 10 行并发；每行自动读输入、判断行内模式、下载参考图、生成、回填、更新状态：
> ```bash
> python3 <skill>/scripts/run_rows.py --url "<URL>" --sheet-id "<SID>" --rows "2,3,5" \
>   --project <projectId> --model <模型> --ratio <比例> \
>   [--max-workers 10] [--out <dir>] [--dry-run]
> ```
> 每行流程：读图片数量/拆图提示词/各图提示词（列由表头自动定位）→ `judge_mode` 判行内模式 → 下载参考图到 **tmp 临时目录** `tmp/zovii-refs/<任务ID>/refs/<行>/`（单元格图片/URL）→ 调 `generate_row_images` → 调 `fillback_images` 回填 → 更新状态列 → **任务结束自动删除参考图临时目录（成败都删，`--keep-tmp` 调试保留）**。**自动维护「耗时(秒)」列**（状态列后一列，表头缺失时自动添加）：记录每行完整流程耗时。输出按行号排序 JSON（含 `elapsed` 字段），失败行退出码 2；清理信息走 stderr 不污染 JSON。
> ⚠️ **并发稳定性**：① `main` 串行预取所有行输入（表头/数量/提示词矩阵/参考图），worker 不重复读表头，避免多行并发读表格触发飞书限流（`99991400`）；② 参考图下载串行化到预取阶段；③ `run_cli` 遇限流自动退避重试；④ 参考图下载 `--output` 用相对路径 + 每行独立 `refs/<行号>/` 目录 + token 前缀唯一文件名。

**手动执行（脚本不可用时兜底）**：

**第一步 — 封面图（图 1）**
```bash
zovii generate-image <projectId> \
  --prompt "<图1提示词>" \
  [--image-input <封面参考图本地路径>] \
  --model <模型> --aspect-ratio <比例> --size 2K
```
- 若图 1 提示词明示使用封面参考图，则 `--image-input` 传该参考图；否则不传
- 记录返回的 `assetId`（= 封面 assetId，后续作为风格锚点）

**第二步 — 配图（图 2~N）**
```bash
zovii generate-image <projectId> \
  --prompt "<图N提示词>" \
  --image-input "<封面assetId>[,<该图明示参考图路径>...]" \
  --model <模型> --aspect-ratio <比例> --size 2K
```
- `--image-input` 第一个**固定传封面 assetId**（保持整组风格一致），其后追加该图提示词明示的其他参考图（本地路径），逗号分隔
- 逐张生成、逐张记录 assetId；等待完成再生成下一张
- 任何一张失败 → 记录失败原因到该行「状态」，继续后续行，最后统一汇报

### Step 6 — 下载图片并回填单元格图片

> **推荐用脚本**（内部处理相对路径约束 + 逐张下载回填 + 结果验证）：
> ```bash
> python3 <skill>/scripts/fillback_images.py --url "<URL>" --sheet-id "<SID>" --row <行号> \
>   --start-col <图1图片列字母> \
>   --assets "<assetId1>:图1-封面.png;<assetId2>:图2.png;..." \
>   --out <out>/images
> ```
> `--assets` 顺序 = 回填列顺序（M→图1, N→图2 ...）；脚本自动 `cd` 后以相对路径回填；输出每张 localPath + filled 状态，有失败返回退出码 2。

**手动执行（脚本不可用时兜底）**：

```bash
mkdir -p <out>/images
zovii download-asset <assetId> --out <out>/images/<行号>-图<N>.png

# ⚠️ +cells-set-image 的 --image 只接受「当前工作目录内的相对路径」，绝对路径会被 Validate 拒绝
# 标准做法：先 cd 进图片目录，再用相对路径回填
cd <out>/images
lark-cli sheets +cells-set-image --url "<URL>" --sheet-name "<sheet>" \
  --range "<图N图片列><行号>" --image "./<行号>-图<N>.png"
```
- 逐张下载 → 逐张回填到该行「图N图片」单元格（单元格图片，随单元格移动）
- **回填路径铁律**：一律先 `cd <out>/images`，`--image` 传相对路径（如 `./图1.png`）；传绝对路径必被拒
- 全部回填完成后，该行「状态」置为 `已完成`（有失败则置 `图片已生成` 并备注）
- 全部行结束后删除参考图临时目录：`rm -rf <cwd>/tmp/zovii-refs/<任务ID>`

---

## 脚本工具（scripts/）

稳定化辅助脚本，零第三方依赖（仅调用 lark-cli / zovii CLI），**优先使用，手动命令兜底**：

| 脚本 | 职责 | 关键参数 |
|---|---|---|
| `check_update.py` | skill 自更新检查（本地 VERSION vs GitHub 远端） | `[--repo] [--timeout]`，退出码 1=有新版 |
| `add_columns.py` | 自动追加图1~N提示词/图片/状态列并初始化状态 | `--url --sheet-id --max-n --row [--dry-run]` |
| `read_cell.py` | 读单元格纯文本（供取提示词） | `--url --sheet-id --range` |
| `generate_row_images.py` | 单行生成，行内并发（sequential=封面→配图并发 / parallel=全图并发），带重试 | `--project --model --ratio --prompts --mode [--refs] [--cover-ref]` |
| `fillback_images.py` | 下载资产 + 回填单元格图片（自动处理相对路径） | `--url --sheet-id --row --start-col --assets --out [--dry-run]` |
| `run_rows.py` | **行间并发调度**（默认10行）：每行自动读输入/判依赖/下载参考图/生成/回填/状态 | `--url --sheet-id --rows --project --model --ratio [--max-workers] [--out] [--dry-run]` |

通用约定：所有脚本走 `--as user`；`<skill>` 指本 skill 安装目录（未安装时用项目路径）；脚本只读/写飞书表格与 zovii 资产，不执行其它副作用。

---

## 决策规则（铁律）

1. **先问再干**：处理颗粒度、模型、比例三问必须在开始前完成
2. **只单图生成**：一律 `zovii generate-image`，禁止 `batch-generate-image`
3. **按依赖决定封面锚点**：提示词明示图间依赖（配图用图1/封面作参考等）→ 封面先行、封面 assetId 作配图锚点；**无依赖表述 → 行内并发（parallel）**，不用封面锚点
4. **行间并发**：多行独立同时处理，默认并发 10 行（`--max-workers` 可调）；参考图下载按行隔离目录
5. **识别列不猜**：表头含义必须读出来后核对，不按直觉猜列名
6. **状态可追踪**：每行状态列全程维护，中断可续跑（续跑时按状态跳过已完成行）
7. **失败不静默**：单张失败记录原因，整批结束统一汇报失败清单
8. **回填用相对路径**：`+cells-set-image` 的 `--image` 只接受当前目录内相对路径，先 `cd` 到图片目录再回填
9. **默认并发**：无图间依赖表述即行内并发；依赖识别见 Step 5 词表
10. **参考图临时化**：参考图先下载到 `tmp/zovii-refs/<任务ID>/` 再上传 zovii；任务结束（无论成败）必删该目录（脚本已内置 finally 清理）；生成图是交付物不在此列

---

## 常用命令速查

| 用途 | 命令 |
|---|---|
| 看项目 | `zovii list-projects` |
| 建项目 | `zovii create-project "<名称>"` |
| 单图生成 | `zovii generate-image <projectId> --prompt "..." [--image-input <ref>] --model <M> --aspect-ratio <R> --size 2K` |
| 下载资产 | `zovii download-asset <assetId> --out <path>` |
| 列资产 | `zovii list-assets <projectId> --type image` |
| 看表格子表 | `lark-cli sheets +workbook-info --url "<URL>"` |
| 读表格 | `lark-cli sheets +csv-get --url "<URL>" --sheet-name "<s>" --range "A1:Z50"` |
| 写文本 | `lark-cli sheets +cells-set --url "<URL>" --sheet-name "<s>" --range "A1" --cells '[[{"value":"..."}]]'` |
| 回填单元格图片 | `lark-cli sheets +cells-set-image --url "<URL>" --sheet-name "<s>" --range "F2" --image "./x.png"` |
| 列浮动图片 | `lark-cli sheets +float-image-list --url "<URL>" --sheet-name "<s>"` |

> 涉及飞书表格的深层操作（列结构、样式、批量写入、浮动图片、wiki 解析等），按需加载 `lark-sheets` / `lark-drive` / `lark-wiki` / `lark-shared` skill；zovii 完整命令参考见 `zovii` skill 的 references/commands.md。

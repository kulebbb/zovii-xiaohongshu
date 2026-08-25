---
name: zovii-xiaohongshu
description: 基于飞书表格批量生成小红书图片组。读取飞书表格（每行=一组图片需求：标题正文、图片数量、图片拆解提示词、若干参考图列），为每张图生成提示词并回填表格，再用 zovii CLI 逐张生成图片（先封面、再以封面为参考图生成配图），最后下载图片并回填为飞书单元格图片。Use when user mentions 小红书图片 / 小红书封面 / 小红书配图 / 批量生成图片 / 飞书表格生图 / 表格生成小红书图 / zovii 小红书 / 图片拆解, or provides a Feishu sheet URL with image-generation requirements.
---

# 飞书表格 → 小红书图片组（zovii 生图）

把「飞书表格里每行一组的小红书图片需求」批量变成「小红书图片组」，并回填到表格。

## 核心概念

- **一行 = 一组图片需求**：标题+正文（小红书文案）、图片需求数量 N、图片拆解提示词、参考图（0~n 列，列名含「参考图」，无类别之分）
- **图 1 = 封面图**，图 2~N = 配图
- **两段式生成（唯一模式，默认 sequential）**：先用图 1 提示词生成封面 → 再以封面 assetId 作**所有配图的风格锚点**逐张生成配图，整组风格一致由锚点保证，无需任何提示词表述；仅当拆图提示词明确写「每张图独立/各图互不相关」才退化为无锚点的全图并发
- **只用单图生成**（`zovii generate-image`），**禁止** `batch-generate-image`
- **参考图使用（全显式，无类别）**：参考图就是参考图，列名含「参考图」（参考图1/参考图2…）即为参考图列；每张参考图用在哪张图，由拆图提示词**显式声明**（如「参考图1用于图片1」「参考图2用于图片3」）——**无任何默认分配**，未声明不附加、不猜测（脚本 stderr 打印跳过提醒）

## 拆图提示词写法约定

| 内容 | 是否必写 | 说明 |
|---|---|---|
| 封面锚点 | 不用写 | 默认生效：封面先生成，封面 assetId 自动作所有配图的风格锚点 |
| 每张参考图用在哪张图 | **必写（全显式）** | 写法：「参考图1用于图片1」「参考图2用于图片3」（参考图列名与目标图号写在**同一句**，可声明多个图号）；多图号用「和/与」连接（如「参考图1用于图片2和图片3」），**勿用顿号**（顿号会断句导致只取第一个图号）；未声明则该参考图不参与任何图的生成（脚本 stderr 提醒） |
| 每张图独立 | 可选 | 明确写「每张图独立/各图互不相关」才退出默认锚点（整组退化为无锚点并发） |

示例（可直接粘贴到表格「拆图提示词」列）：

```
1、标题必须是封面图1的标题，文字醒目吸睛。
2、图片2选取正文中的全部知识点，标题与对应内容必须语义一致，排版清晰有序，禁止出现医生形象。
3、参考图1用于图片1（提供整组画风），参考图2仅用于图片3，只允许出现1次，禁止出现无关信息。
4、图片3突出产品卖点，严格按照参考图2还原，禁止添加参考图2中不存在的包装形态，背景干净无杂乱元素。
5、图片1为封面图，图片2为知识点，图片3为产品页；配图以封面为基准保持整组风格统一。
```

> 解析规则：按「参考图列名 + 图号同句」精确识别——第 3 条是标准声明写法；第 4 条「严格按照参考图2还原」与图号不同句、且第 3 条已声明，不会被重复误识别；第 5 条「图片3为产品页」不含参考图列名，不会触发任何分配。参考图无类别之分，除封面锚点外的一切都由拆图提示词显式驱动。

## 执行守则（铁律，来自实战复盘）

1. **先看参考图，再写提示词**：写含参考图的提示词前，必须先下载并查看该图用到的参考图，产出特征清单（画风媒介/主色配色/构图框架/主体姿态/装饰元素/字体感受），提示词风格段**逐条复述清单、禁止编造**。凭刻板印象写的风格词若与参考图相反，等于把模型往反方向推（实测：裸传参考图相似度仅 5%~8%，锚定+复述后 ~93%；run4 反例：见「夜醒」编出「月亮星星暖橙水彩侧躺」，与参考图四维全面冲突，匹配度跌到 ~10%）。
   > 两把锁脚本已内置：`generate_row_images.py` 对**所有图**自动前置 TEXT_LOCK（文字强约束，防模型自由发挥编造文案）、对**带参考图的图**再前置 STYLE_LOCK（风格锁定）；手动调 `zovii generate-image` 时必须自己写全复述清单与文字约束。
2. **pilot 先行：先跑 1 行看全图，确认后再批量**：正式批量前先用 `--rows <一行>` 跑完整一组，**看完该行全部 N 张图**（不只封面）给用户确认；认可后跑剩余行——同一命令同一 `--out` 重跑走 manifest 断点续跑，pilot 行不重复消耗 credit。
3. **禁止从零自由生成完整提示词**：每条提示词必须按 Step 4 的「条款规则表」组合 + 内容槽位填充；若委托 subagent 写提示词，必须把条款表与预检清单**全文嵌入**其任务描述（run4 教训：执行者一换，说教式规则即失效）。
4. **CLI 升级后先小样本试跑**：lark-cli / zovii 升级可能删除或改名参数导致脚本接口断裂；升级后先用 1 行数据完整试跑再批量。

---

## Layer 1 — 初始化检查（每次使用前必须执行，按顺序）

### 1.0 skill 自更新检查（最先执行）
```bash
python3 <skill>/scripts/check_update.py
```
- 输出 `"update_available": true`（退出码 1）→ **自动执行更新**，不再询问用户：`npx skills update zovii-xiaohongshu`（clone 安装的用户改用 `git pull`）；更新完成后**向用户报告版本变化（X→Y）并 `cat <skill>/VERSION` 复核更新已落地**，再继续任务。⚠️ 更新命令失败 → **重试一次**；仍失败 → **停下并明确告知用户**检查网络/代理后稍后手动执行，**不要静默继续**（更新未落地会带着旧版本跑）。
- ⚠️ **更新生效条件**：更新只改磁盘文件，**已运行会话的上下文里仍是旧版规则**——更新完成后必须提醒用户：**重启 Agent 客户端（或开新会话）后新版本才生效**。
- 输出 `false` 或网络失败（stderr 有警告）→ **不阻塞，直接继续**（无法判断是否有新版时，不强行更新）
- 检测内置三源回退（GitHub raw → fastly.jsdelivr → cdn.jsdelivr），弱网下单源超时会自动换源重试

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
   - ⚠️ **开跑前必须向用户复述口径并确认**：「将处理**绝对行号** X,Y,Z…（表头为第 1 行，数据从第 2 行起）；若表格有筛选/隐藏行，视觉行号可能与绝对行号不一致」——防止把「第 N 条数据」错传成绝对行号导致整批错位
3. **zovii 项目**（projectId）
   - 先 `zovii list-projects` 让用户挑；没有合适项目 → `zovii create-project "<名称>"` 新建
4. **模型**（用户确认的第 6 点，必须问；**先拉取列表，只展示要求的两个候选**，向用户展示显示名，脚本 `--model` 才用 ID）
   - 先跑 `zovii list-models ai_image` 拉取产品当前可用模型列表（工具 `ai_image` 下）
   - **只保留**这两个要求模型，其余一律不展示：
     * **GPT Image 2**（`ws-gpt-image-2`，**默认预选**，skill 文档默认）：参考图风格还原强（实测相似度 ~93%），中文手账/蜡笔手写风文字渲染稳；要严格还原参考图风格时选它，两轮 UAT 均用此模型
     * **Seedream 5.0 Pro**（`doubao-seedream-5-0-pro-260628`）：豆包系质量标杆；不依赖参考图还原、追求豆包生态插画风格时选它
   - **默认保持当前选择 = 预选 GPT Image 2**；若 `list-models` 里恰好查不到其中一个（产品下架/改名），只展示查得到的那个，并提示用户另一候选不可用
   - 向用户展示时用显示名（GPT Image 2 / Seedream 5.0 Pro），确认后 `--model` 才填对应 ID
5. **图片比例**（用户确认的第 6 点，必须问）
   - 小红书封面/配图默认 `3:4`；选项：`1:1` / `3:4` / `4:5` / `2:3` / `9:16` / `4:3` / `16:9`
6. **本地工作目录**
   - 参考图（**临时文件**）：`<cwd>/tmp/zovii-refs/<任务ID>/refs/<行号>/`，任务结束必须删除
   - 生成图（交付物）：`--out` 即图片最终所在目录，**不嵌套子目录**；`run_rows` 默认 `<cwd>/xiaohongshu/<YYYY-MM-DD>/<行号列表>/`（断点清单 `manifest-rowN.jsonl` 也在同一目录）

---

## Layer 3 — 工作流

### Step 1 — 读取表格、识别列结构

```bash
# 若 URL 是 wiki 链接，先解析成 sheet token（见 lark-wiki skill）
lark-cli sheets +workbook-info --url "<URL>"          # 拿 sheet 列表
lark-cli sheets +csv-get --url "<URL>" --sheet-name "<sheet>" --range "A1:Z10"   # 读表头+样例数据
```

> ⚠️ **csv-get 读不到单元格嵌入图片**：参考图列（列名含「参考图」）在 csv-get 输出里显示为**空**，别误判成「用户还没放图」；读参考图列必须用 `+cells-get --include rich_text` 拿 `image_token`（下载方式见 Step 3）。

**识别列**（表头含义不明确时与用户确认）：
- 标题列、正文列（小红书文案）
- 图片数量列（N，决定图 1~N）
- 图片拆解提示词列（用户对整组的拆解说明）
- 参考图列（**列名含「参考图」**即为参考图列，如 参考图1/参考图2…，0~n 列，无类别之分）
- **必需列**（表头必须精确匹配，缺失即报错退出并列出识别到的列名）：`图片数量`、`拆图提示词`、`图1提示词`、`图1图片`、`状态`

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

逐行提取该行用到的参考图（列名含「参考图」的列，按拆图提示词声明确定用在哪张图），按单元格内容形态处理。目标目录：`<cwd>/tmp/zovii-refs/<任务ID>/refs/<行号>/`：

| 单元格内容形态 | 处理方式 |
|---|---|
| URL 文本（http/https） | `curl -L -o <tmp_refs>/<row>-<name>.jpg "<URL>"` 直接下载 |
| 单元格图片（embed-image） | `+cells-get --include rich_text` 拿 `image_token` → `lark-cli api GET "/open-apis/drive/v1/medias/<token>/download" --as user --output ./<文件名>` 下载；**`--output` 只接受相对路径**（先 `cd` 到目标目录），且二进制文件名不可预测，必须显式 `--output` |
| 浮动图片 | `lark-cli sheets +float-image-list` 拿 image_token，下载后使用 |
| 飞书云盘/文档链接 | 用 lark-drive skill 下载 |

- 文件名规范：`<行号>-<参考图列名>-<序号>.jpg`（如 `3-参考图1-1.jpg`、`3-参考图2-1.jpg`）
- 未明确使用的行可不下载；全部下载更稳妥（体积可控时）
- 下载后记录「行号 → 本地参考图路径」的映射，供 Step 4/5 使用
- **收尾清理**：全部图片生成并回填完成后，删除整个任务临时目录：`rm -rf <cwd>/tmp/zovii-refs/<任务ID>`

### Step 4 — 生成每张图的提示词并回填（核心智能环节）

> ⚠️ **禁止从零自由生成完整提示词**（08-25 run4：subagent 自由发挥致整组跑偏）。每条提示词 = **按下方条款规则表组合 + 填内容槽位**；若委托 subagent 写提示词，必须把本节条款表与预检清单**全文嵌入**其任务描述。

**前置（强制）— 参考图预检**：写提示词前必须下载查看该图用到的每张参考图，产出**特征清单**：画风媒介、主色配色、构图框架、主体姿态、装饰元素、字体感受；参考图是版式参考时必须拆到**布局结构层**（分栏/卡片/序号样式/装饰位置）。禁止凭标题/正文关键词联想风格。

**每条提示词 = 条款组合 + 内容槽位**（按该图实际带的参考图组合；图片数量 N、每张图是什么内容、哪张图带哪张参考图，完全由拆解提示词与声明驱动，skill 不预设内容类型）：

| 该图带的参考 | 提示词条款 |
|---|---|
| 有参考图（任意图号） | 风格段**逐条复述**该图参考图的预检特征清单，**禁止编造**；换主体不换构图框架（参考图是站姿上半身居中，就不准写侧躺全身） |
| 带多张参考图 | 显式声明每张角色，如「第一张严格还原其形态，第二张仅提供画风」——排前的参考图影响更强 |
| 无参考图的配图（sequential，被封面锚定） | **零风格词、零版式词**（不写色调/画风/色块/布局），只写内容——画风版式由封面锚点自动带 |
| 无参考图且无锚点（parallel，仅显式声明时） | 风格必须来自拆解提示词的显式描述 |

**所有图通用三条**：
1. **反脑补**：参考图中已有的实物/元素严格还原；**不得自行添加参考图中不存在的实物元素**（包装、瓶罐、玩偶等）；提示词提到的元素若参考图中不存在，以参考图为准
2. **禁全局反锚点词**：任何一张图禁止出现「写实/摄影/3D/电商/展台」等画风全局词（复述参考图特征时除外）——它比封面锚点和脚本自动注入的 STYLE_LOCK 都凶
3. **文字强约束**：画面文字严格使用提示词给定字句（脚本已自动前置 TEXT_LOCK）；封面只放主/副标题，细节文字留给对应图

**内容槽位**（AI 填）：主体与动作、标题文字、条目内容、卖点文字等——来自「拆解提示词 + 正文 + 图片数量 N」，按图分配；画质后缀（`8k, high detail` 等）统一追加。

**回填**：把每条提示词写入对应行的「图N提示词」列，并将该行「状态」置为 `提示词已生成`。
（逐行生成并回填，完成后向用户展示几条样例确认风格，用户不满意可调整后再批量。）

> **推荐用脚本取值**（避免手写 JSON 解析）：
> ```bash
> python3 <skill>/scripts/read_cell.py --url "<URL>" --sheet-id "<SID>" --range I2   # 输出纯文本提示词
> ```

### Step 5 — 生成图片（默认 sequential 两段式）

对目标行，确认项目、模型、比例后执行：

**行内模式（默认 sequential，唯一核心概念）**：封面（图 1）先生成 → 封面 assetId 自动作图 2~N 的风格锚点，无需任何提示词表述；仅当拆图提示词明确写「每张图独立/各图互不相关/相互独立」才回退全图并发（无锚点）。每张参考图用在哪张图，必须在拆图提示词显式声明（见「拆图提示词写法约定」），脚本按声明分配到对应图号——全显式、无默认分配，未声明不附加（stderr 提醒）。

> **推荐用脚本**（固化两段式 + 失败重试 + 参考图链路）：
> ```bash
> # 单行生成：--mode 默认 sequential（封面→assetId 锚定配图），一般无需指定
> python3 <skill>/scripts/read_cell.py --url "<URL>" --sheet-id "<SID>" --range I2 > prompts.txt
> python3 <skill>/scripts/read_cell.py --url "<URL>" --sheet-id "<SID>" --range J2 >> prompts.txt
> # ...
> python3 <skill>/scripts/generate_row_images.py --project <projectId> \
>   --model <模型> --ratio <比例> --prompts prompts.txt \
>   [--refs "1:参考图1路径;3:参考图2路径"] --size 2K
> ```
> 输出 JSON：`[{"n":1,"assetId":"..."}, ...]`，失败项 status=failed 带 error、不中断后续；有失败退出码 2。`--refs` 按图号挂参考图：只挂拆图提示词声明过的参考图（全显式）。

> **推荐用脚本（行间并发）**：多行同时处理，默认 10 行并发；每行自动读输入、判模式（默认 sequential）、按声明分配参考图、下载、生成、回填、更新状态：
> ```bash
> python3 <skill>/scripts/run_rows.py --url "<URL>" --sheet-id "<SID>" --rows "2,3,5" \
>   --project <projectId> --model <模型> --ratio <比例> \
>   [--max-workers 10] [--out <dir>] [--dry-run]
> ```
> 每行流程：读图片数量/拆图提示词/各图提示词（列由表头自动定位）→ `judge_mode` 判行内模式（默认 sequential，仅显式整组独立才 parallel）→ 下载参考图到 **tmp 临时目录** `tmp/zovii-refs/<任务ID>/refs/<行>/`（单元格图片/URL；参考图列=列名含「参考图」），并按拆图提示词声明**全显式**分配到图号——未声明的参考图不附加并打印 stderr 提醒，无任何默认分配 → 调 `generate_row_images` → 调 `fillback_images` 回填 → 更新状态列 → **任务结束自动删除参考图临时目录（成败都删，`--keep-tmp` 调试保留）**。**自动维护「耗时(秒)」列**（状态列后一列，表头缺失时自动添加）：记录每行完整流程耗时。输出按行号排序 JSON（含 `elapsed` 字段），失败行退出码 2；清理信息走 stderr 不污染 JSON。
> 🔁 **断点续跑**：每张图生成完成立即写入 `<out>/manifest-row<N>.jsonl`（图号+assetId）；**个别图失败或异常中断后，直接重跑同一命令（同一 `--out`）**——已完成图号自动复用 assetId 跳过生成、只补缺失图号与回填，不重复消耗 credit（脚本结束时也会打印此提示）。
> ⚠️ **并发稳定性**：① `main` 串行预取所有行输入（表头/数量/提示词矩阵/参考图），worker 不重复读表头，避免多行并发读表格触发飞书限流（`99991400`）；② 参考图下载串行化到预取阶段；③ `run_cli` 遇限流自动退避重试；④ 参考图下载 `--output` 用相对路径 + 每行独立 `refs/<行号>/` 目录 + token 前缀唯一文件名。

**手动执行（脚本不可用时兜底）**：

**第一步 — 封面图（图 1）**
```bash
zovii generate-image <projectId> \
  --prompt "<图1提示词>" \
  [--image-input <参考图本地路径>] \
  --model <模型> --aspect-ratio <比例> --size 2K
```
- 图 1 的参考图由拆图提示词显式声明（如「参考图1用于图片1」）才附加，未声明则不附加
- 记录返回的 `assetId`（= 封面 assetId，后续作为风格锚点）

**第二步 — 配图（图 2~N）**
```bash
zovii generate-image <projectId> \
  --prompt "<图N提示词>" \
  --image-input "<封面assetId>[,<该图明示参考图路径>...]" \
  --model <模型> --aspect-ratio <比例> --size 2K
```
- `--image-input` 第一个**固定传封面 assetId**（整组风格锚点），其后按拆图提示词声明追加该图的参考图（本地路径），逗号分隔
- 逐张生成、逐张记录 assetId；等待完成再生成下一张
- 任何一张失败 → 记录失败原因到该行「状态」，继续后续行，最后统一汇报

### Step 6 — 下载图片并回填单元格图片

> **推荐用脚本**（内部处理相对路径约束 + 逐张下载回填 + 结果验证）：
> ```bash
> python3 <skill>/scripts/fillback_images.py --url "<URL>" --sheet-id "<SID>" --row <行号> \
>   --start-col <图1图片列字母> \
>   --assets "<assetId1>:图1-封面.png;<assetId2>:图2.png;..." \
>   --out <out>
> ```
> `--assets` 顺序 = 回填列顺序（M→图1, N→图2 ...）；`--out` 即图片最终所在目录；脚本自动 `cd` 后以相对路径回填；输出每张 localPath + filled 状态，有失败返回退出码 2。

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
| `check_update.py` | skill 自更新检查（本地 VERSION vs GitHub 远端，**三源回退**：raw → fastly.jsdelivr → cdn.jsdelivr） | `[--repo] [--timeout]`（单源超时，默认 10s），退出码 1=有新版 |
| `add_columns.py` | 自动追加图1~N提示词/图片/状态列并初始化状态 | `--url --sheet-id --max-n --row [--dry-run]` |
| `read_cell.py` | 读单元格纯文本（供取提示词） | `--url --sheet-id --range` |
| `generate_row_images.py` | 单行生成，**默认 sequential**（封面先行→assetId 锚定配图；parallel 仅显式传入时生效），带重试；带参考图的图自动注入风格锁定句；**manifest 断点续跑**（`[--manifest]`，每张完成即落盘、重跑复用 assetId） | `--project --model --ratio --prompts [--mode] [--refs] [--cover-ref] [--manifest]` |
| `fillback_images.py` | 下载资产 + 回填单元格图片（自动处理相对路径）+ **读回验证落格** | `--url --sheet-id --row --start-col --assets --out [--dry-run]` |
| `run_rows.py` | **行间并发调度**（默认10行）：每行自动锚点校验/读输入/判模式（默认 sequential）/全显式分配参考图（列名含「参考图」，未声明打印提醒）/生成（内置断点续跑）/回填/状态 | `--url --sheet-id --rows --project --model --ratio [--max-workers] [--out] [--dry-run]` |

通用约定：所有脚本走 `--as user`；`<skill>` 指本 skill 安装目录（未安装时用项目路径）；脚本只读/写飞书表格与 zovii 资产，不执行其它副作用。

---

## 决策规则（铁律）

1. **先问再干**：处理颗粒度、模型、比例三问必须在开始前完成
2. **只单图生成**：一律 `zovii generate-image`，禁止 `batch-generate-image`
3. **默认 sequential，封面必为配图锚点**：封面先生成、assetId 作全部配图风格锚点；仅拆图提示词显式写「每张图独立/各图互不相关」类整组独立声明才回退全图并发（无锚点）
4. **行间并发**：多行独立同时处理，默认并发 10 行（`--max-workers` 可调）；参考图下载按行隔离目录
5. **识别列不猜**：表头含义必须读出来后核对，不按直觉猜列名
6. **状态可追踪、中断真可续跑**：每行状态列全程维护；每张图完成即落盘 `manifest-rowN.jsonl`，重跑同一 `--out` 自动复用已完成 assetId（只补下载回填），不再整批重做
7. **失败不静默**：单张失败记录原因，整批结束统一汇报失败清单
8. **回填用相对路径**：`+cells-set-image` 的 `--image` 只接受当前目录内相对路径，先 `cd` 到图片目录再回填
9. **参考图全显式，无类别**：参考图列=列名含「参考图」；每张参考图用在哪张图由拆图提示词显式声明（参考图列名与目标图号同句），未声明则不参与任何图的生成（stderr 提醒）——**无任何默认分配**
10. **参考图临时化**：参考图先下载到 `tmp/zovii-refs/<任务ID>/` 再上传 zovii；任务结束（无论成败）必删该目录（脚本已内置 finally 清理）；生成图是交付物不在此列
11. **写入前验锚、写入后读回**：`run_rows` 预取时对每行做锚点校验（绝对寻址直读 vs 批量映射值，不一致=行号错位→该行响亮失败、零写入）；`fillback` 每张回填后读回确认 embed 落格。任何校验不过立即报错，绝不静默错装
12. **传图≠风格锁定**：带参考图的图必须显式锚定参考图风格——脚本已自动注入 STYLE_LOCK；手动生成时提示词需三层锚点（显式遵循句 + 风格特征清单 + 反向排除冲突画风），且写词前必须先看参考图

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

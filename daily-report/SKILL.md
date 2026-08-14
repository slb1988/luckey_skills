# 每日日报生成器

## 触发条件

用户说以下任意词时激活此 Skill：
- "写日报"
- "生成日报"
- "daily report"
- "write daily note"

## 输入参数（ARGUMENTS）

调用时可附带飞书日报总结作为参数，格式不限（自由文本、分点、表格均可）。内容通常包含：
- 当日工作时段、参与群聊数
- 主要工作成果分类（性能优化、UI问题、项目管理等）
- 具体技术事项、协作人员、沟通结论

**有参数时**：将飞书内容作为第三路数据源，与 ActivityWatch（时长/行为证据）和 P4（代码变更证据）三路合并，互相补充：
- 飞书提供**工作内容语义**（做了什么、结论是什么）
- AW 提供**时间分配佐证**（花了多久、用了什么工具）
- P4 提供**代码变更记录**（提交了什么、改了哪些文件）

**无参数时**：仅用 AW + P4 数据生成条目。

---

## 工作流

### Step 1 — 确定日期与目标路径

日期：使用 currentDate（系统 context 已注入），或 `date "+%Y-%m-%d"`。

**目标路径不要硬编码**——权威来源是 Daily Notes 插件配置：

```bash
cat luckey/.obsidian/daily-notes.json
# {"folder": "02_notes/daily", "template": "00_meta/templates/daily-note", ...}
```

- 目标文件：`luckey/<folder>/YYYY-MM-DD.md`
- 模板文件：`luckey/<template>.md`

> ⚠️ vault 重构后旧路径（`301 Daily Notes`、`Templates/DailyNoteTemplate.md`）已失效。`luckey/AGENTS.md` 规定 `02_notes/daily` 由 Daily Notes 插件管理、不按年月拆分——路径以插件配置为准。

### Step 2 — 查询 ActivityWatch

要点：
- curl 必须加 `-sL`（AW API 返回 308 重定向，不加 `-L` 会得到空响应）
- bucket 名为 `aw-watcher-window_<hostname>` / `aw-watcher-afk_<hostname>`，hostname 用 `hostname` 命令获取

需要三组数据（**完整可运行的命令见 [references/activitywatch-api.md](references/activitywatch-api.md)**）：
1. 全量 app 总时长聚合（用于 Step 6 表格）
2. 工作相关 app 的 title 明细（duration > 5min，用于 Step 4 条目）
3. AFK `not-afk` 事件分段（用于 Step 5 上下班时间）

**`unknown` app 说明**：AW 无法识别窗口归属时记为 `unknown`，时长常来自 Orca 内嵌 agent 终端/子窗口。保留在表格中并加注，不要静默丢弃，也不要当作有效工作时间证据。

curl 失败时用 Playwright fallback 访问 `http://localhost:5600`（见 references）。

### Step 3 — 采集 P4 提交记录

三个服务器（**详细命令与错误处理见 [references/p4-changelist.md](references/p4-changelist.md)**）：

| 服务器 | 用户 | 说明 |
|--------|------|------|
| 192.168.2.236:1666 | sunlaibing | 公司项目仓库 |
| 192.168.2.13:1666  | admin_sun  | 内网 CICD（Unicode，需 `P4CHARSET=utf8`） |
| 10.77.77.6:1666 | admin | 个人服务器（Unicode，需 `P4CHARSET=utf8`） |

每个服务器：
1. `p4 changes -u <user> -s submitted @YYYY/MM/DD,@YYYY/MM/DD+1`（`-u` 必须放在 `changes` 之后，作全局 flag 不过滤）
2. `p4 describe -s <CL>` 取描述和文件列表

连接失败则跳过并在日记中标注 `（连接失败）`。

### Step 4 — 三路合并，生成 DailySucc 条目

| 数据源 | 作用 |
|--------|------|
| 飞书参数（ARGUMENTS） | 工作内容语义：做了什么、结论是什么 |
| ActivityWatch（Step 2） | 时间佐证：花了多久、用了什么工具 |
| P4 提交（Step 3） | 代码变更：提交了什么、改了哪些文件 |

**合并规则**：

1. **飞书提到、AW 有时长佐证** → 合并为一条，时长写入括号：
   `- [x] **联机调试**：排查 DS 连接问题（UnrealEditor + DSDemoServer 约 63m）`
2. **飞书提到、AW 无对应记录** → 仍写入，不加时长
3. **AW 有记录、飞书未提及** → 按 AW 数据写入（duration > 5min 才记录）
4. **P4 提交** → 合并进对应分类，作为缩进子项（不单独列出）：
   ```
   - [x] **联机调试**：排查 DS 连接问题（约 63m）
     - CL 88565 [主仓库]：修复 DS 连接逻辑（3 文件）
   ```
   服务器简称：`192.168.2.236` → `[主仓库]`，`192.168.2.13` → `[CICD]`，`10.77.77.6` → `[个人]`

**ActivityWatch app 分类参考**（duration > 5min 才记录）：

| 分类 | 识别关键词 |
|------|-----------|
| P4/版本控制 | `p4v.exe`, `BCompare`, `p4` in title |
| 编译/构建 | `devenv.exe` + build/compile, TeamCity, UGS |
| 代码编辑 | `Code.exe`, `devenv.exe`, `rider64.exe` |
| UE 编辑器 | `UnrealEditor.exe`, `DSDemoServer.exe`, `ProjectLungfishGame.exe` |
| 终端/自动化 | `WindowsTerminal.exe`, `Orca.exe`（结合 title 描述具体任务） |
| 沟通协作 | `Feishu.exe`, `Weixin.exe`, 浏览器+会议 |
| 技术研究 | 浏览器 + YouTube/文档/技术博客 title |
| 文档/规划 | `Obsidian.exe`, `notepad++.exe`, 浏览器+文档 |

**排列顺序**：按重要性/时长降序。若 AW 数据不完整，在 DailySucc 末尾注明 `> 数据覆盖时段：HH:MM — HH:MM`。

### Step 5 — 推断上下班时间

对 `aw-watcher-afk_<hostname>` 的 `not-afk` 事件合并连续活跃段（间隔 < 60 分钟视为同一段；脚本见 references/activitywatch-api.md）。

**判断规则**：
- **上班时间**：当天第一个白天 not-afk 段的开始时间（00:00–05:00 的段属前一晚跨午夜活动，不算）
- **下班时间**：最长连续工作段（通常延伸到 18:00–20:00）的结束时间
- 下班后 20:00 之后的零散活跃段视为下班后活动，不计入；跨午夜的段单独注明

**输出格式**（追加在 `## App 使用时长` 表格之后）：

```markdown
## 工作时间

上班：HH:MM　下班：HH:MM
```

### Step 6 — 生成 App 使用时长表格

数据来源：Step 2 的全量 app 聚合。规则：
- 按时长降序；时长 < 2min 忽略
- **排除** `LockApp.exe`（锁屏，非活动时间）
- `unknown` 保留，标注「未识别窗口」并加表注
- 游戏类 app **保留**，分类标注 `🎮 游戏`

分类：🎮 游戏 / 浏览器 / UE 编辑器 / 沟通协作 / 终端自动化 / 代码编辑 / P4版本控制 / 工具 / 文档规划 / 系统。

```markdown
## App 使用时长

| 时长 | 应用 | 分类 |
|-----:|------|------|
| 138m | Hearthstone.exe | 🎮 游戏 |
| 125m | chrome.exe | 浏览器 |
```

### Step 7 — 写入日记文件

目标路径：Step 1 解析出的 `luckey/<folder>/YYYY-MM-DD.md`。

**⚠️ 必须先 Read 目标文件判断状态：**

- **文件不存在**：读取 Step 1 解析出的模板文件，按模板结构 Write 到目标路径。现行模板结构：
  ```markdown
  ---
  id: daily-YYYYMMDD
  ---
  # YYYY-MM-DD
  ## 📥 捕获 Capture / 🔄 InBox 分诊 / 🌱 今日触碰的笔记 ...
  ***
  ## DailySucc
  - 
  ```
  将 `## DailySucc` 下的 `- ` 占位替换为 Step 4 条目，区块末尾追加 `## App 使用时长` 与 `## 工作时间`；其余区块（捕获/分诊/TODO 等）**保持原样，不填内容**。严格保留模板空行、HTML 标签和 dataview 代码块。

- **文件已存在且有内容**：**用 Edit 合并，不 Write 覆盖**——
  - 新数据源的条目融入现有 DailySucc：语义去重、为已有条目补充飞书语义/时长/CL 子项、新事项插为新条目
  - 估算/占位表格用真实 AW 数据替换
  - vault 规则禁止覆盖与当前任务无关的用户改动

### Step 8 — 确认完成

告知用户：写入路径、DailySucc 条数、App 表格条数、上班/下班时间、数据覆盖时段（如有限）。

---
name: daily-report
title: 每日日报生成器
description: 自动查询 ActivityWatch API 汇总今日工作，按 Obsidian 日记模板写入日记文件。触发词：写日报、生成日报、daily report、write daily note。
tags: [Daily-Report, ActivityWatch, Obsidian, Automation, Productivity]
---

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

### Step 1 — 确定日期

```bash
date /t   # Windows
```

或直接使用 `currentDate`（系统 context 中已注入）。目标文件路径：

```
luckey\301 Daily Notes\YYYY-MM-DD.md
```

如文件已存在，询问用户是否覆盖，否则直接 Write。

---

### Step 2 — 查询 ActivityWatch

> **重要**：ActivityWatch API 会返回 308 重定向，curl 必须加 `-L` 跟随重定向，否则返回空响应导致 JSON 解析失败。

**步骤 2a：确认 hostname（用于 bucket 名）**

```bash
hostname
```

**步骤 2b：列出所有 bucket，确认 aw-watcher-window_\<hostname\> 存在**

```bash
# 注意：必须用 -sL（-L 跟随 308 重定向）
curl -sL http://localhost:5600/api/0/buckets/ \
  | python -c "import json,sys; [print(k) for k in json.load(sys.stdin).keys()]"
```

**步骤 2c：查询各 app 总时长（先全量，排除非工作 app）**

```bash
curl -sL "http://localhost:5600/api/0/query/" \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "timeperiods": ["YYYY-MM-DDT00:00:00+08:00/YYYY-MM-DDT23:59:59+08:00"],
    "query": [
      "events = query_bucket(\"aw-watcher-window_<hostname>\");",
      "events = merge_events_by_keys(events, [\"app\"]);",
      "RETURN = sort_by_duration(events);"
    ]
  }' | python -c "
import json, sys
for e in json.load(sys.stdin)[0]:
    mins = int(e['duration'] // 60)
    if mins >= 2:
        print(f'{mins:4d}m  [{e[\"data\"].get(\"app\",\"\")}]')
"
```

**步骤 2d：查询工作相关 app 的详细 title（duration > 5min 才记录）**

```bash
# 常见工作相关 app 列表（可按实际输出调整）
curl -sL "http://localhost:5600/api/0/query/" \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "timeperiods": ["YYYY-MM-DDT00:00:00+08:00/YYYY-MM-DDT23:59:59+08:00"],
    "query": [
      "events = query_bucket(\"aw-watcher-window_<hostname>\");",
      "events = filter_keyvals(events, \"app\", [\"chrome.exe\",\"Code.exe\",\"devenv.exe\",\"p4v.exe\",\"rider64.exe\",\"notepad++.exe\",\"p4merge.exe\",\"BeyondCompare4.exe\",\"UnrealEditor.exe\",\"obsidian.exe\",\"Feishu.exe\",\"WindowsTerminal.exe\",\"GitHubDesktop.exe\",\"RDCMan.exe\",\"UnrealGameSync.exe\"]);",
      "events = merge_events_by_keys(events, [\"app\", \"title\"]);",
      "RETURN = sort_by_duration(events);"
    ]
  }' | python -c "
import json, sys
for e in json.load(sys.stdin)[0]:
    dur = e['duration']
    if dur >= 300:
        app = e['data'].get('app','')
        title = e['data'].get('title','')
        print(f'{int(dur//60):4d}m  [{app}]  {title[:80]}')
"
```

**方式 B：Playwright fallback（curl 仍失败时）**

用 `mcp__playwright__browser_navigate` 访问 `http://localhost:5600`，截图后手动读取 bucket 数据。

参考：`.claude/skills/daily-report/references/activitywatch-api.md`

---

### Step 3 — 采集 P4 提交记录

对三个服务器分别执行查询（详细命令见 `references/p4-changelist.md`）：

| 服务器 | 用户 | 说明 |
|--------|------|------|
| 192.168.2.236:1666 | sunlaibing | 公司项目仓库 |
| 192.168.2.13:1666  | admin_sun  | 内网 CICD（**Unicode 服务器，需加 `P4CHARSET=utf8`**） |
| 10.77.77.6:1666 | admin    | 个人服务器 |

每个服务器执行：
1. `p4 -p <server> changes -u <user> -s submitted @YYYY/MM/DD,@YYYY/MM/DD+1` — 获取当日 CL 列表
2. `p4 -p <server> describe -s <CL>` — 获取每条 CL 的描述和文件列表

> **192.168.2.13 专用命令**（必须带 `P4CHARSET=utf8`，否则报 "Unicode server permits only unicode enabled clients" 并退出）：
> ```bash
> P4CHARSET=utf8 p4 -p 192.168.2.13:1666 -u admin_sun changes -s submitted @YYYY/MM/DD,@YYYY/MM/DD+1
> P4CHARSET=utf8 p4 -p 192.168.2.13:1666 -u admin_sun describe -s <CL>
> ```

按服务器分组，整理为结构化摘要供 Step 4 使用。
若某服务器连接失败，跳过并在日记中标注 `（连接失败）`。

---

### Step 4 — 三路合并，生成 DailySucc 条目

将以下三路数据合并，生成不重复、有实质内容的条目：

| 数据源 | 作用 |
|--------|------|
| 飞书参数（ARGUMENTS） | 工作内容语义：做了什么、讨论了什么、结论是什么 |
| ActivityWatch（Step 2） | 时间佐证：花了多久、用了什么工具 |
| P4 提交（Step 3） | 代码变更：提交了什么、改了哪些文件 |

**合并规则**：

1. **飞书提到、AW 有时长佐证** → 合并为一条，时长写入括号，如：
   ```
   - [x] **联机调试**：排查 DS 连接问题，验证服务器配置（UnrealEditor + DSDemoServer 约 63m）
   ```

2. **飞书提到、AW 无对应记录** → 仍写入，不加时长，如：
   ```
   - [x] **项目管理**：与朱伟杰规划性能检测每日扫描需求，推进联机 bug 修复机制
   ```

3. **AW 有记录、飞书未提及** → 按 AW 数据写入（duration > 5min 才记录），如：
   ```
   - [x] **技术研究**：研究 UE5 Steam 专用服务器联机方案（YouTube 视频约 72m）
   ```

4. **P4 提交** → 合并进对应分类，作为缩进子项列在该分类下（不单独列出）：
   ```
   - [x] **联机调试**：排查 DS 连接问题，验证服务器配置（约 63m）
     - CL 88565 [主仓库]：修复 DS 连接逻辑（3 文件）
     - CL 562 [CICD]：更新部署配置（1 文件）
   ```
   **服务器简称**：`192.168.2.236` → `[主仓库]`，`192.168.2.13` → `[CICD]`，`10.77.77.6` → `[个人]`
   若某 CL 无法归类到现有分类，为其单独创建新分类条目。

**ActivityWatch app 分类参考**（duration > 5min 才记录）：

| 分类 | 识别关键词 |
|------|-----------|
| P4/版本控制 | `p4v.exe`, `P4Merge`, `BeyondCompare`, `p4` in title |
| 编译/构建 | `devenv.exe` + build/compile, TeamCity, UGS |
| 代码编辑 | `Code.exe`, `devenv.exe` + 代码文件名 |
| UE 编辑器 | `UnrealEditor.exe`, `DSDemoServer.exe`, `ProjectLungfishGame.exe` |
| 终端/自动化 | `WindowsTerminal.exe`（结合 title 描述具体任务） |
| 沟通协作 | `Feishu.exe`, `Weixin.exe`, 浏览器+会议 |
| 技术研究 | 浏览器 + YouTube/文档/技术博客 title |
| 文档/规划 | `Obsidian.exe`, `notepad++.exe`, 浏览器+文档 |

**排列顺序**：按重要性/时长降序，有 CL 子项的分类正常穿插排列。

若 AW 数据不完整（如未运行全天），在 DailySucc 末尾注明：
```
> 数据覆盖时段：HH:MM — HH:MM
```

---

### Step 5 — 推断上下班时间

查询 `aw-watcher-afk_<hostname>` 的 `not-afk` 事件，合并连续活跃段（间隔 < 60 分钟视为同一段），推断上下班时间：

```bash
curl -sL "http://localhost:5600/api/0/query/" \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "timeperiods": ["YYYY-MM-DDT00:00:00+08:00/YYYY-MM-DDT23:59:59+08:00"],
    "query": [
      "events = query_bucket(\"aw-watcher-afk_<hostname>\");",
      "events = filter_keyvals(events, \"status\", [\"not-afk\"]);",
      "RETURN = events;"
    ]
  }' | python -c "
import json, sys
from datetime import datetime, timezone, timedelta

tz = timezone(timedelta(hours=8))
events = json.load(sys.stdin)[0]
events.sort(key=lambda e: e['timestamp'])

segments = []
for e in events:
    start = datetime.fromisoformat(e['timestamp'].replace('Z','+00:00')).astimezone(tz)
    end = start + timedelta(seconds=e['duration'])
    if segments and (start - segments[-1][1]).total_seconds() < 3600:
        segments[-1] = (segments[-1][0], max(end, segments[-1][1]))
    else:
        segments.append((start, end))

for s, e in segments:
    dur = int((e - s).total_seconds() // 60)
    print(f'{s.strftime(\"%H:%M\")} - {e.strftime(\"%H:%M\")}  ({dur}m)')
"
```

**判断规则**：
- **上班时间**：第一个 not-afk 段的开始时间
- **下班时间**：找最长的连续工作段（通常从上班时间延伸到傍晚 18:00–20:00），该段的结束时间即为下班时间
- 晚上 20:00 之后的零散活跃段（< 60 分钟）视为下班后活动，不计入下班时间

**输出格式**（追加在 `## App 使用时长` 表格之后）：

```markdown
## 工作时间

上班：HH:MM　下班：HH:MM
```

---

### Step 6 — 生成 App 使用时长表格

在 DailySucc 之后，追加 `## App 使用时长` 区块。

**数据来源**：Step 2c 的全量 app 聚合结果。

**规则**：
- 按时长降序排列
- **排除** `LockApp.exe`（锁屏，非活动时间）
- 时长 < 2min 的条目忽略
- 游戏类 app（如 `Hearthstone.exe`）**保留**，分类标注 `🎮 游戏`

**分类参考**：

| 分类 | 常见 app |
|------|---------|
| 🎮 游戏 | Hearthstone.exe、任何游戏进程 |
| 浏览器 | chrome.exe、msedge.exe |
| UE 编辑器 | UnrealEditor.exe、DSDemoServer.exe、ProjectLungfishGame.exe、DSDemo.exe |
| 沟通协作 | Feishu.exe、Weixin.exe、WeChatAppEx.exe、Outlook.exe |
| 终端/自动化 | WindowsTerminal.exe、cmd.exe |
| 代码编辑 | devenv.exe、Code.exe、notepad++.exe、rider64.exe |
| P4/版本控制 | p4v.exe、p4merge.exe、BeyondCompare4.exe |
| 工具 | RDCMan.exe、GitHubDesktop.exe、UnrealGameSync.exe |
| 文档/规划 | Obsidian.exe、WINWORD.EXE |
| 系统 | explorer.exe、Taskmgr.exe |

**输出格式**：

```markdown
## App 使用时长

| 时长 | 应用 | 分类 |
|-----:|------|------|
| 138m | Hearthstone.exe | 🎮 游戏 |
| 125m | chrome.exe | 浏览器 |
| ...  | ...  | ...  |
```

---

### Step 7 — 写入日记文件

目标路径（固定，不得更改）：

```
luckey\301 Daily Notes\YYYY-MM-DD.md
```

**⚠️ 必须先用 Read 读取目标路径文件，判断文件状态：**

- **文件已存在且有内容**：用 **Edit** 替换 `## DailySucc` 区块占位行，不要 Write 到任何其他路径。
- **文件不存在**：先读取模板 `luckey/Templates/DailyNoteTemplate.md`，按模板结构用 Write 写入目标路径，再将 DailySucc 内容填入。

替换规则：
- `create time:` 后的占位 → 实际日期（`YYYY-MM-DD`）
- `## DailySucc` 下方的占位行（`- `）→ Step 4 生成的条目逐行列出
- `## DailySucc` 区块末尾追加 Step 5 生成的 `## App 使用时长` 表格
- 其余区块（`## 长期目标` / `## 昨日 Review` / `## Delay` / `## TODO` 及子分区）**保持原样，不填内容**

严格保留模板中的空行和 HTML 标签格式。

---

### Step 8 — 确认完成

告知用户：
- 写入路径
- DailySucc 共几条
- App 使用时长表格共几条
- 上班/下班时间
- 数据覆盖时段（如果有限）

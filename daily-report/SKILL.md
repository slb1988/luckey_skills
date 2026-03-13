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
| 116.232.109.35:32768 | admin    | 个人服务器 |

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

### Step 4 — 分析活动，生成 DailySucc 条目

合并 Step 2（ActivityWatch）和 Step 3（P4）的数据，按以下规则生成条目。

**ActivityWatch 数据分类**（每条 duration > 5min 才记录）：

| 分类 | 识别关键词 |
|------|-----------|
| P4/版本控制 | `p4v.exe`, `P4Merge`, `BeyondCompare`, `p4` in title |
| 编译/构建 | `devenv.exe` + build/compile, TeamCity, UGS |
| 代码编辑 | `Code.exe`, `devenv.exe` + 代码文件名 |
| 工具配置 | 安装程序、Settings、配置类窗口 |
| 沟通协作 | 飞书、Outlook、浏览器+会议/meeting |
| 文档/规划 | Obsidian, Notion, Word, 浏览器+文档 |

ActivityWatch 条目格式：
```
- ✅ **[分类]**：[具体描述，30字以内]
```

**P4 数据条目**（来自 Step 3，格式见 `references/p4-changelist.md`）：
```
- ✅ **P4 提交 [服务器名] CL XXXXX**：[描述摘要，30字以内]（涉及 N 个文件）
```

**排列顺序**：ActivityWatch 条目在前，P4 条目在后，P4 按服务器分组相邻排列。

若 AW 数据不完整（如未运行全天），在 DailySucc 末尾注明：
```
> 数据覆盖时段：HH:MM — HH:MM
```

---

### Step 5 — 写入日记文件

**先读取模板文件**，以模板为基准写入日记，避免格式随 Skill 版本漂移：

```bash
# 读取最新模板
Read: luckey/Templates/DailyNoteTemplate.md
```

按模板内容写入，替换规则：
- `{{date}}` → 实际日期（`YYYY-MM-DD`）
- `## DailySucc` 下方的占位行 → Step 4 生成的条目逐行列出
- 其余区块（`## 长期目标` / `## 昨日 Review` / `## Delay` / `## TODO` 及子分区）**保持原样，不填内容**

严格保留模板中的空行和 HTML 标签格式。

---

### Step 6 — 确认完成

告知用户：
- 写入路径
- DailySucc 共几条
- 数据覆盖时段（如果有限）

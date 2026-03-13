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

**方式 A：curl（优先）**

```bash
# 2a. 确认 hostname（用于 bucket 名）
hostname

# 2b. 列出所有 bucket，找 aw-watcher-window_<hostname>
curl -s http://localhost:5600/api/0/buckets

# 2c. 查询今日窗口活动（将 YYYY-MM-DD 和 <hostname> 替换为实际值）
curl -s "http://localhost:5600/api/0/query/" \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "timeperiods": ["YYYY-MM-DDT00:00:00+08:00/YYYY-MM-DDT23:59:59+08:00"],
    "query": [
      "events = query_bucket(\"aw-watcher-window_<hostname>\");",
      "events = filter_keyvals(events, \"app\", [\"chrome.exe\",\"Code.exe\",\"devenv.exe\",\"p4v.exe\",\"rider64.exe\",\"notepad++.exe\"]);",
      "events = merge_events_by_keys(events, [\"app\", \"title\"]);",
      "RETURN = sort_by_duration(events);"
    ]
  }'
```

**方式 B：Playwright fallback（curl 失败时）**

用 `mcp__playwright__browser_navigate` 访问 `http://localhost:5600`，截图后手动读取 bucket 数据。

参考：`.claude/skills/daily-report/references/activitywatch-api.md`

---

### Step 3 — 分析活动，生成 DailySucc 条目

从 ActivityWatch 数据中按以下规则分类（每条 duration > 5min 才记录）：

| 分类 | 识别关键词 |
|------|-----------|
| P4/版本控制 | `p4v.exe`, `P4Merge`, `BeyondCompare`, `p4` in title |
| 编译/构建 | `devenv.exe` + build/compile, TeamCity, UGS |
| 代码编辑 | `Code.exe`, `devenv.exe` + 代码文件名 |
| 工具配置 | 安装程序、Settings、配置类窗口 |
| 沟通协作 | 飞书、Outlook、浏览器+会议/meeting |
| 文档/规划 | Obsidian, Notion, Word, 浏览器+文档 |

输出格式：
```
- ✅ **[分类]**：[具体描述，30字以内]
```

若数据不完整（如 AW 未运行全天），在 DailySucc 末尾注明：
```
> 数据覆盖时段：HH:MM — HH:MM
```

---

### Step 4 — 写入日记文件

按以下模板写入，**严格保留空行和 HTML 标签格式**：

```markdown
create time: YYYY-MM-DD

## 长期目标

## 昨日 Review

## Delay

## TODO

### <font color="#ff0000">重要且紧急</font>
- [
### <font color="#00b0f0">重要不紧急</font>
- [
### <font color="#f79646">不重要紧急</font>
- [
### 不重要不紧急
- [


***

## DailySucc
{Step 3 生成的条目逐行列出}
```

注意：
- `## 长期目标` / `## 昨日 Review` / `## Delay` / `## TODO` 及其子分区**留空**（不填内容）
- TODO 子分区的 `- [` 保持原样（Obsidian checkbox 占位符）
- `***` 上方保留两个空行

---

### Step 5 — 确认完成

告知用户：
- 写入路径
- DailySucc 共几条
- 数据覆盖时段（如果有限）

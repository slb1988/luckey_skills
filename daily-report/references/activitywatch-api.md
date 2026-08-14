# ActivityWatch API 参考

本地 ActivityWatch 实例地址：`http://localhost:5600`

---

## 常用 Endpoints

| Method | URL | 说明 |
|--------|-----|------|
| GET | `/api/0/buckets` | 列出所有 bucket |
| GET | `/api/0/buckets/<bucket_id>/events` | 获取 bucket 的原始事件 |
| POST | `/api/0/query/` | 执行 AQL 查询（推荐） |
| GET | `/api/0/info` | 获取 AW 版本和 hostname |

---

## AQL 查询示例

### 查询今日窗口活动（按 app+title 合并，按时长排序）

```bash
curl -s "http://localhost:5600/api/0/query/" \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "timeperiods": ["2026-03-13T00:00:00+08:00/2026-03-13T23:59:59+08:00"],
    "query": [
      "events = query_bucket(\"aw-watcher-window_HOSTNAME\");",
      "events = merge_events_by_keys(events, [\"app\", \"title\"]);",
      "RETURN = sort_by_duration(events);"
    ]
  }'
```

### 只看特定 app（过滤）

```bash
curl -s "http://localhost:5600/api/0/query/" \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "timeperiods": ["2026-03-13T00:00:00+08:00/2026-03-13T23:59:59+08:00"],
    "query": [
      "events = query_bucket(\"aw-watcher-window_HOSTNAME\");",
      "events = filter_keyvals(events, \"app\", [\"chrome.exe\",\"Code.exe\",\"devenv.exe\",\"p4v.exe\"]);",
      "events = merge_events_by_keys(events, [\"app\", \"title\"]);",
      "RETURN = sort_by_duration(events);"
    ]
  }'
```

### 查询浏览器标签（需要 aw-watcher-web）

```bash
curl -s "http://localhost:5600/api/0/query/" \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "timeperiods": ["2026-03-13T00:00:00+08:00/2026-03-13T23:59:59+08:00"],
    "query": [
      "browser_events = query_bucket(\"aw-watcher-web-chrome\");",
      "browser_events = merge_events_by_keys(browser_events, [\"url\", \"title\"]);",
      "RETURN = sort_by_duration(browser_events);"
    ]
  }'
```

---

## 事件数据结构

```json
[
  {
    "id": 12345,
    "timestamp": "2026-03-13T09:00:00.000000+08:00",
    "duration": 3600.5,
    "data": {
      "app": "devenv.exe",
      "title": "ProjectLungfish - Microsoft Visual Studio"
    }
  }
]
```

- `duration`：秒数（浮点）
- `data.app`：进程名
- `data.title`：窗口标题

---

## 常见 Bucket 名称

| Bucket | 说明 |
|--------|------|
| `aw-watcher-window_<hostname>` | 窗口焦点（主要数据源）|
| `aw-watcher-afk_<hostname>` | AFK/空闲检测 |
| `aw-watcher-web-chrome` | Chrome 浏览器标签 |
| `aw-watcher-web-firefox` | Firefox 浏览器标签 |

获取实际 hostname：
```bash
curl -s http://localhost:5600/api/0/info
```
或
```bash
hostname
```

---

## 日报生成专用查询（可直接运行）

> 以下命令中 `<hostname>` 用 `hostname` 命令输出替换，`YYYY-MM-DD` 替换为目标日期。curl 必须带 `-sL`——AW API 会返回 308 重定向，不加 `-L` 得到空响应导致 JSON 解析失败。

### 1. 全量 app 总时长（用于 App 使用时长表格）

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

### 2. 工作相关 app 的 title 明细（duration > 5min，用于 DailySucc 条目）

```bash
curl -sL "http://localhost:5600/api/0/query/" \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "timeperiods": ["YYYY-MM-DDT00:00:00+08:00/YYYY-MM-DDT23:59:59+08:00"],
    "query": [
      "events = query_bucket(\"aw-watcher-window_<hostname>\");",
      "events = filter_keyvals(events, \"app\", [\"chrome.exe\",\"Code.exe\",\"devenv.exe\",\"p4v.exe\",\"rider64.exe\",\"notepad++.exe\",\"BCompare.exe\",\"UnrealEditor.exe\",\"Obsidian.exe\",\"Feishu.exe\",\"WindowsTerminal.exe\",\"GitHubDesktop.exe\",\"RDCMan.exe\",\"UnrealGameSync.exe\",\"Orca.exe\"]);",
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

### 3. AFK 上下班时间推断（not-afk 分段，间隔 < 60min 合并）

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

### `unknown` app 的含义

AW 无法识别窗口归属时记为 `unknown`。重度使用 Orca 的日子里 `unknown` 常是当天最长条目——Orca 内嵌的 agent 终端/子窗口不产生独立进程名。处理：保留在 App 表格中并加注（如「大概率为 Orca 内嵌终端」），不静默丢弃，也不作为具体工作内容的时长证据。

---

## Playwright Fallback

当 curl 失败时，用 Playwright 访问 ActivityWatch Web UI：

1. 导航到 `http://localhost:5600`
2. 截图查看 Dashboard
3. 导航到 `http://localhost:5600/#/timeline` 查看时间线
4. 或直接访问 API URL 在浏览器中查看 JSON 响应

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

## Playwright Fallback

当 curl 失败时，用 Playwright 访问 ActivityWatch Web UI：

1. 导航到 `http://localhost:5600`
2. 截图查看 Dashboard
3. 导航到 `http://localhost:5600/#/timeline` 查看时间线
4. 或直接访问 API URL 在浏览器中查看 JSON 响应

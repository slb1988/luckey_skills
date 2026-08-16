# Memory Center REST API

- Swagger 文档：`http://<NAS-IP>:8005/docs`（可直接交互式调试）
- 健康检查：`GET http://<NAS-IP>:8005/healthcheck`
- Neo4j Browser：`http://<NAS-IP>:7474`（账号 `neo4j`）

## 端点概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/messages` | 写入消息（异步，返回 202 后排队处理） |
| POST | `/search` | 检索（向量 + 图，返回事实列表） |
| POST | `/get-memory` | 按 group 取记忆 |
| GET | `/episodes/{group_id}?last_n=N` | 查某 group 的 episodes（`last_n` 必填） |
| DELETE | `/group/{group_id}` | 清空某 group |
| POST | `/clear` | 清空全图 |
| GET | `/healthcheck` | 健康检查 |

## 写入记忆（POST /messages）

```bash
curl -X POST http://127.0.0.1:8005/messages -H "Content-Type: application/json" -d '{
  "group_id": "my-agent",
  "messages": [
    {"content": "我叫小明，我住在北京。", "role_type": "user", "role": "小明"}
  ]
}'
```

- 返回 202 只代表「已入队」，实际抽取/写入是异步的（抽取约需 10 秒，补丁已关闭推理模式；embedding 走云端较快）。202 ≠ 入库成功——入库标志是 `/episodes` 返回非空。
- `group_id` 用于隔离不同 agent/用户/会话的记忆，检索时按 group 过滤。原版只允许 `[a-zA-Z0-9_-]`（不能含冒号），补丁已放宽为额外允许 `:`（支持 `project:xxx` 命名空间）。
- `messages` 是数组，可一次传多条；每条字段：`content`（正文）、`role_type`（`user`/`assistant`/`system`）、`role`（角色名，可选）、`timestamp`（可选，默认当前时间）。

## 检索（POST /search）

```bash
curl -X POST http://127.0.0.1:8005/search -H "Content-Type: application/json" \
  -d '{"query":"小明住在哪里？","group_ids":["my-agent"],"num_results":5}'
```

返回示例（`facts` 数组，含事实文本与关系名）：

```json
{
  "facts": [
    {
      "uuid": "3a4b297b-...",
      "name": "LIVES_IN",
      "fact": "小明住在北京",
      "valid_at": "2026-08-15T21:05:50.998245+00:00",
      "invalid_at": null,
      "created_at": "2026-08-15T21:06:05.649893+00:00",
      "expired_at": null
    }
  ]
}
```

## 查 episodes

```bash
curl "http://127.0.0.1:8005/episodes/my-agent?last_n=10"
```

> 不带 `last_n` 会返回 422（`Field required`）。

## 清空

```bash
# 清空单个 group
curl -X DELETE http://127.0.0.1:8005/group/my-agent

# 清空全图（会重建索引）
curl -X POST http://127.0.0.1:8005/clear
```

## 验证示例（端到端）

⚠️ `/healthcheck` 只证明 HTTP 进程活着，不能证明索引管线正常（worker 可能已静默挂掉）。真正的健康标准是「写入 → episode 入库 → 检索出事实」闭环：

```bash
# 1. 写入
curl -s -X POST http://127.0.0.1:8005/messages -H "Content-Type: application/json" \
  -d '{"group_id":"selftest","messages":[{"content":"我叫测试员，我在成都。","role_type":"user","role":"测试员"}]}'

# 2. 等 ~15 秒，确认 episode 真的入库（非空即成功；一直空 = worker 挂了）
curl -s "http://127.0.0.1:8005/episodes/selftest?last_n=10"

# 3. 确认能检索到事实
curl -s -X POST http://127.0.0.1:8005/search -H "Content-Type: application/json" \
  -d '{"query":"测试员住在哪","group_ids":["selftest"],"num_results":5}'

# 4. 清理
curl -s -X DELETE http://127.0.0.1:8005/group/selftest
```

预期：第 2 步返回非空数组，第 3 步 `facts` 里出现「测试员住在成都」。

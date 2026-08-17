# Memory Hub API 实测备忘

服务端仓库的 `docs/API_CONTRACT.md` 是权威契约；本文件记录客户端**实测确认**的契约细节与常用 curl。
权威契约与本文件冲突时以权威契约为准，并更新本文件。

## 变更端点必须带 Idempotency-Key

`POST /v1/files/uploads`、`PUT /v1/sessions/{id}/versions`、`POST /v1/memories` 等写操作要求
`Idempotency-Key` 请求头（≤256 字符）。缺失时返回：

```json
{"error":{"code":"INVALID_ARGUMENT","message":"Idempotency-Key header is required and must be <= 256 chars"}}
```

- 同 key + 相同请求 → 服务端去重（安全重试）；同 key + 不同请求 → `IDEMPOTENCY_CONFLICT`。
- 手写脚本时用**确定性 key**（如 `manual-upload:{kind}:{session_id}:{sha256前16位}`），中断重跑天然幂等；
  内容变化时 sha 变化自动生成新 key，不会冲突。
- GET 请求与 `POST /v1/memories/search` 不需要该头。

## 文件上传通道的字段约束（实测）

| 字段 | 约束 |
|---|---|
| `media_type` | 只接受 `application/json` 或 `application/gzip`（其他值 400 `literal_error`） |
| `compression` | 接受 `none` / `gzip` |
| session 内容 | **必须是合法 JSON 文档**；原始 .jsonl（多行 JSON）被拒：`INVALID_ARGUMENT "session file is not valid JSON"`（trailing garbage） |

- 多行 transcript 需包装成单个 JSON 文档再上传。`scripts/upload_sessions.py` 用
  `agent-session-archive/1` 包裹：`{schema_version, source:{agent,session_id,cwd,transcript_path,format}, event_count, events[]}`，
  紧凑序列化保证同内容同 SHA-256（跨机器幂等）。
- 初始化后未完成 `complete` 的上传会过期，重传需重新初始化。

## 常用接口速查

```bash
HUB_URL=http://10.77.77.6:9287
# 请求头：X-User-Id / X-Agent-Id / X-Project-Id（生产另需 Bearer token；写操作另需 Idempotency-Key）

# 0) 列出已知 project（检索前先确认该用哪个 project scope；返回含 agent_ids 可核对归档归属）
curl -sS "$HUB_URL/v1/projects" -H "X-User-Id: $USER_ID" -H "X-Agent-Id: $AGENT_ID" -H "X-Project-Id: $PROJECT_ID"

# 1) 检索记忆（body 不带 user_id；body 的 agent_id/project_id 必须与请求头一致）
curl -sS -X POST "$HUB_URL/v1/memories/search" -H 'Content-Type: application/json' \
  -H "X-User-Id: $USER_ID" -H "X-Agent-Id: $AGENT_ID" -H "X-Project-Id: $PROJECT_ID" \
  -d '{"schema_version":"memory-search/1","query":"...","agent_id":"...","project_id":"...","limit":10,"session_view":"captured"}'

# 2) 查询记忆索引状态（pending/submitted/indexed/failed）
curl -sS "$HUB_URL/v1/memories/{memory_id}" -H "X-User-Id: $USER_ID" -H "X-Agent-Id: $AGENT_ID" -H "X-Project-Id: $PROJECT_ID"

# 3) 健康检查（dependencies.graphiti 才反映上游连通）
curl -sS "$HUB_URL/health/ready"

# 4) 下载已归档 session 文件（验证归档保真度）
curl -sS "$HUB_URL/v1/files/{file_id}/download" -H "X-User-Id: $USER_ID" -H "X-Agent-Id: $AGENT_ID" -H "X-Project-Id: $PROJECT_ID"
```

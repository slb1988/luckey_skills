# Memory Hub API 实测备忘

服务端仓库的 `docs/API_CONTRACT.md` 是权威契约；本文件记录客户端**实测确认**的契约细节与常用 curl。
权威契约与本文件冲突时以权威契约为准，并更新本文件。

## 端点总览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health/live` | 存活探针 |
| GET | `/health/ready` | 就绪探针（含 graphiti/metadata 依赖） |
| POST | `/v1/files/uploads` | 初始化文件上传（只收元数据 + SHA-256） |
| PUT | `/v1/files/uploads/{upload_id}/content` | 上传 session JSON 原始字节流 |
| POST | `/v1/files/uploads/{upload_id}/complete` | 校验并置为 available |
| GET | `/v1/files/{file_id}` / `/download` | 文件元数据 / 下载 |
| POST | `/v1/sessions` | 由 Hub 分配 session_id |
| PUT | `/v1/sessions/{session_id}/versions` | 提交不可变 session 版本 |
| GET | `/v1/sessions/{session_id}` / `/versions/{v}` | 查询 latest / 确定版本 |
| POST | `/v1/memories` | 写入精炼记忆（返回 202，初始 pending） |
| GET | `/v1/memories/{memory_id}` | 查询索引状态 |
| POST | `/v1/memories/search` | 检索记忆（v1，纯 FTS，无质量门禁） |
| POST | `/v1/memories/search-v2` | 检索记忆（v2，LLM 质量门禁；三端 hook 实际走这个） |
| GET | `/v1/projects` | 列出已知 project（含 memory/session 计数，用于选择检索 scope） |

## 检索：v2 与 v1 的差异（实测）

三端 hook（memory_hook.py / Pi 扩展预热与 memory_search）实际打的是 `POST /v1/memories/search-v2`，
schema `memory-search/2`，请求体固定带 `quality_mode=llm` + `session_view=captured` + `scope_mode=current_project`，
LLM 判分读超时 120s。与 v1 的关键差异：

- **质量门禁**：v2 用 LLM 对候选逐条判分（fail-closed），只返回过门禁的结果，并带审计元数据
  （`retrieval_id` / `policy_version` / quality 摘要：候选数→保留数、min_rating）；v1 是纯 FTS，**无门禁**，返回原始候选。
- **回退方向只有一条路**：仅 v2 返回 404 才回退 v1；**503 / 坏响应绝不回退**（fail-closed，错误原样透传调用方）。
- **结果不可直接对比**：v1 的输出是未过 LLM 门禁的原始 FTS 结果，跟 hook 预热/召回注入的内容是两条链路。
  排查「检索测试结果跟 hook 召回对不上」时，先确认对比的客户端走的是 v2——dashboard 检索测试的后端代理
  （clients.py）2026-09 起已对齐 v2（若 dashboard 仍返回无门禁结果，先查 NAS 部署是否包含该修复）。

## 完整写入流程（顺序固定）

```text
初始化上传 → 上传字节流 → complete 校验 → 提交 SessionVersion → 写精炼 Memory → 等 submitted/indexed
```

1. `POST /v1/files/uploads`：传 `size_bytes`、`sha256`、`media_type`、`compression`，拿 `upload_id` + `file_id`。
2. `PUT /v1/files/uploads/{upload_id}/content`：`--data-binary @file`，原始字节流，不 base64。
3. `POST .../complete`：等 `status: available`。
4. `PUT /v1/sessions/{id}/versions`：首版本 `base_version=null, update_mode=replace`；后续 `base_version=latest, update_mode=append`（文件仍是完整快照）。
5. `POST /v1/memories`：传 `session_id/session_version/file_id` + `scope_type` + `memory_type` + `distilled_content` + `summary`，拿 `memory_id`（状态 `pending`）。
6. `GET /v1/memories/{id}` 轮询直到 `indexed`。

约束详见下文「变更端点必须带 Idempotency-Key」与「文件上传通道的字段约束」。
完整带变量的 curl 示例见服务端仓库 `docs/USAGE.md` 第 7 节。

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
# 2026-08-22 起 Hub(:9287) 与 dashboard(:9288) 都强制 Bearer MEMORY_HUB_API_KEY（enabled outside development），
# 缺失返回 UNAUTHENTICATED；dashboard 报 “requires DASHBOARD_API_KEY” 但用的是同一把 key 值。
# upload_sessions.py 拉 inventory 会自动带 Bearer（传 --api-key 或设置 MEMORY_HUB_API_KEY）。

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

## Memory 索引状态

- `pending`：已可靠落库，尚未投递 Graphiti。
- `submitted`：Graphiti 已接受，等待 episode 可查询确认。
- `indexed`：对应 group 最近 episodes 中已确认该 memory_id。
- `failed`：永久错误或重试耗尽（看 `error_code`）。

## 错误码表

| code | 处理 |
|---|---|
| `UNAUTHENTICATED` | 检查 Bearer token、X-Agent-Id/X-Project-Id |
| `SCOPE_FORBIDDEN` | 资源越权；global 写需受信角色 |
| `RAW_SESSION_CONTENT_FORBIDDEN` | 完整内容改走文件上传通道 |
| `FILE_TOO_LARGE` | 超 100MiB 原始 / 250MiB 解压上限 |
| `FILE_NOT_AVAILABLE` | 先 complete，或上传已过期需重新初始化 |
| `SESSION_REFERENCE_MISMATCH` | session/version/file 不是同一确定版本 |
| `SESSION_VERSION_CONFLICT` | base 不是 latest；拉 latest 重生成快照 |
| `IDEMPOTENCY_CONFLICT` | 同 key 用于不同请求；换新 key |
| `GRAPHITI_UNAVAILABLE` | 检查 `10.77.77.6:8005/healthcheck`；≠空结果 |

所有错误返回 `error.code/message/request_id/retryable/details`，`request_id` 同时出现在 `X-Request-Id` 响应头。

# 误归档 session 清理 Runbook（按 scope 定点删除）

适用场景：客户端误配 project（如 `project:sun`、`project:sunlaibing`），同一批 session 已按正确
project 重传、Hub 上正确副本确认存在，需只删错误 scope 的副本及其衍生数据。

2026-08-29 两次实测：`project:sun`（11 session / 13 version / 7 episode / 140 行 SQLite）与
`project:sunlaibing`（1 session / 1 episode / 11 行）。

## 系统结构（决定删除范围的硬知识）

### 一个 session 在 Hub 元数据里的完整足迹（9 类行，缺一不可）

| 表 | 关联键 | 说明 |
|---|---|---|
| `sessions` | session_id | 主行 |
| `session_versions` | session_id | 每 version 一行，`file_id`=归档快照、`full_file_id`=完整 session 文件 |
| `memories` | session_id | 每 version 一条 session_summary；`graphiti_episode_id` == memory_id |
| `memories_fts` | memory_id | **删除触发器自动同步**，不用手删 |
| `files` | file_id（26 个/11 session 量级） | 快照 + full 各一行 |
| `uploads` | file_id | 上传会话记录，FK 引用 files，必须随删 |
| `intake_reviews` / `extraction_reviews` | memory_id | 审核记录，FK 引用 memories，必须先删 |
| `session_usage_daily` / `session_usage_state` | session_id | 用量统计，FK 引用 sessions |
| `graphiti_cleanup` / `outbox` | session_id / aggregate_id | 通常 0 行，但**必须查**——outbox 未完结事件会让 worker 重启后重建 episode |

### 对象文件两种寻址方式（共享判断的关键坑）

| 资产 | storage_key 形态 | 寻址 |
|---|---|---|
| 归档快照（`agent-session-archive/1` 包装文档） | `objects/<sha前2位>/<sha256>.json.gz` | **内容寻址**，sha 唯一 |
| 完整 session 文件 | `objects/named/<source>/<原始文件名>.json.gz` | **文件名寻址，非内容寻址** |

**named 对象的共享不能只看 sha256**：同一原始 jsonl 重传到不同 project 会产生相同 storage_key，
后上传者覆盖同一物理文件。实测正确副本重传后，named 对象磁盘内容已属正确副本（错误副本 files 行
里的 sha256 与磁盘实际内容已不一致）。因此共享判断要查两遍：

1. `actual_sha256/declared_sha256` 被清单外 files 行引用 → 保留
2. **`storage_key` 被清单外 files 行引用 → 保留**（sha 检查完全查不出这种共享）

两次实测结果一致：sha 寻址快照全部孤儿可删；named 对象全部 key_shared=1 必须保留。

### Graphiti 侧

- episode uuid == memories.memory_id（== graphiti_episode_id）。
- `status='rejected'` 的 memory **没有 episode**（intake 审核拒掉的不会进图谱），删 episode 前以
  `GET /episodes/{group}?last_n=100` 的组内容为准逐一核对。
- 删 episode **不级联**已抽取的实体/边，组内残留 Entity/RELATES_TO 只影响该废弃 scope 的检索，
  默认保留；查看残留用 cypher-ro :8006（`POST /query`，字段名 `cypher`/`params`，Bearer 在
  memory-center `.env` 的 `RO_TOKEN`）。

## 标准流程

1. **停 Hub + worker**（dashboard 只读 BFF 可不停）：按 `data/run/*.pid` 逐个 kill，
   `stop_all.sh` 会把 dashboard 一起停，不想停就手动按 pidfile 停两个。注意确认 :9297
   retrieval-candidate 是独立实验实例（独立 DB），不要碰。
2. **备份**：SQLite 是 WAL 模式，裸 `cp .sqlite3` 会丢 WAL 里的新数据。正确做法：
   `PRAGMA wal_checkpoint(TRUNCATE)` 后用 `sqlite3.Connection.backup()` 另存。
3. **盘点（只读连接 `mode=ro`）**：
   - `SELECT ... WHERE session_id LIKE '<prefix>:%'` 与待删清单**精确比对**（数量、id），
     有清单外内容立即停下报告
   - 检查每个 uuid 是否在正确 project 有 active 副本（`session_id LIKE '%:<uuid>'`）
   - 记录 memory_id（= episode uuid）、file_id、sha256、storage_key、outbox 未完结事件
4. **删除（单事务）**：先 `BEGIN` + 全套 DELETE + 残留复查 + `ROLLBACK` 演练确认行数与盘点一致，
   再原样跑一遍 `COMMIT`。删除顺序（子表先行）：extraction_reviews → intake_reviews → memories →
   session_usage_daily → session_usage_state → session_versions → uploads → sessions → files。
5. **删 Graphiti episode**：`curl -X DELETE http://127.0.0.1:8005/episode/<uuid>`，逐个核对组内容后删。
6. **对象文件**：只删 sha 寻址且 sha+key 双重共享检查都通过的；named 对象有 key_shared 即保留。
7. **组残留**：cypher-ro 查 Entity/边数量，报告后默认保留。
8. **起服务验证**：`start_all.sh` → Hub `/health/ready` 全 true → 抽查正确副本 active 且 memory
   `indexed` → `episodes/{group}` 返回 `[]`。

## 回滚

- SQLite：`cp` 备份文件回 `data/memory-hub.sqlite3`，重启 Hub + worker。
- 误删共享对象文件：客户端 `upload_sessions.py --hook-namespace` 重传原 session 即可重建。

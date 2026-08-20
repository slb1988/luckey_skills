---
name: memory-center
description: Memory Center（Graphiti 时序知识图谱记忆服务）运维与部署指南。记录 QNAP NAS 上 memory-center 的容器架构（Neo4j + Graphiti + 备选 Ollama）、端口、LLM/embedding 端点配置（Kimi 网关 kimi-k3/deepseek-v4-flash (Anthropic 协议) + 百炼 DashScope qwen3.7-text-embedding）、兼容性补丁、关键坑位、运维命令与 REST API 用法。当用户提到 memory-center、graphiti、记忆中心、记忆图谱、记忆服务、Neo4j 记忆，或需要查看状态/重启/备份/排障/重新部署/写入或检索记忆时触发。即使用户只说"memory-center 怎么了""帮我看下记忆服务""记忆图谱挂了"也应触发。
---

# Memory Center (Graphiti 记忆中心)

基于 [Graphiti](https://github.com/getzep/graphiti) 的时序知识图谱记忆服务，运行在 QNAP NAS 的 Docker 中。为 AI agent 提供可查询的长期记忆（实体/关系抽取 + 向量检索 + 时序追踪）。

## 快速信息

| 项目 | 值 |
|------|-----|
| 项目目录 | `/share/Container/memory_center/memory-center/` |
| 编排文件 | `compose.yml` |
| 环境配置 | `.env`（含两把 key：Kimi 网关 LLM key + 百炼 embedding key、Neo4j 密码） |
| 兼容补丁 | `patches/zep_graphiti.py` + `patches/ingest.py` |
| 项目 README | `README.md`（详细文档，优先参考） |

## 参考文档

| 主题 | 文件 |
|------|------|
| 架构 / 目录 / 数据流 / 补丁原理 | [references/architecture.md](references/architecture.md) |
| REST API 用法 | [references/api.md](references/api.md) |
| 运维命令 / 备份 / 重新部署 | [references/operations.md](references/operations.md) |
| 切换 LLM / Embedding provider | [references/provider-switch.md](references/provider-switch.md) |
| 换 embedding 模型后的数据迁移 (re-embed) | [references/reembedding.md](references/reembedding.md) |
| ingest 吞吐瓶颈 / 批量补传实测 / outbox 确认判读 | [references/ingest-performance.md](references/ingest-performance.md) |

## 架构

| 服务 | 容器名 | 镜像 | 端口 | 状态 | 说明 |
|------|--------|------|------|------|------|
| Neo4j | `memory-center-neo4j` | `neo4j:5.26-community` | 7474 (HTTP) / 7687 (Bolt) | 运行中 | 图数据库 |
| Graphiti | `memory-center-graphiti` | `zepai/graphiti:latest` (core 0.22.0) | **8005** → 8000 | 运行中 | REST API + Swagger |
| 只读 Cypher 网关 | `memory-center-cypher-ro` | `zepai/graphiti:latest`（复用镜像，零构建） | **8006** → 8000 | 运行中 | 外部只读查图，Bearer token 认证 |
| Ollama | `memory-center-ollama` | `ollama/ollama:latest` | 11434 | **已停用(未卸载)** | 旧本地 embedding (bge-m3)，备选 |

数据流：Graphiti 调 **Kimi 网关 (kimi-k3 主 / deepseek-v4-flash small，Anthropic 协议)** 做实体/关系抽取 → 调 **百炼 DashScope (qwen3.7-text-embedding)** 生成 1024 维向量 → 写入 Neo4j。

## LLM / Embedding 端点

| 用途 | 端点 | 模型 | key 前缀 |
|------|------|------|---------|
| LLM (主) | `http://10.77.77.4:8600` (Anthropic 协议) | `kimi-k3` | `ik_...` (Kimi 网关) |
| LLM (small) | 同上 | `deepseek-v4-flash` | 同上 |
| Embedding | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.7-text-embedding` | `sk-ws-H...` (百炼) |

- LLM 是 **Anthropic/Claude 协议**网关（`/v1/messages` + `x-api-key` 头），不是 OpenAI；`graph_service/config.py` 只读 `OPENAI_*` 变量名，所以复用它们承载 Anthropic 的 key/base_url。
- 百炼 DashScope key 同时有 LLM 和 embedding，但这里只用它的 embedding。
- `qwen3.7-text-embedding` 默认 **1024 维**，正好匹配 graphiti 0.22.0 硬编码的 `EMBEDDING_DIM=1024`。
- Kimi k3 / deepseek-v4-flash 默认开思考（reasoning），结构化抽取必须 `thinking: disabled` + `tool_choice: any`，否则要么 reasoning token 占满 max_tokens → content 空，要么 `tool_choice 'specified' is incompatible with thinking`。详见 [provider-switch.md](references/provider-switch.md)。

## 目录结构

```
memory-center/
├── compose.yml          # 四容器编排 (ollama 保留但已停用)
├── .env                 # 两把阿里云 key / Neo4j 密码 / RO_TOKEN / embedding 配置
├── cypher-ro/cypher_ro.py  # 只读 Cypher 网关代码（bind mount 进容器）
├── config/neo4j.conf    # Neo4j 内存配置（heap 512m / pagecache 256m）
├── data/neo4j/          # Neo4j 数据
├── data/ollama/         # Ollama 模型 (bge-m3 已拉取，未删除)
├── logs/neo4j/ · logs/graphiti/
├── patches/zep_graphiti.py  # LLM/embedding 端点分离 + 关推理 + group_id 放宽 + 重试 2 次 + LLM 落盘（bind mount）
├── patches/ingest.py        # worker 韧性 + uuid 预建 + episode 上下文注入（bind mount）
├── scripts/llm_stats.py     # LLM 调用日志汇总分析（读 logs/graphiti/llm_calls.jsonl）
└── backup/              # 挂载到 neo4j:/backup
```

## 兼容性补丁（patches/zep_graphiti.py）

官方 `zepai/graphiti:latest` 镜像内置 **graphiti-core 0.22.0**，直接跑有多处问题，补丁解决：

1. **LLM 端点分离（Anthropic 协议）**：`_build_llm_client()` 构造自定义 `GuardedAnthropicClient`（httpx 直连，不依赖 anthropic SDK），显式传 `LLMConfig(api_key/base_url/model)` 指向 Kimi 网关。
2. **embedding 端点分离**：embedder 指向 `EMBEDDING_BASE_URL`（百炼 DashScope），与 LLM 端点独立。
3. **small_model 必须显式指定**：graphiti 的 `small_model` 默认 `gpt-4.1-nano`，非 OpenAI 端点不存在 → 报 `Model not exist`。补丁设为 `deepseek-v4-flash`。
4. **防 schema 描述复制的护栏**（`GuardedAnthropicClient`）：推理模型抽取时容易把字段的 `description`/`title` 原样复制成值（如把 summary 输出成 `{"description":..., "title":..., "type":...}`），导致 Neo4j 写入报 `CypherTypeError`。补丁在 system 消息加护栏提示。
5. **强制关闭思考模式 + tool_choice any**：Kimi k3 / deepseek-v4-flash 默认开 reasoning，reasoning token 占满 `max_tokens=8192` 导致 `content` 为空；且网关 `tool_choice specified` 与 thinking 不兼容。补丁加 `thinking: disabled` + `tool_choice: {'type':'any'}`。
6. **放宽 group_id 校验（允许冒号）**：原版只允许 `[a-zA-Z0-9_-]`，Memory Hub 用 `project:xxx` 命名空间（含 `:`）会抛 `GroupIdValidationError`。补丁 monkeypatch `graphiti_core.graphiti.validate_group_id` 额外放行冒号。
7. **worker 韧性与 uuid 预建**（`patches/ingest.py`）：原版 ingest worker 只捕获 `CancelledError`，任何异常都会让 worker 静默死亡（`/healthcheck` 仍 healthy 但不再处理任何消息）。补丁改为捕获所有异常、打印 traceback 并继续处理后续消息。同时 graphiti 的 `add_episode(uuid=X)` 语义是「更新已有 episode」（X 不存在抛 `NodeNotFoundError`），而 Memory Hub 把自己的 Memory ID 作为 uuid 传入，补丁在调用前若该 uuid 不存在就先预建 episode（MERGE 幂等），使 `episode.uuid == Memory ID` 成立。另将同 uuid 跨 group 重投升级为**搬家语义**：已有 episode 的 group ≠ 请求 group 时先删旧再按新 group 预建（原版更新语义会让 episode 永远留在首个 group，新 group 调用方永远 confirm 不到）。
8. **model_size 分层修复**：上游 Anthropic/Generic client 忽略 `model_size`（写死 `self.model`），small/medium 分层失效。补丁重写 `_generate_response`：small → `deepseek-v4-flash`，medium → `kimi-k3`。
9. **历史上下文去重注入（降本）**：add_episode 每一步都带最近 10 条历史 episode 全文，属性抽取也带，占输入 ~86%。补丁把属性抽取的 `previous_episodes` 置空、历史窗口 10→3。详见 [architecture.md](references/architecture.md)。
10. **LLM 重试收敛为 2 次**：上游 tenacity 写死 `stop_after_attempt(4)` + 退避 `max=120s`，网关 503 时单 job 被拖到 76s+ 仍失败。补丁覆盖 `_generate_response_with_retry`：`stop_after_attempt(2)`、退避 `multiplier=2, min=2, max=10`，快速失败交给上层。
11. **LLM 调用落盘（JSONL）**：每次调用（ok/error/retry）追加到 `logs/graphiti/llm_calls.jsonl`（容器内 `/app/logs/llm_calls.jsonl`）。字段：`ts, status(ok/error/retry), model, size, caller（哪个抽取步骤发起的，如 node_operations.extract_nodes / edge_operations.extract_edges / extract_attributes_from_node）, attempt, latency_ms, http_status, stop_reason, prompt_tokens, completion_tokens, prompt_chars, usage_raw, response_model, episode_uuid, group_id, error, traceback`，以及完整原文：`system, messages, request_params(max_tokens/temperature/tool_choice/tools schema), response(解析后结果), raw_response(网关原始响应)`（episode/group 由 ingest worker 通过 contextvar 注入；设 `LLM_LOG_PAYLOAD=0` 可只记指标不记原文；原文里的 `\uXXXX` 转义已解码为可读中文，仅显示层面处理，LLM 实际收到的仍是转义形式——graphiti 上游拼 prompt 用 json.dumps 默认转义所致）。超 200MB 轮转为 `llm_calls.YYYYMMDD_HHMMSS.jsonl` 归档（**历史记录全部保留不删除**）。可用 `LLM_LOG_PATH` / `LLM_LOG_MAX_BYTES` / `LLM_LOG_PAYLOAD` 环境变量调整。

12. **实体抽取负例护栏（`_ENTITY_GUARD`）**：graphiti 默认 extract_nodes prompt 只要求抽 "significant entities"，无任何"什么不该抽"的约束——commit hash、会话标题、路径、uuid 都会被忠实抽成 Entity 节点，且 hash 每次不同、resolve 去重无法吸收（2026-08-20 噪声事故）。补丁按 `response_model.__name__ == 'ExtractedEntities'` 定向注入负例约束（只影响实体抽取，不影响 summary/edge 步骤），负例含 commit hash、分支引用（`origin/main`，首版护栏漏了它导致重建期间被重抽）、会话标题、路径、uuid、job id 等。结构化调用的 response_model 名单：`ExtractedEntities` / `ExtractedEdges` / `NodeResolutions` / `EdgeDuplicate` / `EntityAttributes_<hash>`（属性抽取，每实体动态生成）。事故全文：`incidents/2026-08-20-entity-extraction-noise.md`。

## LLM 调用复盘 / 监控

```bash
cd /share/Container/memory_center/memory-center

# 汇总（默认全量，含所有时间戳归档文件）
python3 scripts/llm_stats.py

# 只看最近 2 小时
python3 scripts/llm_stats.py --hours 2

# 列出 token 最多的 5 个 episode
python3 scripts/llm_stats.py --episodes 5

# 原始记录（每行一个 JSON）
tail -f logs/graphiti/llm_calls.jsonl

# 找某次失败/重试
grep '"status": "error"' logs/graphiti/llm_calls.jsonl | tail
grep '"status": "retry"' logs/graphiti/llm_calls.jsonl | tail

# 复盘某个 episode 的全部 LLM 调用（含完整 prompt 原文与响应）
grep '<episode_uuid>' logs/graphiti/llm_calls.jsonl

# 提取某次调用的完整 prompt 看内容
python3 -c "
import json
for line in open('logs/graphiti/llm_calls.jsonl'):
    r = json.loads(line)
    if r.get('episode_uuid') == '<episode_uuid>':
        print('='*20, r.get('caller'), r.get('model'))
        print(r.get('system',''))
        for m in r.get('messages') or []: print(f\"[{m['role']}] {m['content'][:2000]}\")
        print('→ response:', json.dumps(r.get('response'), ensure_ascii=False)[:1000])
"
```

> 注意：`logs/graphiti/` 需对容器内 uid 999(app) 可写（已 chmod 777），重建目录后记得重新放权。

补丁通过 compose 的 bind mount 生效，无需重建镜像：
```yaml
volumes:
  - ./patches/zep_graphiti.py:/app/graph_service/zep_graphiti.py:ro
  - ./patches/ingest.py:/app/graph_service/routers/ingest.py:ro
```

> 修改补丁后必须 `docker compose restart graphiti`（bind mount 内容变化不会触发 recreate，需重启进程重新 import）。

## 只读 Cypher 网关（cypher-ro，端口 8006）

给外部/dashboard 提供只读查图能力。**背景**：Neo4j Community 版不支持 RBAC（`GRANT ROLE` 是 Enterprise 功能，`SHOW ROLES`/`GRANT` 均报 `Unsupported administration command`），任何 `CREATE USER` 出来的账号都是**全权限**（实测可 CREATE/DELETE）——所以「建只读账号直连 7687」在社区版做不到，改用本网关做只读强制。

- **只读强制**：所有查询在显式 READ access-mode 事务中执行（`execute_read`），写查询被服务端直接拒（`Neo.ClientError.Statement.AccessMode` → 403）；另有预检拦 `dbms.*`/用户/数据库管理命令；返回上限默认 500 行（最大 2000），查询超时 30s。
- **铁律（修订版）**：外部读图一律走 8006 网关（只读账号 + 只读查询由网关强制）；**写入永远走 Graphiti REST (8005) / Memory Hub**，任何组件不得用 neo4j 管理员账号直连 7687 做写入。7474/7687 仅用于本机运维和 Neo4j Browser 临时看图。
- 实现：复用 `zepai/graphiti:latest` 镜像（自带 python3.12 + fastapi + neo4j driver），零构建；代码 `cypher-ro/cypher_ro.py` bind mount，改代码后 `docker compose restart cypher-ro`。
- 认证：`Authorization: Bearer $RO_TOKEN`（token 在 `.env` 的 `RO_TOKEN`）。

```bash
TOKEN=$(grep -E '^RO_TOKEN=' .env | cut -d= -f2)

# 统计聚合
curl -X POST http://10.77.77.6:8006/query -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cypher":"MATCH (n) RETURN labels(n) AS labels, count(*) AS c"}'

# episode↔entity MENTIONS 联查
curl -X POST http://10.77.77.6:8006/query -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cypher":"MATCH (e:Episodic)-[:MENTIONS]->(n:Entity) RETURN n.name, count(e) AS episodes ORDER BY episodes DESC", "limit": 10}'
```

## 关键坑位

- **删 episode 的官方级联语义（重建图谱的基础）**：`DELETE /episode/{uuid}`（`remove_episode`）会连带删除：① 该 episode 创建的边（`edge.episodes[0] == uuid`）；② 只被该 episode 提及的实体节点；③ episode 本体。被多个 episode 共享的实体/边会保留。因此「删 episode → 重投同一内容」可以干净重建某条记忆的派生映射，配合 episode uuid == Memory ID 可实现整组重放（脚本见 memory-hub `scripts/reingest_group.py`）。**注意级联实测不是 100% 可靠**（出现过 MENTIONS 已空但实体残留的孤儿节点），重建后必须补一次模式扫描清扫。
- **Neo4j Community 版没有 RBAC**：`GRANT ROLE` 等管理命令报 `Unsupported administration command`；`CREATE USER` 可执行但新账号是全权限（实测可写可删），**绝不能**作为「只读账号」对外发放。外部只读访问走 cypher-ro 网关（8006）。
- **Neo4j 管理员用户名必须是 `neo4j`**。`NEO4J_AUTH` 只允许设置 neo4j 的密码，写其他用户名报 `Invalid admin username, it must be neo4j.`。
- **改 Neo4j 密码后要清空 `data/neo4j/`**：数据用旧密码加密，无法登录。
- **`qwen3.7-text-embedding` 只在百炼 DashScope 端点存在**（`sk-ws-...` key）；Kimi 网关/DeepSeek 都不提供 embedding。
- **small_model 默认 gpt-4.1-nano 会报 Model not exist**，已用补丁改成 `deepseek-v4-flash`。
- **Kimi k3 / deepseek-v4-flash 默认开思考（reasoning）**：不显式传 `thinking: disabled` 时，reasoning token 会占满 `max_tokens`，导致 `content` 为空、抽取失败。且网关的 `tool_choice specified` 与 thinking 不兼容，必须用 `tool_choice: any`。补丁已统一处理。
- **group_id 原版不允许冒号（`:`）**：上游 `validate_group_id` 只允许 `[a-zA-Z0-9_-]`，`project:xxx` 会抛 `GroupIdValidationError`。补丁已放宽为额外允许冒号。
- **ingest worker 只捕获 `CancelledError`，其它异常会让它静默挂掉**：某条消息处理失败（非法 group_id、LLM 抽取失败等）后，worker 停止处理后续所有消息，`/episodes` 永远为空，但 `/healthcheck` 仍是 healthy。排查：看日志最后一次 `Got a job` 之后是否还有新记录，长时间没有就说明 worker 已死，需 `docker compose restart graphiti`。补丁已改为捕获所有异常并继续。
- **`add_episode(uuid=X)` 是「更新」语义，X 必须是已存在的 episode**：新消息传入新 uuid（如 Memory Hub 的 Memory ID）会抛 `NodeNotFoundError`，导致该条记忆永远无法入库。补丁在调用前预建同 uuid 的 episode（MERGE 幂等），保证 `episode.uuid == 传入 uuid`。
- **`latest` 标签是旧版**：`zepai/graphiti` 只有 `latest` 和 `0.22.0` 两个可用标签，Docker Hub 未跟进 GitHub 0.29.x。
- **Ollama 已停用但未卸载**：镜像和数据都在，`docker compose start ollama` 可随时切回本地 bge-m3（需同时改 `.env` 的 EMBEDDING_* 指回 `http://ollama:11434/v1`）。
- **换 embedding 模型后必须 re-embed 存量数据**：原始文本（`Episodic.content` / `Entity.name` / `Edge.fact`）已在 Neo4j，但向量空间变了，新旧向量不能混用，需重算向量。见 [reembedding.md](references/reembedding.md)。

## 常用运维命令

```bash
cd /share/Container/memory_center/memory-center

# 状态
docker compose ps

# 启动 / 停止 / 重启
docker compose up -d
docker compose down
docker compose restart graphiti   # 改补丁/.env 后必须 restart

# 停用/恢复 Ollama（备选 embedding）
docker compose stop ollama        # 停用（当前状态）
docker compose start ollama       # 恢复

# 日志
docker compose logs -f graphiti

# 资源占用
docker stats memory-center-neo4j memory-center-graphiti
```

**端口检查**（部署前确认无占用）：
```bash
for p in 8005 8006 7474 7687 11434; do
  (exec 3<>/dev/tcp/127.0.0.1/$p) 2>/dev/null && echo "$p 已占用" || echo "$p 空闲"
done
```

## 直接查 Neo4j

常用查询命令见 [operations.md](references/operations.md)。

## REST API 用法

Swagger：`http://<NAS-IP>:8005/docs`；健康检查：`/healthcheck`；Neo4j Browser：`http://<NAS-IP>:7474`（账号 `neo4j`）。

```bash
# 写入记忆（异步，返回 202 后排队处理，抽取约需 10 秒）
curl -X POST http://127.0.0.1:8005/messages -H "Content-Type: application/json" -d '{
  "group_id": "my-agent",
  "messages": [
    {"content": "我叫小明，我住在北京。", "role_type": "user", "role": "小明"}
  ]
}'

# 检索
curl -X POST http://127.0.0.1:8005/search -H "Content-Type: application/json" \
  -d '{"query":"小明住在哪里？","group_ids":["my-agent"],"num_results":5}'

# 查某 group 的 episodes（last_n 必填）
curl "http://127.0.0.1:8005/episodes/my-agent?last_n=10"

# 清空某 group / 全图
curl -X DELETE http://127.0.0.1:8005/group/my-agent
curl -X POST http://127.0.0.1:8005/clear
```

## 自我验证（端到端）

⚠️ `/healthcheck` 只证明 HTTP 进程活着，**不能**证明索引管线正常（worker 可能已静默挂掉）。完整四步验证见 [api.md 验证示例](references/api.md)。

## 备份与恢复

⚠️ Neo4j Community 版**不支持在线 dump**（报 `The database is in use`），必须停库备份：

```bash
# 离线 dump（停库 → dump → 启动）
docker compose stop neo4j
docker compose run --rm neo4j neo4j-admin database dump neo4j --to-path=/backup
docker compose start neo4j

# 或 tar 整目录快照
docker compose stop neo4j && tar -czf backup/neo4j-$(date +%F).tar.gz data/neo4j && docker compose start neo4j
```

> 原始输入文本已存在 Neo4j（`Episodic.content`），**无需单独备份 input**；换 embedding 模型只需 re-embed，见 [reembedding.md](references/reembedding.md)。

## 从零重新部署（关键步骤）

1. 恢复目录结构 + `compose.yml` + `.env` + `patches/zep_graphiti.py` + `config/neo4j.conf`。
2. `.env` 里配两把 key：`OPENAI_*` 用 Kimi 网关（Anthropic 协议，复用变量名）、`EMBEDDING_*` 用百炼 DashScope；`NEO4J_USER=neo4j`。
3. 检查端口（见上）。
4. `docker compose pull` → `docker compose up -d`。
5. 若要用本地 embedding，`docker compose start ollama` + `docker exec memory-center-ollama ollama pull bge-m3`，并把 `.env` 的 `EMBEDDING_*` 指回 Ollama。
6. 验证（端到端，别只看 healthcheck）：`docker compose ps` healthy；写入一条消息后等 ~15 秒，确认 `/episodes/<group>?last_n=10` 返回非空、`/search` 能返回事实（见 [api.md 验证示例](references/api.md)）。

## 注意事项

- `.env` 含真实密钥（两把阿里云 key、Neo4j 密码），不要在对话中回显完整内容。
- 父目录 `/share/Container/memory_center/` 下旧的 `compose.yml`/`.env` 是历史草稿，正式配置在 `memory-center/` 子目录内。
- 修改 `compose.yml` 或 `.env` 需 **`docker compose up -d`**（recreate 容器才重新注入环境变量；`restart` 只重启进程、env 不变）；修改 `patches/` 需 `docker compose restart graphiti`（bind mount 内容变化需重启进程重新 import）。

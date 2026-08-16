---
name: memory-center
description: Memory Center（Graphiti 时序知识图谱记忆服务）运维与部署指南。记录 QNAP NAS 上 memory-center 的容器架构（Neo4j + Graphiti + 备选 Ollama）、端口、LLM/embedding 端点配置（CodePlan qwen3.8-max + 百炼 DashScope qwen3.7-text-embedding）、兼容性补丁、关键坑位、运维命令与 REST API 用法。当用户提到 memory-center、graphiti、记忆中心、记忆图谱、记忆服务、Neo4j 记忆，或需要查看状态/重启/备份/排障/重新部署/写入或检索记忆时触发。即使用户只说"memory-center 怎么了""帮我看下记忆服务""记忆图谱挂了"也应触发。
---

# Memory Center (Graphiti 记忆中心)

基于 [Graphiti](https://github.com/getzep/graphiti) 的时序知识图谱记忆服务，运行在 QNAP NAS 的 Docker 中。为 AI agent 提供可查询的长期记忆（实体/关系抽取 + 向量检索 + 时序追踪）。

## 快速信息

| 项目 | 值 |
|------|-----|
| 项目目录 | `/share/Container/memory_center/memory-center/` |
| 编排文件 | `compose.yml` |
| 环境配置 | `.env`（含两把阿里云 key、Neo4j 密码） |
| 兼容补丁 | `patches/zep_graphiti.py` |
| 项目 README | `README.md`（详细文档，优先参考） |

## 参考文档

| 主题 | 文件 |
|------|------|
| 架构 / 目录 / 数据流 / 补丁原理 | [references/architecture.md](references/architecture.md) |
| REST API 用法 | [references/api.md](references/api.md) |
| 运维命令 / 备份 / 重新部署 | [references/operations.md](references/operations.md) |
| 切换 LLM / Embedding provider | [references/provider-switch.md](references/provider-switch.md) |
| 换 embedding 模型后的数据迁移 (re-embed) | [references/reembedding.md](references/reembedding.md) |

## 架构

| 服务 | 容器名 | 镜像 | 端口 | 状态 | 说明 |
|------|--------|------|------|------|------|
| Neo4j | `memory-center-neo4j` | `neo4j:5.26-community` | 7474 (HTTP) / 7687 (Bolt) | 运行中 | 图数据库 |
| Graphiti | `memory-center-graphiti` | `zepai/graphiti:latest` (core 0.22.0) | **8005** → 8000 | 运行中 | REST API + Swagger |
| Ollama | `memory-center-ollama` | `ollama/ollama:latest` | 11434 | **已停用(未卸载)** | 旧本地 embedding (bge-m3)，备选 |

数据流：Graphiti 调 **CodePlan (qwen3.8-max)** 做实体/关系抽取 → 调 **百炼 DashScope (qwen3.7-text-embedding)** 生成 1024 维向量 → 写入 Neo4j。

## LLM / Embedding 端点

| 用途 | 端点 | 模型 | key 前缀 |
|------|------|------|---------|
| LLM (主) | `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` | `qwen3.8-max` | `sk-sp-H...` (CodePlan) |
| LLM (small) | 同上 | `deepseek-v4-flash-0731` | 同上 |
| Embedding | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.7-text-embedding` | `sk-ws-H...` (百炼) |

- CodePlan (token-plan) 套餐**只含 LLM，不含 embedding**。
- 百炼 DashScope key 同时有 LLM 和 embedding，但这里只用它的 embedding。
- `qwen3.7-text-embedding` 默认 **1024 维**，正好匹配 graphiti 0.22.0 硬编码的 `EMBEDDING_DIM=1024`。
- 价格：embedding ¥0.5/M tokens（中端云价，个人用≈免费）；LLM 走 CodePlan 套餐。

## 目录结构

```
memory-center/
├── compose.yml          # 三容器编排 (ollama 保留但已停用)
├── .env                 # 两把阿里云 key / Neo4j 密码 / embedding 配置
├── config/neo4j.conf    # Neo4j 内存配置（heap 512m / pagecache 256m）
├── data/neo4j/          # Neo4j 数据
├── data/ollama/         # Ollama 模型 (bge-m3 已拉取，未删除)
├── logs/neo4j/ · logs/graphiti/
├── patches/zep_graphiti.py  # 兼容补丁（bind mount 到容器内）
└── backup/              # 挂载到 neo4j:/backup
```

## 兼容性补丁（patches/zep_graphiti.py）

官方 `zepai/graphiti:latest` 镜像内置 **graphiti-core 0.22.0**，直接跑有三处问题，补丁解决：

1. **LLM 端点分离**：`get_graphiti` 里显式传 `LLMConfig(api_key/base_url/model)` 给 `OpenAIClient`，让 LLM 走 CodePlan。
2. **embedding 端点分离**：embedder 指向 `EMBEDDING_BASE_URL`（百炼 DashScope），与 LLM 端点独立。
3. **small_model 必须显式指定**：graphiti 的 `small_model` 默认 `gpt-4.1-nano`，CodePlan 上不存在 → 报 `Model not exist`。补丁设为 `deepseek-v4-flash-0731`。
4. **防 schema 描述复制的护栏**（`GuardedOpenAIClient`）：推理模型（qwen3.8-max）抽取时容易把字段的 `description`/`title` 原样复制成值（如把 summary 输出成 `{"description":..., "title":..., "type":...}`），导致 Neo4j 写入报 `CypherTypeError`。补丁在 system 消息加护栏提示。

补丁通过 compose 的 bind mount 生效，无需重建镜像：
```yaml
volumes:
  - ./patches/zep_graphiti.py:/app/graph_service/zep_graphiti.py:ro
```

> 修改补丁后必须 `docker compose restart graphiti`（bind mount 内容变化不会触发 recreate，需重启进程重新 import）。

## 关键坑位

- **Neo4j 管理员用户名必须是 `neo4j`**。`NEO4J_AUTH` 只允许设置 neo4j 的密码，写其他用户名报 `Invalid admin username, it must be neo4j.`。
- **改 Neo4j 密码后要清空 `data/neo4j/`**：数据用旧密码加密，无法登录。
- **CodePlan 只含 LLM，不含 embedding**：`/models` 列表里没有任何 embedding 模型，`/embeddings` 一律 `Model not exist`。
- **`qwen3.7-text-embedding` 在 CodePlan 上不存在**，必须在百炼 DashScope 端点用 `sk-ws-...` key 调用。
- **small_model 默认 gpt-4.1-nano 会报 Model not exist**，已用补丁改成 `deepseek-v4-flash-0731`。
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
for p in 8005 7474 7687 11434; do
  (exec 3<>/dev/tcp/127.0.0.1/$p) 2>/dev/null && echo "$p 已占用" || echo "$p 空闲"
done
```

## 直接查 Neo4j

```bash
docker exec memory-center-neo4j cypher-shell -u neo4j -p '<密码>' \
  "MATCH (n:Entity) RETURN n.name, n.group_id;"

docker exec memory-center-neo4j cypher-shell -u neo4j -p '<密码>' \
  "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) RETURN a.name, r.name, b.name;"
```

## REST API 用法

Swagger：`http://<NAS-IP>:8005/docs`；健康检查：`/healthcheck`；Neo4j Browser：`http://<NAS-IP>:7474`（账号 `neo4j`）。

```bash
# 写入记忆（异步，返回 202 后排队处理，qwen3.8-max 抽取约需 1 分钟）
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
2. `.env` 里配两把 key：`OPENAI_*` 用 CodePlan、`EMBEDDING_*` 用百炼 DashScope；`NEO4J_USER=neo4j`。
3. 检查端口（见上）。
4. `docker compose pull` → `docker compose up -d`。
5. 若要用本地 embedding，`docker compose start ollama` + `docker exec memory-center-ollama ollama pull bge-m3`，并把 `.env` 的 `EMBEDDING_*` 指回 Ollama。
6. 验证：`docker compose ps` healthy；写入一条消息后 `/search` 检索。

## 注意事项

- `.env` 含真实密钥（两把阿里云 key、Neo4j 密码），不要在对话中回显完整内容。
- 父目录 `/share/Container/memory_center/` 下旧的 `compose.yml`/`.env` 是历史草稿，正式配置在 `memory-center/` 子目录内。
- 修改 `compose.yml` 需 `docker compose up -d`；修改 `patches/` 或 `.env` 需 `docker compose restart graphiti`。

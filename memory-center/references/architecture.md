# Memory Center 架构详解

## 目录结构

```
memory-center/
├── compose.yml          # 三容器编排（ollama 保留但已停用）
├── .env                 # 两把阿里云 key / Neo4j 密码 / embedding 配置
├── config/neo4j.conf    # Neo4j 内存配置（heap 512m / pagecache 256m）
├── data/neo4j/          # Neo4j 数据
├── data/ollama/         # Ollama 模型（bge-m3，已停用未卸载）
├── logs/neo4j/ · logs/graphiti/
├── patches/zep_graphiti.py  # LLM/embedding 端点分离补丁（bind mount）
└── backup/              # 挂载到 neo4j:/backup
```

## 数据流

```
写入记忆：POST /messages → Graphiti 异步队列 → CodePlan qwen3.8-max（实体/关系抽取）
         → 百炼 DashScope qwen3.7-text-embedding（生成 1024 维向量）→ Neo4j（存节点/边/向量）
检索：   POST /search   → 查询词向量化 → Neo4j 向量相似度 + 图遍历 → 返回事实
```

## 端点分离（为什么需要 patches/）

graphiti 默认 LLM 和 embedding 用**同一个 OpenAI 配置**。本项目两者是不同端点，必须分离：

| 用途 | 端点 | 模型 |
|------|------|------|
| LLM | CodePlan `token-plan.cn-beijing.maas.aliyuncs.com` | `qwen3.8-max`（small: `deepseek-v4-flash-0731`） |
| Embedding | 百炼 `dashscope.aliyuncs.com` | `qwen3.7-text-embedding`（1024 维） |

补丁里 `_build_llm_client()` 构造 `OpenAIClient`，`_build_embedder()` 构造 `OpenAIEmbedder`，分别读 `.env` 的两组变量，在 `_create_client()` 注入 `ZepGraphiti`。

### 补丁处理的三个问题

1. **端点分离** —— LLM 走 CodePlan，embedding 走百炼（见上）。
2. **small_model 默认值失效** —— graphiti 的 `small_model` 默认 `gpt-4.1-nano`，非 OpenAI 端点不存在 → `Model not exist`。补丁显式设为 `deepseek-v4-flash-0731`。
3. **推理模型复制 schema 描述** —— `GuardedOpenAIClient`（继承 `OpenAIClient`）在 system 消息加护栏，防止 qwen3.8-max 把字段 `description` 当值输出（否则 Neo4j 报 `CypherTypeError`）。

### 补丁生效方式

补丁通过 compose 的 bind mount 覆盖容器内文件，无需重建镜像：

```yaml
volumes:
  - ./patches/zep_graphiti.py:/app/graph_service/zep_graphiti.py:ro
environment:
  OPENAI_API_KEY: ${OPENAI_API_KEY}          # LLM (CodePlan)
  OPENAI_BASE_URL: ${OPENAI_BASE_URL}
  MODEL_NAME: ${MODEL_NAME}
  EMBEDDING_BASE_URL: ${EMBEDDING_BASE_URL}  # embedding (百炼)
  EMBEDDING_API_KEY: ${EMBEDDING_API_KEY}
  EMBEDDING_MODEL_NAME: ${EMBEDDING_MODEL_NAME}
```

> 改补丁/.env 后要 `docker compose restart graphiti`（不是 `up -d`）。

## 切换 provider

详见 [provider-switch.md](provider-switch.md)。换 embedding 模型后的数据迁移见 [reembedding.md](reembedding.md)。

## Ollama（已停用，备选）

Ollama 是早期的本地 embedding 方案（bge-m3，1024 维），因吃 1.78GB 内存且 CodePlan 无 embedding 而被百炼 DashScope 取代。镜像和数据仍在，`docker compose start ollama` + 改 `.env` 的 `EMBEDDING_*` 指回 `http://ollama:11434/v1` 即可切回。

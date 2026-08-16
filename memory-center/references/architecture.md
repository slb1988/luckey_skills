# Memory Center 架构详解

## 目录结构

```
memory-center/
├── compose.yml          # 三容器编排
├── .env                 # DeepSeek key / Neo4j 密码 / embedding 配置
├── config/neo4j.conf    # Neo4j 内存配置（heap 512m / pagecache 256m）
├── data/neo4j/          # Neo4j 数据
├── data/ollama/         # Ollama 模型（bge-m3 已拉取，持久化）
├── logs/neo4j/ · logs/graphiti/
├── patches/zep_graphiti.py  # DeepSeek 兼容补丁（bind mount 到容器内）
└── backup/              # 挂载到 neo4j:/backup
```

## 数据流

```
写入记忆：POST /messages → Graphiti 异步队列 → DeepSeek（实体/关系抽取）
         → Ollama bge-m3（生成 1024 维向量）→ Neo4j（存节点/边/向量索引）
检索：   POST /search   → 查询词向量化 → Neo4j 向量相似度 + 图遍历 → 返回事实
```

## 两个核心兼容性补丁（为什么需要 patches/）

官方 `zepai/graphiti:latest` 镜像内置的是 **graphiti-core 0.22.0**，默认客户端与 DeepSeek 有两处不兼容，不补丁则只能启动、无法工作：

### 1. DeepSeek 不支持 `json_schema` 结构化输出

0.22.0 的 `OpenAIClient` 用 `beta.chat.completions.parse`（发送 `response_format={"type":"json_schema"}`），DeepSeek 会返回：

```
This response_format type is unavailable now (HTTP 400)
```

补丁把 LLM 客户端换成 `OpenAIGenericClient`：用 `response_format={"type":"json_object"}`（DeepSeek 支持），并把 pydantic 的 JSON schema 注入到 prompt 里，再自行 `json.loads` 解析结果。

### 2. DeepSeek 没有 `/embeddings` 接口

DeepSeek 的 `POST /embeddings` 返回 404，无法生成向量。补丁把 embedder 指向本地 Ollama 的 OpenAI 兼容接口，模型用 `bge-m3`（1024 维，与 graphiti 默认 `EMBEDDING_DIM=1024` 一致，且支持中文）。

### 补丁生效方式

补丁通过 compose 的 bind mount 覆盖容器内文件，无需重建镜像：

```yaml
# compose.yml 中 graphiti 服务的关键片段
volumes:
  - ./patches/zep_graphiti.py:/app/graph_service/zep_graphiti.py:ro
environment:
  EMBEDDING_BASE_URL: http://ollama:11434/v1
  EMBEDDING_API_KEY: ollama        # 占位，Ollama 不校验
  EMBEDDING_MODEL_NAME: bge-m3
```

`patches/zep_graphiti.py` 里 `_build_llm_client()` 构造 `OpenAIGenericClient`（LLM 走 DeepSeek），`_build_embedder()` 构造 `OpenAIEmbedder`（embedding 走 Ollama），两者在 `_create_client()` 中注入 `ZepGraphiti`。

> 若更换了同时支持 json_schema 和 embeddings 的 provider（如 OpenAI 官方、SiliconFlow 等），理论上可去掉补丁、删掉 Ollama 服务，但需同步改 `compose.yml` 的挂载和 env。

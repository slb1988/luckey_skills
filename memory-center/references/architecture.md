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
写入记忆：POST /messages → Graphiti 异步队列 → CodePlan qwen3.7-max（实体/关系抽取）
         → 百炼 DashScope qwen3.7-text-embedding（生成 1024 维向量）→ Neo4j（存节点/边/向量）
检索：   POST /search   → 查询词向量化 → Neo4j 向量相似度 + 图遍历 → 返回事实
```

## graphiti-core 关键行为（系统属性）

### add_episode 的 uuid 语义：更新，不是创建

`add_episode(uuid=...)` 的 uuid 参数不是「给新 episode 指定 id」，而是「定位要更新的已有 episode」：

| uuid 参数 | 行为 |
|---|---|
| `None` | 新建 episode，uuid 由 `str(uuid4())` 自动生成 |
| 非空 `X` | `EpisodicNode.get_by_uuid(X)` 加载已有 episode 再重跑抽取；`X` 不存在 → 抛 `NodeNotFoundError` |

设计意图：**同 uuid 重复调用 = 幂等更新**（重跑抽取、`MERGE` 覆盖写）。要给新 episode 指定固定 uuid，必须先用相同 uuid 预建 `EpisodicNode` 并 `save()`（`MERGE` 幂等），再调 `add_episode(uuid=X)` 走更新路径——没有「创建并指定 uuid」的直通 API。

### ingest worker：单 task 循环 + 只捕获 CancelledError

worker 是单个 asyncio task 的 `while True` 循环：

```python
while True:
    print("Got a job: ...")   # 在 queue.get() 之前打印
    job = await queue.get()
    await job()
```

- `Got a job` 每次循环都打印（队列空时是「就绪等待」信号）——它是 worker 存活的唯一外部可见标志：提交消息后若长时间不再出现新的 `Got a job`，worker 已死/卡死。
- 循环只捕获 `asyncio.CancelledError`；job 抛任何其它异常 → task 静默结束（`async_worker.task` 持有引用，asyncio 不打印 "Task exception was never retrieved"）。HTTP 服务照常响应，`/healthcheck` 仍 healthy。

### add_episode 抽取管线（顺序）

```
validate_group_id
→ retrieve_previous_episodes（同 group 最近 N 条，作为去重/合并上下文）
→ get_or_create episode
→ extract_nodes（LLM 结构化抽取实体）
→ 并行：resolve_extracted_nodes ＋ extract_edges
→ 并行：resolve_extracted_edges ＋ extract_attributes_from_nodes
→ build_episodic_edges / build_duplicate_of_edges
→ add_nodes_and_edges_bulk（Episodic / Entity / Edge 全部 MERGE 幂等写）
```

> embedding 只作用于实体名与边事实（短文本），不作用于整条 episode 正文——所以长正文不会撞 embedding 输入上限，长正文的瓶颈在 LLM 抽取那步。

## 端点分离（为什么需要 patches/）

graphiti 默认 LLM 和 embedding 用**同一个 OpenAI 配置**。本项目两者是不同端点，必须分离：

| 用途 | 端点 | 模型 |
|------|------|------|
| LLM | CodePlan `token-plan.cn-beijing.maas.aliyuncs.com` | `qwen3.7-max`（small: `deepseek-v4-flash-0731`） |
| Embedding | 百炼 `dashscope.aliyuncs.com` | `qwen3.7-text-embedding`（1024 维） |

补丁里 `_build_llm_client()` 构造 `OpenAIClient`，`_build_embedder()` 构造 `OpenAIEmbedder`，分别读 `.env` 的两组变量，在 `_create_client()` 注入 `ZepGraphiti`。

### 补丁处理的问题

1. **端点分离** —— LLM 走 CodePlan，embedding 走百炼（见上）。
2. **small_model 默认值失效** —— graphiti 的 `small_model` 默认 `gpt-4.1-nano`，非 OpenAI 端点不存在 → `Model not exist`。补丁显式设为 `deepseek-v4-flash-0731`。
3. **推理模型复制 schema 描述** —— `GuardedOpenAIClient`（继承 `OpenAIClient`）在 system 消息加护栏，防止 qwen3.7-max 把字段 `description` 当值输出（否则 Neo4j 报 `CypherTypeError`）。
4. **推理模式必须关闭** —— CodePlan/百炼端点所有模型默认开推理（返回 `reasoning_content`），推理 token 会占满 `max_tokens=8192` 导致 `content` 为空、抽取失败/极慢。补丁在 `_create_structured_completion` / `_create_completion` 里加 `extra_body={'enable_thinking': False}`。
5. **group_id 不允许冒号** —— 上游 `validate_group_id` 只允许 `[a-zA-Z0-9_-]`，`project:xxx` 会抛 `GroupIdValidationError` 并让 ingest worker 静默挂掉（worker 只捕获 `CancelledError`）。补丁 monkeypatch `graphiti_core.graphiti.validate_group_id` 额外放行冒号。
6. **worker 静默死 + uuid 必须是已存在 episode** —— 原版 ingest worker 只捕获 `CancelledError`，任何异常都会让 worker 静默死亡（task 引用未释放，asyncio 不打印）；且 `add_episode(uuid=X)` 是「更新」语义，X 不存在抛 `NodeNotFoundError`。Memory Hub 把自己的 Memory ID 作为 uuid 传入，新记忆必然报错。补丁（`patches/ingest.py`）改为捕获所有异常继续处理，并在调用前预建同 uuid 的 episode。

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

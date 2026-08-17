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
写入记忆：POST /messages → Graphiti 异步队列 → Kimi 网关 kimi-k3(主)/deepseek-v4-flash(small)（实体/关系抽取，Anthropic 协议）
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

### add_episode 的 LLM 调用次数与历史注入（成本结构）

每入库一条消息，LLM 调用 = **3 次 medium + N 次 small（每实体属性）+ M 次 small（边去重，仅当有相关边）**：

| 步骤 | 模型档 | 次数 | prompt 带历史？ |
|------|--------|------|----------------|
| extract_nodes | medium | 1 | 是（10 条历史全文） |
| resolve_extracted_nodes（去重） | medium | 1 | 是 |
| extract_edges | medium | 1 | 是 |
| extract_attributes_from_nodes（属性） | small | N（每实体 1 次） | 是（10 条历史全文） |
| resolve_extracted_edges（边去重） | small | M（仅当有相关边） | 否（只带边 fact） |

`RELEVANT_SCHEMA_LIMIT=10`：add_episode 拉同 group 最近 10 条 episode 全文作
`previous_episodes`，注入除边去重外的每一步。单条历史平均 ~1600 字符、10 条 ≈ 11K token，
被重复注入 3+N 次——这是 LLM 消耗的主要来源（实测占单条记忆输入 token 的 ~86%）。

补丁降本（不砍抽取环节，只减历史重复注入）：
- 属性抽取 `previous_episodes` 置空——属性更新只看当前 episode。
- `RELEVANT_SCHEMA_LIMIT` 10 → 3——去重/消歧上下文最近 3 条足够。

实测单条记忆 prompt 从 ~75K 降到 ~15K（降 ~80%）。

> monkeypatch `graphiti_core.graphiti.RELEVANT_SCHEMA_LIMIT` 只影响 add_episode：graphiti.py 是
> `from graphiti_core.search.search_utils import RELEVANT_SCHEMA_LIMIT`，改 graphiti 模块命名空间
> 里的名字不动 search_utils 内部引用的同名全局常量（search 的 limit 仍是 10）。

## 端点分离（为什么需要 patches/）

graphiti 默认 LLM 和 embedding 用**同一个 OpenAI 配置**。本项目两者是不同端点，必须分离：

| 用途 | 端点 | 模型 |
|------|------|------|
| LLM | Kimi 网关 `10.77.77.4:8600`（Anthropic 协议） | `kimi-k3`（small: `deepseek-v4-flash`） |
| Embedding | 百炼 `dashscope.aliyuncs.com` | `qwen3.7-text-embedding`（1024 维） |

补丁里 `_build_llm_client()` 构造 `GuardedAnthropicClient`（httpx 直连，不依赖 anthropic SDK），`_build_embedder()` 构造 `OpenAIEmbedder`，分别读 `.env` 的两组变量，在 `_create_client()` 注入 `ZepGraphiti`。

### 补丁处理的问题

1. **端点分离** —— LLM 走 Kimi 网关（Anthropic 协议），embedding 走百炼（见上）。
2. **small_model 默认值失效** —— graphiti 的 `small_model` 默认 `gpt-4.1-nano`，非 OpenAI 端点不存在 → `Model not exist`。补丁显式设为 `deepseek-v4-flash`。
3. **推理模型复制 schema 描述** —— `GuardedAnthropicClient` 在 system 消息加护栏，防止模型把字段 `description` 当值输出（否则 Neo4j 报 `CypherTypeError`）。
4. **思考模式必须关闭 + tool_choice 必须 any** —— Kimi k3 / deepseek-v4-flash 默认开思考，reasoning token 占满 `max_tokens` 导致 `content` 为空；且网关 `tool_choice specified` 与 thinking 不兼容。补丁加 `thinking: {'type':'disabled'}` + `tool_choice: {'type':'any'}`。
5. **内置 AnthropicClient 忽略 `model_size` 且不传 base_url** —— 补丁自定义 `GuardedAnthropicClient` 重写 `_generate_response`：`model_size == small` 用 `small_model`（deepseek-v4-flash），否则主模型（kimi-k3）；httpx 直连自定义 base_url。
6. **历史上下文重复注入** —— add_episode 每一步（除边去重）都把最近 10 条历史 episode 全文塞进 prompt，占单条记忆输入 token 的 ~86%。补丁把属性抽取的 `previous_episodes` 置空、历史窗口降到 3（详见上「LLM 调用次数与历史注入」）。
7. **group_id 不允许冒号** —— 上游 `validate_group_id` 只允许 `[a-zA-Z0-9_-]`，`project:xxx` 会抛 `GroupIdValidationError` 并让 ingest worker 静默挂掉（worker 只捕获 `CancelledError`）。补丁 monkeypatch `graphiti_core.graphiti.validate_group_id` 额外放行冒号。
8. **worker 静默死 + uuid 必须是已存在 episode** —— 原版 ingest worker 只捕获 `CancelledError`，任何异常都会让 worker 静默死亡（task 引用未释放，asyncio 不打印）；且 `add_episode(uuid=X)` 是「更新」语义，X 不存在抛 `NodeNotFoundError`。Memory Hub 把自己的 Memory ID 作为 uuid 传入，新记忆必然报错。补丁（`patches/ingest.py`）改为捕获所有异常继续处理，并在调用前预建同 uuid 的 episode。

### 补丁生效方式

补丁通过 compose 的 bind mount 覆盖容器内文件，无需重建镜像：

```yaml
volumes:
  - ./patches/zep_graphiti.py:/app/graph_service/zep_graphiti.py:ro
environment:
  OPENAI_API_KEY: ${OPENAI_API_KEY}          # LLM (Kimi 网关，Anthropic 协议)
  OPENAI_BASE_URL: ${OPENAI_BASE_URL}
  MODEL_NAME: ${MODEL_NAME}
  EMBEDDING_BASE_URL: ${EMBEDDING_BASE_URL}  # embedding (百炼)
  EMBEDDING_API_KEY: ${EMBEDDING_API_KEY}
  EMBEDDING_MODEL_NAME: ${EMBEDDING_MODEL_NAME}
```

> 改 `patches/` 后要 `docker compose restart graphiti`（bind mount 内容变化需重启进程重新 import）；改 `.env` 后要 `docker compose up -d`（recreate 才重新注入环境变量）。

## 切换 provider

详见 [provider-switch.md](provider-switch.md)。换 embedding 模型后的数据迁移见 [reembedding.md](reembedding.md)。

## Ollama（已停用，备选）

Ollama 是早期的本地 embedding 方案（bge-m3，1024 维），因吃 1.78GB 内存且 CodePlan 无 embedding 而被百炼 DashScope 取代。镜像和数据仍在，`docker compose start ollama` + 改 `.env` 的 `EMBEDDING_*` 指回 `http://ollama:11434/v1` 即可切回。

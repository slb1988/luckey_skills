# 切换 LLM / Embedding Provider

memory-center 把 LLM 和 embedding **解耦**成两组独立配置，可以分别切换，互不影响。

## 配置结构（.env + 补丁）

| 用途 | 环境变量 | 当前值 |
|------|---------|--------|
| LLM（主模型） | `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `MODEL_NAME` | CodePlan / `qwen3.7-max` |
| LLM（small 模型） | 补丁里写死的 `small_model` | `deepseek-v4-flash-0731` |
| Embedding | `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL_NAME` | 百炼 DashScope / `qwen3.7-text-embedding` |

`patches/zep_graphiti.py` 里 `_build_llm_client()` 构造 `OpenAIClient`（LLM），`_build_embedder()` 构造 `OpenAIEmbedder`（embedding），两者在 `_create_client()` 注入 `ZepGraphiti`。

## 换 provider 前必须满足的三个硬约束

1. **embedding 必须是 1024 维**。graphiti-core 0.22.0 硬编码 `EMBEDDING_DIM=1024`（`embedder/client.py`）。选非 1024 维模型（如 nomic-embed-text 768 维）必须额外改这个文件。
2. **`small_model` 必须显式指定**。默认 `gpt-4.1-nano` 在任何非 OpenAI 端点上都不存在 → `Model not exist`。补丁已设为 `deepseek-v4-flash-0731`，换端点时同步改成该端点上真实存在的模型。
3. **LLM 端点需支持 json_schema 结构化输出**。补丁用的是原生 `OpenAIClient`（`beta.chat.completions.parse`）。若端点不支持（如 DeepSeek 直连），退回 `OpenAIGenericClient`（json_object + prompt 注入 schema），且要保留护栏（见下）。

## Provider 能力矩阵（实测）

| Provider | 端点 | LLM | json_schema | Embedding |
|---------|------|:---:|:-----------:|:---------:|
| CodePlan (token-plan) | `token-plan.cn-beijing.maas.aliyuncs.com` | ✅ qwen3.7-max 等 | ✅ | ❌ |
| 百炼 DashScope | `dashscope.aliyuncs.com` | ✅ | ✅ | ✅ `qwen3.7-text-embedding`(1024) / `text-embedding-v4` |
| DeepSeek 直连 | `api.deepseek.com` | ✅ | ❌ | ❌ |
| Ollama（本地） | `localhost:11434/v1` | — | — | ✅ `bge-m3`(1024) |

> CodePlan 的 `/models` 列表**不含任何 embedding 模型**，`/embeddings` 一律 `Model not exist`；key 也不能跨端点用（CodePlan key 打到 dashscope 端点报 401）。

## 切换 LLM

1. 改 `.env`：`OPENAI_API_KEY` / `OPENAI_BASE_URL` / `MODEL_NAME`。
2. 改补丁里的 `small_model`（新端点上真实存在的快模型）。
3. 若新端点不支持 json_schema，把 `_build_llm_client` 换成 `OpenAIGenericClient` 并保留 `GuardedOpenAIClient` 的护栏逻辑。
4. `docker compose restart graphiti`（改补丁/.env 必须 restart，不是 `up -d`）。
5. 验证：`POST /messages` 写入一条 → 日志无 `Model not exist` / `CypherTypeError` → Neo4j 出实体。

## 切换 Embedding

1. 改 `.env`：`EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL_NAME`。
2. `docker compose restart graphiti`。
3. **必须重新 embedding 存量数据**（向量空间变了）——见 [reembedding.md](reembedding.md)。

## 护栏：推理模型会复制 schema 描述

qwen3.7-max 等推理模型在结构化抽取时，容易把字段的 `description`/`title` 原样复制成值（如把 `summary` 输出成 `{"description":..., "title":..., "type":...}`），导致 Neo4j 写入报 `CypherTypeError`。补丁的 `GuardedOpenAIClient` 在 system 消息里加护栏提示：

> Field descriptions in the response schema describe what a real value LOOKS LIKE — they are NEVER valid values and must NEVER be copied into any field. If you have no value, set null.

换模型后若再遇到 `CypherTypeError`（值里出现 `Map{... -> Map{description...}}`），优先怀疑这个护栏是否还在生效。

## 关键注意

- 改 `patches/` 或 `.env` → `docker compose restart graphiti`（bind mount 内容变化不触发 recreate，需重启进程重新 import）。
- 改 `compose.yml`（增删服务/挂载/端口）→ `docker compose up -d`。

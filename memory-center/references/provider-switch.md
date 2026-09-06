# 切换 LLM / Embedding Provider

memory-center 把 LLM 和 embedding **解耦**成两组独立配置，可以分别切换，互不影响。

## 配置结构（.env + 补丁）

| 用途 | 环境变量 | 当前值 |
|------|---------|--------|
| LLM（主模型） | `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `MODEL_NAME` | Kimi 网关 / `kimi-k3` |
| LLM（small 模型） | 补丁里写死的 `small_model` | `deepseek-v4-flash` |
| Embedding | `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL_NAME` | 百炼 DashScope / `qwen3.7-text-embedding` |

`patches/zep_graphiti.py` 里 `_build_llm_client()` 构造 `GuardedAnthropicClient`（LLM，Anthropic 协议），`_build_embedder()` 构造 `OpenAIEmbedder`（embedding），两者在 `_create_client()` 注入 `ZepGraphiti`。

> `graph_service/config.py` 只读 `openai_api_key` / `openai_base_url` / `model_name` 三个变量名，所以接 Anthropic 协议时**复用 `OPENAI_*` 变量名承载 key/base_url/model**，改值不改名。

### CodePlan Anthropic 端点与凭据

`https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic` 是阿里云 CodePlan 的 Anthropic Messages 兼容入口；凭阿里云 CodePlan token 即可调用，不需要另有 OpenAI 或 Anthropic 官方账号。

直接接入 Claude Code 时用 `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_MODEL`；Anthropic SDK 通常用 `ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY`（模型由调用参数或应用配置指定）。memory-center 因上游配置读取限制，仍把同一组 base URL/key/model 写入 `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `MODEL_NAME`，不要把两套变量名混用。

## 换 provider 前必须满足的三个硬约束

1. **embedding 必须是 1024 维**。graphiti-core 0.22.0 硬编码 `EMBEDDING_DIM=1024`（`embedder/client.py`）。选非 1024 维模型（如 nomic-embed-text 768 维）必须额外改这个文件。
2. **`small_model` 必须显式指定**。默认 `gpt-4.1-nano` 在任何非 OpenAI 端点上都不存在 → `Model not exist`。补丁已设为 `deepseek-v4-flash`，换端点时同步改成该端点上真实存在的模型。
3. **结构化输出路径要匹配协议**。OpenAI 协议走 `OpenAIClient`（json_schema）或 `OpenAIGenericClient`（json_object）；Anthropic 协议走自定义 `GuardedAnthropicClient`（tool_use）。换端点时先确认协议，再选对应 client（见下「Anthropic 协议网关」）。

## Provider 能力矩阵（实测）

| Provider | 端点 | LLM | json_schema | Embedding |
|---------|------|:---:|:-----------:|:---------:|
| CodePlan (token-plan) | `token-plan.cn-beijing.maas.aliyuncs.com` | ✅ qwen3.7-max 等 | ✅ | ❌ |
| 百炼 DashScope | `dashscope.aliyuncs.com` | ✅ | ✅ | ✅ `qwen3.7-text-embedding`(1024) / `text-embedding-v4` |
| DeepSeek 直连 | `api.deepseek.com` | ✅ | ❌ | ❌ |
| Kimi 网关 | `10.77.77.4:8600` | ✅ kimi-k3 / deepseek-v4-flash 等 | ❌（Anthropic 协议） | ❌ |
| Ollama（本地） | `localhost:11434/v1` | — | — | ✅ `bge-m3`(1024) |

> CodePlan 的 `/models` 列表**不含任何 embedding 模型**，`/embeddings` 一律 `Model not exist`；key 也不能跨端点用（CodePlan key 打到 dashscope 端点报 401）。

## DeepSeek V4 模型体系（2026-08 起）

`api.deepseek.com/models` 只返回两个模型：`deepseek-v4-flash`（快/便宜）和
`deepseek-v4-pro`（强）。`deepseek-chat` 是 `deepseek-v4-flash` 的旧别名（请求 deepseek-chat
返回的 `model` 字段是 deepseek-v4-flash）。

**两个模型默认都开思考（reasoning）**：响应带 `reasoning_content`，reasoning token 计入
`completion_tokens`（`completion_tokens_details.reasoning_tokens`）并会占满 `max_tokens`，
导致 `content` 为空——结构化抽取因此失败/重试。`deepseek-v4-pro` 尤其严重。

必须显式关思考：`extra_body={'thinking': {'type': 'disabled'}}`。`{'type': 'enabled',
'effort': 'low'|'medium'|'high'}` 控制思考等级，但实测 low/high 在短任务下都会占满
max_tokens，结构化抽取**只能 disabled**（不是 low）。

## DeepSeek 直连行为特征（json_object 模式）

DeepSeek API 不支持 json_schema 结构化输出——`response_format=json_schema` 直接返回 400
`This response_format type is unavailable now`。接 DeepSeek 只能走 `OpenAIGenericClient`
的 json_object 模式（schema 注入 prompt）。实测 `deepseek-v4-flash` 在该模式下有三种固定输出形态：

| 输出形态 | 说明 |
|---|---|
| 顶层包裹 `properties` | 输出 `{"properties": {...}}`，而非扁平字段对象（照抄 schema 结构） |
| schema 定义当字段值 | 字段值输出 `{"description":..., "title":..., "type":...}`，而非字符串 |
| JSON 后追加多余文字 | 输出 `{...} 解释文字`，`json.loads` 报 `Extra data` |

> 三种形态都必须由 client 侧容错（解包 `properties` / 删除 schema 定义字段 / `raw_decode`
> 提取第一个完整 JSON），否则字段取不到或 Neo4j 报 `CypherTypeError`。

**`OpenAIGenericClient` 原生忽略 `model_size`**：上游 `_generate_response` 写死 `self.model`，
small/medium 分层在 generic client 路径下失效。补丁重写 `_generate_response` 补上分层：
`model_size == small` → `small_model`（deepseek-v4-flash），否则主模型（deepseek-v4-pro）。

## Anthropic 协议网关（Kimi k3，当前 LLM）

`http://10.77.77.4:8600` 是 **Anthropic/Claude 协议**网关（不是 OpenAI）：`/v1/messages` + `x-api-key` 头。模型列表含 `kimi-k3`、`kimi-k2.7-code`、`deepseek-v4-pro`、`deepseek-v4-flash` 等。

### 内置 AnthropicClient 有三处硬伤，必须自定义 client

graphiti-core 0.22.0 自带 `AnthropicClient`，但直接用于自建网关会失败：

| 缺陷 | 后果 | 补丁做法 |
|---|---|---|
| 不传 `base_url`（写死官方端点） | 请求发到 api.anthropic.com，自建网关不可达 | `GuardedAnthropicClient` 用 httpx 直连自定义 base_url |
| `tool_choice={'type':'tool','name':X}`（specified） | 网关 thinking 开启时报 `tool_choice 'specified' is incompatible with thinking enabled` | 改用 `tool_choice={'type':'any'}` |
| 忽略 `model_size`（永远 `self.model`） | small/medium 分层失效 | 重写 `_generate_response`：small → `small_model`，medium → 主模型 |

### 网关协议特性（实测）

- `kimi-k3` 和 `deepseek-v4-flash` **默认都开思考**，响应含 `thinking` + `text`/`tool_use` 两个 block。
- 结构化抽取必须 **`thinking: disabled` + `tool_choice: any`**：关思考后模型直接返回干净的 `tool_use.input`，无 thinking block，token 更省。
- `tool_choice: specified` 与 thinking 不兼容；`tool_choice: auto` 需要大 `max_tokens` 才稳定。
- 请求需带 `anthropic-version: 2023-06-01` 头。

## 切换 LLM

1. 改 `.env`：`OPENAI_API_KEY` / `OPENAI_BASE_URL` / `MODEL_NAME`（Anthropic 协议也复用这三个变量名）。
2. 改补丁里的 `small_model`（新端点上真实存在的快模型）。
3. 按协议选 client：OpenAI → `OpenAIClient`/`OpenAIGenericClient`；Anthropic → `GuardedAnthropicClient`。护栏逻辑两种 client 都要保留。
4. 改 `.env` 用 `docker compose up -d`（重建容器才会重新读环境变量）；改 `patches/` 用 `docker compose restart graphiti`。
5. 验证：`POST /messages` 写入一条 → 日志无 `Model not exist` / `CypherTypeError` → Neo4j 出实体。

## 切换 Embedding

1. 改 `.env`：`EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL_NAME`。
2. `docker compose up -d`（改 .env 必须 recreate，见「关键注意」）。
3. **必须重新 embedding 存量数据**（向量空间变了）——见 [reembedding.md](reembedding.md)。

## 护栏：推理模型会复制 schema 描述

推理模型（qwen3.7-max、DeepSeek V4、kimi-k3）在结构化抽取时，容易把字段的 `description`/`title` 原样复制成值（如把 `summary` 输出成 `{"description":..., "title":..., "type":...}`），导致 Neo4j 写入报 `CypherTypeError`。补丁的 `GuardedAnthropicClient`（当前 Kimi 网关）在 system 消息里加护栏提示：

> Field descriptions in the response schema describe what a real value LOOKS LIKE — they are NEVER valid values and must NEVER be copied into any field. If you have no value, set null.

换模型后若再遇到 `CypherTypeError`（值里出现 `Map{... -> Map{description...}}`），优先怀疑这个护栏是否还在生效。

## 关键注意

- 改 `patches/` → `docker compose restart graphiti`（bind mount 内容变化不触发 recreate，需重启进程重新 import）。
- 改 `.env` → **`docker compose up -d`**（`restart` 只重启进程，**不重新读环境变量**，容器仍带旧 env；只有 recreate 才注入新 env）。
- 改 `compose.yml`（增删服务/挂载/端口）→ `docker compose up -d`。

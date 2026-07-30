---
name: ragflow
description: |
  RAGFlow 使用与调优参考。在 Claude 需要回答 RAGFlow 使用、配置、检索调优、模型接入、API 问题时触发。
  触发场景：(1) 用户问 RAGFlow 怎么用、如何配置；(2) 检索结果不准、漏答案、答案不全；(3) 配置 LLM/Embedding/Rerank 模型；
  (4) 调整 chunk_method、parser_config、prompt_config、top_k、top_n、similarity_threshold 等；(5) RAGFlow API 调用报错。
  即使用户只是说"ragflow 检索不到""知识库回答不完整""怎么接本地模型""更新 chunk_method 报 405"也应该触发。
  如果任务涉及服务器部署、安装、容器、端口、镜像拉取，优先使用 ragflow-deploy skill。
---

# RAGFlow 使用参考

面向 RAGFlow v0.26+ 的快速参考，覆盖检索调优、模型接入、常见 API 坑点。

## 先决判断

先判断用户问题属于哪一类：

| 问题类型 | 去向 |
|---|---|
| 安装/部署/容器/端口/镜像拉取 | 读 `.claude/skills/ragflow-deploy/SKILL.md` |
| 检索不准/漏答/枚举型问题答不全 | 读 `references/retrieval-tuning.md` |
| LLM/Embedding/Rerank 模型接入 | 读 `references/model-integration.md` |
| API 报错（如 405）、端点形状 | 读 `references/api-notes.md` |

## 核心检索链路（速查）

```
解析 → 分块(chunk_method) → 索引(auto_keywords) → 混合检索(top_k)
  → 重排 → 截断(top_n) → 送入 LLM(prompt_config.keyword)
```

关键参数：

| 参数 | 位置 | 作用 |
|---|---|---|
| `chunk_method` | 文档配置 | `naive` vs `table`，决定块内信噪比 |
| `parser_config.auto_keywords` | 数据集解析配置 | 索引阶段给块打关键词 |
| `prompt_config.keyword` | 聊天助手配置 | 查询阶段扩展用户问题关键词 |
| `top_k` | 聊天助手检索配置 | 进入混合排序的候选数 |
| `top_n` | 聊天助手检索配置 | 最终送入 LLM 的片段数 |
| `similarity_threshold` | 聊天助手检索配置 | 最终相似度硬门槛 |
| `vector_similarity_weight` | 聊天助手检索配置 | 向量相似度权重，默认 0.3 |

> 默认 keyword 权重高（0.7），项目专有名词（如列名）必须命中。

## 常见症状对应表

| 症状 | 优先检查 |
|---|---|
| 专有名词/列名检索不到 | `auto_keywords`、`prompt_config.keyword`、`vector_similarity_weight` |
| "列出所有 XXX" 答不全 | `top_n` 是否过小；`chunk_method` 是否为 `table` |
| 表格行答案混杂无关内容 | `chunk_method` 从 `naive` 改为 `table` |
| 检索得分都低于阈值 | `similarity_threshold` 是否过高 |
| 更新 chunk_method 报 405 | 是否用了批量端点，应改用单文档端点 |

## 模型接入速查

RAGFlow 通过 Provider 接入外部模型。常见组合：

| 能力 | Provider | Base URL 示例 |
|---|---|---|
| LLM | OpenAI-API-Compatible | `http://host:8000/v1` |
| Embedding | Ollama | `http://host:11434` |
| Rerank | GPUStack / Xinference / TEI | `http://host:8002` |

详细配置与排障见 `references/model-integration.md`。

## 输出原则

- 先判断问题是使用/配置还是部署/运维。
- 给出可调参数的组合建议，而不是只调一个。
- 说明"为什么"：混合评分公式、keyword 分层、top_n 截断等。
- 需要服务器信息时，指向 `ragflow-deploy` skill。

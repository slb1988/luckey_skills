---
name: ragflow
description: |
  RAGFlow 使用、检索调优、模型接入、API 排障和 Memory 人工提炼维护参考。在 Claude 需要回答 RAGFlow 使用、配置、检索调优、模型接入、API 或长期记忆问题时触发。
  触发场景：(1) 用户问 RAGFlow 怎么用、如何配置；(2) 检索结果不准、漏答案、答案不全；(3) 配置 LLM/Embedding/Rerank 模型；
  (4) 调整 chunk_method、parser_config、prompt_config、top_k、top_n、similarity_threshold；(5) RAGFlow API 报错；
  (6) 用户说“ragflow remember”“remember memory”“记住”“写进 memory”“更新 ragflow memory”，要求把当前上下文提炼到 RAGFlow Memory。
  Memory 请求必须实际写入、建立写入前基线并重复检索验证，不得只口头确认。即使用户只说“把这点记住”也应触发。
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
| `ragflow remember` / `remember memory` / “记住”并有长期保存意图 | 完整读取并执行 `references/memory-curation.md` |

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
| 目标文档被大量近义行淹没（如问"象蛇"命中一堆"象蛇蛋"） | 文档级 `auto_questions`；别名注入让查询字面词进索引；见 `references/retrieval-tuning.md` |
| 同一文档重解析后排名反而暴跌 | 数据集 `pagerank` 是否改过——旧 chunk 带 `pagerank_fea` 快照加分，见 `references/api-notes.md` |
| 检索得分都低于阈值 | `similarity_threshold` 是否过高 |
| 更新 chunk_method 报 405 | 是否用了批量端点，应改用单文档端点 |
| 大量文档分块数为 0 | 按 `run` 状态分诊（RUNNING 跳过 / FAIL 重触发），见 `references/api-notes.md` |

## 模型接入速查

RAGFlow 通过 Provider 接入外部模型。常见组合：

| 能力 | Provider | Base URL 示例 |
|---|---|---|
| LLM | OpenAI-API-Compatible | `http://host:8000/v1` |
| Embedding | Ollama | `http://host:11434` |
| Rerank | GPUStack / Xinference / TEI | `http://host:8002` |

详细配置与排障见 `references/model-integration.md`。

## Memory 人工维护约定

- 不依赖所有普通对话自动写入；只有用户明确表达长期保存意图时才人工提炼。
- 触发后必须实际调用 Memory API，不要只回复“已记住”。
- 从项目根目录 `.env` 读取 `RAGFLOW_TOKEN`，禁止输出或写入 Token。
- 先将上下文提炼为稳定事实、事件经验或操作步骤，再写入 `ragflow-tips`。
- 写入前保存测试查询的检索基线，写入后等待异步抽取并重复测试。
- 只有新记录能被真实查询召回、内容符合预期时，才报告更新成功。
- 完整步骤、固定 Memory ID 和脚本用法见 `references/memory-curation.md`。

## 输出原则

- 先判断问题是使用/配置、Memory 维护还是部署/运维。
- 给出可调参数的组合建议，而不是只调一个。
- 说明“为什么”：混合评分公式、keyword 分层、top_n 截断等。
- Memory 更新报告必须包含提炼内容、写入前后检索差异及是否通过。
- 需要服务器信息时，指向 `ragflow-deploy` skill。

## 项目知识存放规则（硬性约定，2026-08-07 用户明确）

- **项目知识禁止写进聊天助手的 system prompt**，只能写入 RAGFlow Memory（走 `references/memory-curation.md` 的强制流程）。
- 项目知识 = 具体文档名（如《成员分工安排》）、工种/角色清单、字段术语映射（如 食用效果=扣血）、编号换算规则、版本取舍约定等一切项目专属事实。
- system prompt 只放**通用行为规则**：输出格式、触发词识别、枚举扫描、精确匹配、禁止推测等，不得出现项目专有名词。
- 通用 prompt 的安装脚本：`.claude/scripts/feishu_ragflow_sync/update_chat_person_finding_prompt.py`。
- 发现历史 prompt 中残留项目知识时，应迁出到 Memory 并做检索验证。

# RAGFlow 检索调优

RAGFlow 的检索是 dense + keyword 混合评分，再经过重排和截断。调试漏检或答不全的问题时，需要同时看评分公式、关键词层、截断点和分块策略。

## 混合检索评分

```text
similarity = vector_similarity_weight × vector_similarity
           + (1 - vector_similarity_weight) × term_similarity
           + pagerank_fea              # chunk 级快照加分，见 references/api-notes.md
           + tag_fea 匹配分 × 10        # 命中数据集标签特征时
```

- 默认 `vector_similarity_weight = 0.3`，即 keyword 匹配占 0.7。
- 项目专有名词（如列名 `食用效果`）是强 term 信号，漏掉会把相关数据压到阈值以下。
- API 返回的 `similarity` 可能大于 1（含 pagerank/tag 加分）；比较两个 chunk 的真实混合分，用 `w×vec+(1-w)×term` 手算。

## 词项权重分层（索引字段 ≠ 同权）

rerank 计数时各索引字段按固定倍率计入词项匹配（源码 `rag/nlp/search.py`）：

| 索引字段 | 倍率 | 来源 |
|---|---|---|
| `content_ltks`（正文） | ×1 | 解析产出 |
| `title_tks`（文档名） | ×2 | 文件名分词 |
| `important_kwd` | ×5 | `auto_keywords` 抽取或 chunk API 手设 |
| `question_tks` | ×6 | `auto_questions` 生成的"本块回答什么问题" |

推论：想让某类问法稳定命中，把词放进高倍率字段比堆正文更有效——文档名（×2）、关键词（×5）、自动问题（×6）。

## rerank 模型不是纯重排

`rerank_by_model` 的输出仍是混合分：`tkweight×词项分 + vtweight×rerank模型分 + rank_fea(pagerank/tag)`。
pagerank 等加分贯穿 rerank 前后；rerank 模型本身看不到 pagerank，但最终排序包含它。

## rerank 候选窗：混合分是入场券

rerank 只对混合检索融合后的头部候选（实测约 100 席）重打分；候选窗之外的 chunk 保持原序，rerank 再强也捞不到。
诊断"rerank 为什么不生效"时，先看目标 chunk 的**无 rerank 混合排名**是否进窗，而不是先怀疑 rerank 模型。

## 配置是快照，不是实时继承

- 文档的 `parser_config` 在上传/单独修改时定格，不随数据集配置后续变化；新上传才继承数据集当前值。全库扫描配置离群的文档（如 `auto_keywords=0`、误开 `enable_metadata`）应作为检索异常的例行检查。
- `pagerank_fea` 同理：解析时从数据集 `pagerank` 快照进每个 chunk，改数据集值只影响之后解析的文档（案例见 `references/api-notes.md`）。

## 检索侧与生成侧各司其职

聊天助手 system prompt（含术语映射、同义词规则）只作用于**生成**——它教 LLM 怎么解读 chunk，改变不了任何 chunk 的得分。
让查询字面词进入索引的路径只有三条：正文包含（如源数据别名注入）、`important_kwd`（auto_keywords / chunk API）、`question_tks`（auto_questions）。

## 关键词分两层

| 层级 | 配置键 | 作用域 | 效果 |
|---|---|---|---|
| 索引期 | `parser_config.auto_keywords` | 数据集 | 解析时给每个 chunk 自动提取关键词 |
| 查询期 | `prompt_config.keyword` | 聊天助手 | 用 LLM 把用户问题扩展成加权 term 匹配 |

两层都需要。只开 `auto_keywords` 不会把问题中的关键词注入 term 匹配。

## 三个截断点

1. `top_k`：进入混合池的向量候选数。
2. **rerank 候选窗**（约 100 席，无配置项）：混合融合分头部候选才交给 rerank 模型重打分——见上文"rerank 候选窗"。
3. `top_n`：重排后真正作为 `{knowledge}` 传给 LLM 的候选数。

枚举型问题（如"列出所有带 Debuff 的食物"）对 `top_n` 很敏感；即使检索到了正确行，`top_n` 太小也会丢掉。`similarity_threshold` 是最终 `similarity` 的硬下限。

## 分块策略决定信噪比

| 方法 | 产出 | 风险/收益 |
|---|---|---|
| `naive` | 1024-token 滑动块 | 会把无关表格行合并进一个 chunk，稀释 dense 相关性 |
| `table` | 每行一个 chunk，重复表头 | 每行自包含，枚举查找稳定 |

 heterogeneous sheet 的 Excel 文件，数据行建议用 `table` chunking。

## 调优检查清单

遇到检索问题时，按以下顺序检查：

1. **分块策略**：表格/枚举类数据是否用了 `table`？
2. **索引关键词**：`parser_config.auto_keywords` 是否开启？
3. **查询关键词**：`prompt_config.keyword` 是否开启？
4. **截断参数**：`top_n` 是否足够大？`similarity_threshold` 是否过高？
5. **权重**：`vector_similarity_weight` 是否需要根据数据特征调整？
6. **候选窗**：目标 chunk 的**无 rerank 混合排名**是否进窗（约 100 席）？被大量近义行淹没时，用文档级 `auto_questions`（×6 词项权重）或源数据别名注入把查询字面词送进高倍率索引字段。
7. **快照一致性**：目标文档是否近期重解析过而存量没有？手算 `w×vec+(1-w)×term` 与 API `similarity` 对比，整数级差值 = `pagerank_fea` 快照差（见 `references/api-notes.md`）。

## 更新文档配置

修改 `chunk_method` 必须用单文档端点：

```text
PUT /api/v1/datasets/{dataset_id}/documents/{document_id}
{ "chunk_method": "table" }
```

批量 `PUT /api/v1/datasets/{dataset_id}/documents` 加 `"ids": [...]` 会返回 `405 Method Not Allowed`。

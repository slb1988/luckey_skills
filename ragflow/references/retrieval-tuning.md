# RAGFlow 检索调优

RAGFlow 的检索是 dense + keyword 混合评分，再经过重排和截断。调试漏检或答不全的问题时，需要同时看评分公式、关键词层、截断点和分块策略。

## 混合检索评分

```text
similarity = vector_similarity_weight × vector_similarity
           + (1 - vector_similarity_weight) × term_similarity
```

- 默认 `vector_similarity_weight = 0.3`，即 keyword 匹配占 0.7。
- 项目专有名词（如列名 `食用效果`）是强 term 信号，漏掉会把相关数据压到阈值以下。

## 关键词分两层

| 层级 | 配置键 | 作用域 | 效果 |
|---|---|---|---|
| 索引期 | `parser_config.auto_keywords` | 数据集 | 解析时给每个 chunk 自动提取关键词 |
| 查询期 | `prompt_config.keyword` | 聊天助手 | 用 LLM 把用户问题扩展成加权 term 匹配 |

两层都需要。只开 `auto_keywords` 不会把问题中的关键词注入 term 匹配。

## 两个截断点

1. `top_k`：进入混合池的向量候选数。
2. `top_n`：重排后真正作为 `{knowledge}` 传给 LLM 的候选数。

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

## 更新文档配置

修改 `chunk_method` 必须用单文档端点：

```text
PUT /api/v1/datasets/{dataset_id}/documents/{document_id}
{ "chunk_method": "table" }
```

批量 `PUT /api/v1/datasets/{dataset_id}/documents` 加 `"ids": [...]` 会返回 `405 Method Not Allowed`。

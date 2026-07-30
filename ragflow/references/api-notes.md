# RAGFlow API 注意事项

## 更新文档分块方法

批量端点不支持 `chunk_method` 更新：

```text
PUT /api/v1/datasets/{dataset_id}/documents
{ "ids": ["doc1", "doc2"], "chunk_method": "table" }
```

返回：`405 Method Not Allowed`

应使用单文档端点：

```text
PUT /api/v1/datasets/{dataset_id}/documents/{document_id}
{ "chunk_method": "table" }
```

## chunk_method 选择

| 方法 | 适用 |
|---|---|
| `naive` | 普通文本、连续段落 |
| `table` | Excel/CSV 数据行、枚举查找 |

切换 chunk_method 后需要重新解析文档。

## 混合评分公式

```text
similarity = vector_similarity_weight × vector_similarity
           + (1 - vector_similarity_weight) × term_similarity
```

- 默认 `vector_similarity_weight = 0.3`。
- `similarity_threshold` 是最终 `similarity` 的硬门槛。

## 关键词配置层级

- 索引期：`parser_config.auto_keywords`（数据集级）
- 查询期：`prompt_config.keyword`（聊天助手级）

两层独立，缺一不可。

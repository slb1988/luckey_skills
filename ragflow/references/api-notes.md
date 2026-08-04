# RAGFlow API 注意事项

## 启动/停止解析（v0.20+，含 v0.26）

- **启动**：`POST /api/v1/datasets/{dataset_id}/chunks`，body 只需 `{"document_ids": [...]}`
- **停止**：`DELETE /api/v1/datasets/{dataset_id}/chunks`，body `{"document_ids": [...]}`
- **坑**：旧版写法 `POST .../chunks {"run": "0"}` 不再表示停止——`run` 字段被忽略，一律按"启动解析"处理。对 RUNNING 中的文档调用会报 `102 Can't parse document that is currently being processed`。停止必须用 `DELETE`。
- 卡住的 RUNNING 文档（`progress_msg` 长期显示 `N tasks are ahead in the queue`、chunk=0）修复流程：`DELETE` 停止 → `POST` 重新触发。参考脚本 `.claude/scripts/ragflow_fix_stuck_parse.py`。

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

## parser_config 超限（101 错误）

报错：`Parser config exceeds size limit (max 65,535 characters)`。

- 65,535 是 RAGFlow 应用层写死的校验，与 MySQL 列类型无关（v0.26+ 的 `parser_config` 列已是 LONGTEXT）。
- 常见根因：开启元数据（`enable_metadata`）后，文档正文被当成字段名灌进 `parser_config.field_map`（每个文档一份全量副本），或 `table_column_names` 无限累积。**不是** GraphRAG/RAPTOR prompt 导致（这些不会全文入库）。
- `field_map` 在数据集和文档的 PUT API 里都是只读派生字段（`Extra inputs are not permitted`），无法通过 API 清除，只能改库：

```sql
UPDATE document SET parser_config=JSON_REMOVE(parser_config,'$.field_map','$.table_column_names') WHERE kb_id='<dataset_id>';
UPDATE knowledgebase SET parser_config=JSON_REMOVE(parser_config,'$.field_map','$.table_column_names') WHERE id='<dataset_id>';
```

- bash 双引号内写 `mysql -e` 时，`$.` 需转义为 `\$.`；heredoc 结束符必须顶格。
- 清理后若不关闭元数据功能，重新解析可能复发（2026-08 cyancook 实例验证）。

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

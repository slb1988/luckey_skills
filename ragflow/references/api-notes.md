# RAGFlow API 注意事项

## 启动/停止解析（v0.20+，含 v0.26）

- **启动**：`POST /api/v1/datasets/{dataset_id}/chunks`，body 只需 `{"document_ids": [...]}`
- **停止**：`DELETE /api/v1/datasets/{dataset_id}/chunks`，body `{"document_ids": [...]}`
- **坑**：旧版写法 `POST .../chunks {"run": "0"}` 不再表示停止——`run` 字段被忽略，一律按"启动解析"处理。对 RUNNING 中的文档调用会报 `102 Can't parse document that is currently being processed`。停止必须用 `DELETE`。
- 卡住的 RUNNING 文档（`progress_msg` 长期显示 `N tasks are ahead in the queue`、chunk=0）修复流程：`DELETE` 停止 → `POST` 重新触发。参考脚本 `.claude/scripts/ragflow_fix_stuck_parse.py`。
- **根因（2026-08-05 cyancook 实例验证）**：一批任务入队后 valkey/redis 或 task executor 重启，Redis 队列条目丢失，但 MySQL 里文档状态仍停在 RUNNING + 队首，永远不会被消费。判别方法：同库新触发的任务能正常跑（executor 活着），而老任务 `process_begin_at` 停留在同一历史时刻、progress 接近 0——即"假 RUNNING"。批量修复时只处理 `RUNNING && chunk_count==0 && progress_msg 含 ahead in the queue` 的文档，别误伤 FAIL 的和真正在跑的。
- **2026-08-06 复发变体**：84 篇卡住文档显示的是 `0 tasks are ahead in the queue`（队首位置 0 但无人消费），且有一篇大文档（文本总表.xlsx）所有 Page 子任务日志均显示 `Task done`，文档级状态却停在 RUNNING、progress 不更新——说明队列条目和最终状态回写一起丢了（executor 空闲数小时）。修复相同；对这种"子任务全 done、状态假 RUNNING、chunk>0"的文档**只 DELETE 停止、不要重触发**（块已索引，重触发会重复解析）。注意脚本按 `chunk>0 且无 ahead` 启发式会把它误判为"真实在跑"，需单独处理。

## 零分块文档（chunk_count=0）排查与重触发

列表端点 `GET /api/v1/datasets/{id}/documents?page=N&page_size=100`（结果在 `data.docs`）每篇文档带三个可用于分诊的字段：

| 字段 | 取值 | 含义 |
|---|---|---|
| `chunk_count` | 0 | 无分块（解析失败 / 正在解析 / 内容为空） |
| `run` | `UNSTART` / `RUNNING` / `DONE` / `FAIL` | 解析任务状态 |
| `progress` | `-1.0` = FAIL，`1.0` = DONE，中间值 = 进行中 | 解析进度 |

`chunk_count=0` 按 `run` 分三类处理：

| `run` | 处置 |
|---|---|
| `RUNNING` | **跳过**——正在排队/解析，重复 POST 会报 102 |
| `FAIL` | 重新触发：`POST .../chunks {"document_ids": [...]}`，建议每批 ≤32 篇、批间隔 ~1s，避免瞬时压满任务队列 |
| `DONE` 且 chunk=0 | 多为内容为空或解析无产出（如空 Excel）；重触发无害但通常仍是 0，重试后仍失败的应单独列查文件本身 |

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

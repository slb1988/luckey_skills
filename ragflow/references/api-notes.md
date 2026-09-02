# RAGFlow API 注意事项

## 启动/停止解析（v0.20+，含 v0.26）

- **启动**：`POST /api/v1/datasets/{dataset_id}/chunks`，body 只需 `{"document_ids": [...]}`
- **停止**：`DELETE /api/v1/datasets/{dataset_id}/chunks`，body `{"document_ids": [...]}`
- **坑**：旧版写法 `POST .../chunks {"run": "0"}` 不再表示停止——`run` 字段被忽略，一律按"启动解析"处理。对 RUNNING 中的文档调用会报 `102 Can't parse document that is currently being processed`。停止必须用 `DELETE`。
- 卡住的 RUNNING 文档（`progress_msg` 长期显示 `N tasks are ahead in the queue`、chunk=0）修复流程：`DELETE` 停止 → `POST` 重新触发。参考脚本 `.claude/scripts/ragflow_fix_stuck_parse.py`。
- **根因（2026-08-05 cyancook 实例验证）**：一批任务入队后 valkey/redis 或 task executor 重启，Redis 队列条目丢失，但 MySQL 里文档状态仍停在 RUNNING + 队首，永远不会被消费。判别方法：同库新触发的任务能正常跑（executor 活着），而老任务 `process_begin_at` 停留在同一历史时刻、progress 接近 0——即"假 RUNNING"。批量修复时只处理 `RUNNING && chunk_count==0 && progress_msg 含 ahead in the queue` 的文档，别误伤 FAIL 的和真正在跑的。
- **2026-08-06 复发变体**：84 篇卡住文档显示的是 `0 tasks are ahead in the queue`（队首位置 0 但无人消费），且有一篇大文档（文本总表.xlsx）所有 Page 子任务日志均显示 `Task done`，文档级状态却停在 RUNNING、progress 不更新——说明队列条目和最终状态回写一起丢了（executor 空闲数小时）。修复相同；对这种"子任务全 done、状态假 RUNNING、chunk>0"的文档**只 DELETE 停止、不要重触发**（块已索引，重触发会重复解析）。注意脚本按 `chunk>0 且无 ahead` 启发式会把它误判为"真实在跑"，需单独处理。
- **2026-09-02 硬僵尸变体（API 失效，需直接改库）**：57 篇大 xlsx 假 RUNNING 35 天，DELETE 报 `Can't stop parsing document that has not started or already completed`（服务端找不到活任务），POST 又报 `Can't parse document that is currently being processed`——双向锁死。且 PUT 改 chunk_method 会重置 progress 但**不改 run**；POST 失败时还会把 run 重新写成 RUNNING。修复顺序（MySQL：`192.168.2.13:14307` root/`infini_rag_flow`，库 `rag_flow`）：
  1. `UPDATE document SET run='0', progress=0, progress_msg='' WHERE id IN (...)`（run 状态机：UNSTART=0/RUNNING=1/CANCEL=2/DONE=3/FAIL=4）
  2. `DELETE FROM task WHERE doc_id IN (...) AND progress < 1`（清残留 task 行）
  3. 再 `POST /chunks` 重触发。**顺序不能反**——POST 失败后 document.run 会被回写为 1，需重新 reset。

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

**FAIL 要按 `progress_msg` 二次分诊，格式类错误重触发必然复发**（2026-08-29 实测 63 篇 FAIL 中 59 篇属此类）：

- `Duplicate column names detected`：xlsx 合并单元格/重复列名，table 解析器硬限制。处置 = 先用单文档端点把该篇改 `chunk_method=naive` 再重新触发解析
- `field name cannot contain only whitespace`：同为内容格式问题，重试无效
- 大 xlsx（单表上千行）还容易长成 RUNNING 僵尸并拖慢新文档解析队列，批量处置时优先清掉
- **`OllamaEmbed: the input length exceeds the context length`（2026-09-02 根因）**：不是 chunk_token_num 能修的。链路：RagFlow 的 MarkdownParser 按标题切 section 后**不按 token 硬切大 section**（naive.py 合并循环只管合并不管劈开）→ 含几千字符平文本段的 .md 产出大 chunk → bge-m3@Ollama 有效上限实测 ~2048 tokens（3100 中文字符=2014 tokens 过、3148 字符就 400；/api/ps 显示 8192 但实际按 2048 拒绝，且 `truncate=true` 在 ~2K-10K 字符区间失效、>16K 字符反而截断成功——Ollama 截断实现有 bug）。处置：同步侧在上传前把长章节拆小（feishu_ragflow_sync 的 `split_long_sections` transformer，max 2200 字符按空行/换行切，续节补"原标题（续 N）"）；或修 Ollama 部署的 num_ctx/截断。

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
           + pagerank_fea            # ← 隐藏加分项，见下
           + tag_fea 匹配分 × 10      # 标签命中时
```

- 默认 `vector_similarity_weight = 0.3`。
- `similarity_threshold` 是最终 `similarity` 的硬门槛。

### pagerank_fea：新旧 chunk 分差 +1 的根因（2026-08-07 cyancook 实例验证）

**症状**：同一查询下，7 月解析的旧 chunk `similarity` 恰为"混合分 + 1.0"，当天重解析的新 chunk 没有 +1，新文档在混合检索中被旧文档系统性压制 ~100 名。

**根因**：最终分数含 `pagerank_fea`（源码 `rag/nlp/search.py`：`sim + rank_fea`，`rank_fea = tag_fea×10 + pagerank`）。`pagerank_fea` 在**解析时**从数据集 `Knowledgebase.pagerank` 快照进每个 chunk（`task_service.py` 建 task 时读取）。该数据集 7 月 pagerank=1、后被改为 0，导致存量 chunk 全部 +1、新 chunk 为 0。

**操作**：把数据集 pagerank 改回与存量一致的值（本例 `PUT /api/v1/datasets/{id} {"pagerank": 1}`），并重解析需要拉平的新文档。**改了 pagerank 必须重解析才生效**（chunk 存的是快照）；反之若要把全库从 1 降到 0，需全量重解析 3000+ 文档，代价大，勿轻易改。

**判别方法**：对同一 chunk 对比 `similarity` 与 `w×vec+(1-w)×term` 的手算值，差值恰为整数（如 1.0）即为 pagerank_fea 差异。

### auto_questions：对抗"近义词行海"淹没（2026-08-07 验证）

**症状**：目标 chunk 内容完全正确，但同库有几十行字面更像查询的表格行（如问"象蛇"命中 20+ 行"象蛇蛋"），目标被挤出 rerank 候选窗（约 100 席）和 top_n。

**操作**：文档级 `PUT parser_config {"auto_questions": 3}` 后重解析。LLM 为每行生成"该行回答什么问题"，`question_tks` 在计分中权重 ×6（content×1、title×2、important_kwd×5、question×6），对自然语言问法的各变体都能强命中。224 行文档全量生成约 1-2 分钟。

### multipart 上传文件名不要 URL-encode

`POST /datasets/{id}/documents` 的 `Content-Disposition filename` 直接写 UTF-8 原文。若 `urllib.parse.quote` 后再传，RAGFlow 会把编码串当文件名索引进 `docnm_kwd`（`%E6%88%90...`），且后续 `PUT {"name"}` 改名**只改库不改索引**，docnm 词项加成永久丢失，只能删除重传。

## 关键词配置层级

- 索引期：`parser_config.auto_keywords`（数据集级）
- 查询期：`prompt_config.keyword`（聊天助手级）

两层独立，缺一不可。

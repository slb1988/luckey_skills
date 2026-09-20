# 批量批准驱动（scripts/drive_approvals.py）

大批量批准（数十条）的执行驱动，2026-09-19 会话固化（该批 32 条批准全部 indexed、零失败零冲突）。
复用方式：importlib 加载同目录 `review_queue.py` 执行 scan/detail/apply，不重复 HTTP 逻辑；
换一批任务时只需改写脚本内的 `DECISIONS`（`(review_id前缀, group, content_mode, rationale)`
元组列表，按 `GROUP_ORDER` 组间轮转排序）——判断层仍是 agent 的活，脚本只负责执行编排。

## 执行机制（与 core-rules 的对应）

| 机制 | 对应的既有规则 |
|------|---------------|
| 按组交错：每轮每组最多批一条，同组下一条等前一条轮询 `memory_status=indexed` | 同组串行门禁只串行化本执行者；交错让不同组并行推进，是门禁约束下的吞吐安全形式 |
| 每轮 rescan 取新 `snapshot_token` 再组装 `decisions_round.json` | token 在预览重建/并发变更后失效；不复用旧 packet 的 token |
| 条目已不在 open 队列 → 记 skipped 并移出 pending | 并发处理/`already_processed` 是正常结果，不重试不改判 |
| 本轮仍 `preview_pending` → 跳过本轮但留在 pending | 预览生成是异步的，不等死也不丢弃 |
| apply 失败/超时 → 按未知处理：回读 review 状态，已 `approved` 则转入 indexed 等待，否则留 pending 下轮带新 token 重试 | 503/timeout 回执 ≠ 服务端状态；不自动重发，先只读核实 |

## 长批次运行时的队列活性

- **扫描时 `preview_pending` 的条目可能在处置期间由 worker 生成预览**（实证：2026-09-19
  `01a0b9f2`）。收尾前重扫一次，对新出现的预览按标准质量核对后补批，不要一律留队列升级。
- 处置期间新 session 持续归档，队列会边审边涨——本轮批次的范围以扫描判断过的 packet 为准，
  新到条目另起一轮，不混入本次完成统计。

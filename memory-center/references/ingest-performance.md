# Ingest 链路吞吐实测报告（2026-08-18 批量补传实测）

一次 655 条 memory 批量补传（upload_sessions.py）暴露并量化了整条链路的吞吐特征。
数据来源：graphiti `llm_calls.jsonl`（2750 次调用样本）、hub SQLite outbox、Neo4j 直连核验。

## 链路结构

```text
upload/hook → memory-hub outbox(add_episode) → graphiti 内存队列 → 单 worker → LLM 网关 → Neo4j
                   ↓                                                           ↑
            outbox(confirm_episode) ── GET /episodes/{group}?last_n=N ── 轮询确认
```

## graphiti ingest 性能特征（核心瓶颈）

| 指标 | 实测值 |
|---|---|
| 消费模型 | **单 asyncio worker task**，队列严格串行（`patches/ingest.py` 的 `AsyncWorker`） |
| 每 episode LLM 调用数 | **~24.6 次** |
| ├ medium（kimi-k3，实体/边抽取） | ~3 次，**avg 13.6s/次**，p99 27s |
| └ small（deepseek-v4-flash，逐边去重/解析） | ~21 次，avg 3.1s/次 |
| 单 episode 串行延迟 | p50 **89s**，p90 167s |
| 实际吞吐 | **~85 episodes/小时**（~42s/条，内部有部分 gather 并发） |
| 排空估算 | 650 条积压 ≈ **7.5-8 小时** |
| LLM 错误率 | 极低（2750 次中 1 次限流、2 次解析失败）→ 网关有并发余量 |
| 容器 CPU | 30-55%（大部分时间在等 LLM IO），**NAS CPU 不是瓶颈** |

结论：吞吐 = 单 worker × 每条 25 次 LLM 调用 × 网关延迟 的串行乘积。
加速优先级：① worker 并发化（`AsyncWorker.start()` 改为 `create_task` × N，4 并发→~2h 排空；
风险：同 group 并发时边去重可能产生少量重复实体/边）；② medium 换快模型（质量下降，不建议为补传换）；
③ 补传端限速（upload_sessions.py 大批量加速率上限，避免洪峰）。

## memory-hub outbox 确认机制

- 每条 memory 产生一个 outbox 事件，两段式：`add_episode` 成功后**原地改写**为
  `confirm_episode`（attempt_count 归零、status=retry），确认成功才 completed。
- **episode uuid == memory_id**：graphiti 侧 ingest.py 补丁在 add_episode 前按 uuid MERGE 预建
  EpisodicNode，使 hub 可用 memory_id 直接确认。
- confirm 实现：客户端拉 group 的 `/episodes?last_n={GRAPHITI_EPISODE_CONFIRM_LIMIT=100000}`
  全量列表（含完整 content）比对 uuid。**已改为组级批量结算**（一轮一次查询），
  调度语义见下文「confirm 组级冷却语义」。
- 重试策略（.env）：`OUTBOX_MAX_ATTEMPTS=100000`（实际永不失败）、退避 2^n 秒封顶
  `OUTBOX_MAX_BACKOFF_SECONDS=3600`、`OUTBOX_POLL_SECONDS=1`。
- 大批量补传时 retry 堆积是**正常现象**（episode 还在 graphiti 队列里，`episode is not
  indexed yet` 为真），队列排空后自动转 completed/indexed；抽样直连 Neo4j 验证
  `Episodic.uuid` 命中即可区分「真排队」与「确认逻辑失效」。

## confirm 组级冷却语义（批量确认版）

confirm 不再是逐事件轮询，而是**按 group 共享冷却时间点**调度：

- 同 group 的待确认事件对齐到同一个 `next_attempt_at`；到点后一轮只查一次
  `/episodes`，按 **FIFO 前缀结算**：graphiti 对同 group 串行处理，命中最晚可见的
  待确认事件即说明比它早提交的全部已处理完，整段前缀置 completed。
- 有进展 → 退避重置为 poll 级（秒级紧跟下一轮）；无进展 → 指数退避封顶
  `outbox_confirm_max_backoff_seconds`。
- defer 时**整组统一改写**到最早共享点（含 processing 状态的当前事件），旧版逐条
  退避留下的抖动散点一轮内自愈。
- 后果：dashboard 上 submitted/indexed 计数是**阶梯式跳动**而非连续变化，
  组退避到高档位时可能 30-60 分钟才跳一次——这不代表卡住，看 graphiti 队列深度
  （`remaining queue`）才是真实进度。
- 低效放大点：confirm 逐条轮询 + dashboard episode 探测（秒级 `last_n=100000`）叠加，
  给 graphiti/neo4j 增加可观的只读负载。可优化为 group 级批量确认（每 group 每轮查一次）。

## 分析方法（可复用）

| 目的 | 方法 |
|---|---|
| graphiti 队列深度 | `docker logs memory-center-graphiti \| grep "remaining queue" \| tail` |
| 处理速率 | `docker logs --since 2h ... \| grep -c "Got a job"` |
| LLM 延迟/调用数分布 | 解析 `logs/graphiti/llm_calls.jsonl`（字段含 latency_ms/model/size/caller/episode_uuid/status；200MB 自动轮转归档，历史保留） |
| episode 是否已入 Neo4j | cypher-ro `POST :8006/query`，body 字段名是 **`cypher`**（不是 query），头 `Authorization: Bearer $DASHBOARD_NEO4J_GATEWAY_TOKEN`（token 在 memory-hub `.env`）；`MATCH (n:Episodic {uuid:'<memory_id>'}) RETURN n.uuid, n.created_at` |
| hub outbox 堆积 | SQLite `data/memory-hub.sqlite3` 的 `outbox` 表，按 `status/last_error/attempt_count/substr(created_at,1,13)` 聚合 |
| 端到端对账 | retry 集合的 aggregate_id 批量 `WHERE n.uuid IN [...]` 查 cypher-ro：命中=已入库待确认，未命中=仍在 graphiti 队列 |

## 判读速查

- retry 全是 `episode is not indexed yet` + graphiti 队列深度 ≈ retry 数 → **正常排队**，等即可。
- retry 的 episode 已在 Neo4j 查到但 hub 一直不 confirm → 确认逻辑/查询路径失效（查
  `episode_confirm_limit` 是否小于 group episode 总量、`/episodes` 响应是否含 uuid 字段）。
- 长时间没有新的 `Got a job` → ingest worker 死了（补丁后理论上不会，仍需先排除）。

## episode uuid 的 group 粘性（跨组投递语义）

- graphiti `add_episode(uuid=X)` 是**更新语义**，且 episode 的 `group_id` 在创建时固化——
  同 uuid 换 group 重投只更新内容，**episode 永远留在首个 group**（uuid 全局唯一，不按 group 隔离）。
- 补丁的 uuid 预建已升级为**搬家语义**：已有 episode 的 group ≠ 请求 group 时先删旧再按新
  group 重建（日志特征 `[ingest] uuid=... group move: old -> new`）。调用方无需再先手动
  `DELETE /episode/{uuid}`。
- 排查「Hub 永远 confirm 不过的 submitted」：先按 **payload 里的 group** 查 `/episodes` 找不到，
  再查 episode 是否落在**别的 group**（用 cypher-ro 全局按 uuid 查 `n.group_id`）。

## project merge 固化 vs Graphiti 积压

Hub 的 `finalize_project_merge` 对在途事件的保护窗口是「+90s 清扫旧分组复活 episode、
+120s 新分组重建索引」，按 **outbox processing 租约 60s** 校准——隐含假设是 Graphiti ingest
队列只有秒~分钟级积压。**Hub 删不掉已被 202 接受、躺在 Graphiti 内部队列里的旧 group job**：
积压数小时时，旧 job 会在清扫窗口之后消费，episode 在旧 group「复活」（现在有搬家语义兜底，
同 uuid 的新 group 重建到达时会自动纠正，但复活到纠正之间旧分组会被 dashboard 观测到非空）。

实操建议：大批量补传期间避免固化合并；固化后若 source group 仍有 episode 复活，属预期窗口，
等积压排空后同 uuid 的重投会自动搬走，无需人工干预。

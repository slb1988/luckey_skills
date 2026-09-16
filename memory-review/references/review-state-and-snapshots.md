# 审核状态、语义快照与并发归因

## 三种状态口径

| 口径 | 读取位置 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| 单条记忆索引 | Hub `GET /v1/memories/{memory_id}` 的 `status/group_id` | Hub 对该条记忆的索引状态及物理组归属 | 同组全部入图任务已完成、下一次批准必然可放行 |
| 同组新实体入图门禁 | 批准动作结果，如 `entity_admission_blocked` | 本次动作被同物理组的入图约束拦截 | worker 已死亡、发生死锁或数据库故障 |
| 抽取审核状态 | BFF `GET /api/v1/review/extraction/{review_id}` 的 `status/proposed/novelty` | 此次读取时待审核的预览及分析状态 | 预览在之后的批准请求中仍是同一版本 |

批处理逐条等待 `indexed` 只串行化自己的请求。Dashboard、其他 agent 与后台任务仍可并发改变
条目和组状态；单条 `indexed` 不是整个物理组的就绪屏障。

`entity_admission_blocked` 可伴随审核退回、预览清空与重新生成。因此，清理完成的是一个预览版本，
不是永久绑定 review_id 的属性；门禁退回或版本变化后必须重新读取并审核，不能复用旧清理验收。
是否属于正常在途等待或门禁异常，须另外核对该组实际阻塞任务，不能只凭错误名称定根因。

## 正文、预览与演进分析

审核内容分为三个独立层次，预览修订不是对来源记忆的改写：

| 层次 | 字段 | 职责与修订边界 |
|---|---|---|
| 来源正文 | `distilled_content` | 被审核的蒸馏文本；`remove` / `turns` 修订预览，不改写此正文 |
| 抽取投影 | `proposed.entities/edges` | `curated` 的内容来源；实体摘要与边 fact 都是待核验的事实陈述 |
| 事实演进 | `novelty` | 来源记忆相对候选记忆的增量与演进判断，不是对预览准确性的认证；预览修订后可仍保留原分析 |

`content_mode` 决定入图采用哪一层：`curated` 使用审核后的抽取投影，`original` 使用来源正文。
因此，从预览移除某段内容并未从正文删除它；切换为 `original` 不会继承预览清理的效果，
不能把预览清理当作来源正文的脱敏或纠错。

`novel/evolution` 也不保证修订后的 `curated` 投影仍包含分析所依据的增量。
审核应核对剩余实体摘要和边 fact 是否保留有价值的事实，以及请求、计划、本地实现、部署验证等
证据状态是否与正文一致；不能仅凭 novelty 通过就批准当前预览。

## 预览事实与解析元数据分层

| 层 | 字段 | 比对用途 |
|---|---|---|
| 来源与归属 | `memory_id`、`session_id/session_version`、`group_id`、`distilled_content` | 确认审核的仍是同一来源、版本和物理组 |
| 实体事实 | `proposed.entities[].name/type/summary` | 核对实体身份、类型与摘要；名称变化也须核对语义 |
| 关系事实 | `proposed.edges[].source/name/target/fact` | 核对端点、关系类型和正文支撑，不能只比较边数 |
| 放行前置条件 | review `status`、`novelty.status/admission` 及分析内容 | 识别待生成、已决、duplicate、失败或分析变化 |
| 解析与展示辅助 | `entity_resolution`、`entity_existence`、`suggested_canonical` | 候选及存在性信息；不是已确认的新事实 |

remove 后的事实清单可以保持不变而不再携带部分解析提示。语义校验应分别比较实体事实、关系事实、
来源与门禁，不能将整个 detail/proposed 的 JSON 字节相等作为“事实未变”的唯一判据。
`proposed=null` 与空对象都表示没有可用预览；实体、边是否为空仍须读取实际数组。

辅助元数据变化不自动证明事实变化，也不授权忽略实体重命名、摘要或边 fact 的变化。
后者需要逐条复核，不能仅重新计算一个 hash 就视为审核通过。
本地快照比对不提供服务端原子性；读到批准之间的版本绑定由下面的服务端 token/CAS 契约保证。

## 人工批准的快照契约

| 接口或结果 | 含义 |
|---|---|
| BFF `GET /api/v1/review/extraction/{review_id}` 的 `snapshot_token` | 服务端提供的不透明版本标记；客户端原样保留，不自己算 hash |
| 人工 approve 的 `expected_snapshot_tokens: {review_id: token}` | 每个 review 必填；`original` 与 `curated` 一致 |
| 缺映射或缺任一条 token | HTTP 422 / `REVIEW_SNAPSHOT_REQUIRED`，整请求不执行、没有逐项 results |
| token 格式不合法 | 普通 HTTP 422，不是批准结果 |
| token 过期 | HTTP 200 的该项 `status=review_changed`；该项不处置、不写 outbox，也不返回替代 token |
| reject / retry_preview | 服务端不要求批准 token；CLI 的 reject 保持兼容 |

同一批请求的其他项可能成功，不能把一个 `review_changed` 解读为整批回滚。CLI 留下逐项结果并停止后续动作，
重新读取后仍须重新审核，不自动换 token 再批准；`already_processed` 保持并发跳过语义。

token 覆盖正文、归属、审核状态、novelty 以及实体/关系事实，排除解析提示与更新时间噪音。
组门禁仍在批准时即时检查；token 不取代组就绪约束，也不授权自动 approve。

scan 将 token 与供审核的正文/预览一起保存，并保留状态、attempts 和来源元数据；字段缺失留空，不猜版本。
决策文件必须复制该次已审核的 token，apply 不通过 GET 自动补齐。
同一 review 的 remove/approve 必须拆文件；remove 后重新读取、核对整个预览，再使用其新 token。
本地缺 token 或存在同条 remove+approve 时，连 dry-run 也拒绝；remove 失败后不发送任何后续批准或拒绝。

本契约依赖服务端版本支持；客户端安装/推送不代表服务已部署。旧服务返回无 token 的 detail 时仍可扫描，
但新客户端不能批准，不提供绕过快照校验的兼容降级。

## 动作台账与队列快照分层

| 记录 | 用途 |
|---|---|
| 本次已确认的 review_id 集合 | 划定允许操作的批次；新到条目不因出现在队列里就获得授权 |
| 每次请求与动作回执 | 统计本执行者的批准、拒绝、清理、失败与并发跳过 |
| 后续 memory 索引状态 | 区分“批准已受理”与“Hub 已标记 indexed” |
| 最终队列快照 | 描述快照时仍待审、已批准或已拒绝的条目，不用于推算本次写操作数量 |

其他执行者可以处理本报告中的保留项或采取与原建议不同的决定。`already_processed`，以及复读时
已为 approved/rejected 的条目，均应跳过，不重试、不改判，也不把它们计入自己的成功动作。
不能仅凭 `decision_rationale` 为空推断操作者身份；归因须结合本次动作回执，报告并发变化即可。

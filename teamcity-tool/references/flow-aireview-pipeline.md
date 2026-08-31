# PLN_FlowAiReview 管线性能画像（2026-08-31 基线，14 次构建采样）

AI Review 复合链：`PLN_SyncDepot → PLN_Unshelve → PLN_BuildUE_Linux → PLN_AiReview`（pi agent 评审）。
REST API 查复合构建只返回直接 snapshot 依赖，**要递归追踪** `snapshot-dependencies` 才能拿到完整链路。

## 各环节耗时基线

| 环节 | 典型耗时 | 性质 |
|---|---|---|
| 排队 | 0~4+ min | 单 Linux agent 串行，见下 |
| Sync Depot | 63~93s | 恒定开销：p4 sync 全量 have-list 扫描；`p4 sync --parallel=threads=4` 约省一半 |
| Unshelve | ~12s | 可忽略 |
| BuildUE_Linux | 增量 12~48s | 57min 全量重编只出现在 2026-08-24/25（跨链 UBT makefile 互爆，脚本内修复已生效）；再出现 57min 级别耗时可判定为该问题复发 |
| AiReview | 77s~20min | **99% 是 `Pi_Agent_Review` 单步**（LLM 评审），其余步骤全部 <1s |

## Pi_Agent_Review 步的非显性特征

- 评审时长**与 diff 大小不相关**（0.8KB diff 审 321s，157KB 的反而 126s）；耗时由 turn 数和 thinking 深度驱动。
- `thinking_level=high` 下每个 LLM 往返 20~30s，验证性 grep/read 也会产出上万字符思考；上下文随 turn 单调膨胀（实测 15K→245K tokens，末 turn cacheRead 237K），越跑越慢。单次评审成本约 $10。
- pi CLI 支持 `--thinking low`，大部分 turn 只是验证性工具调用，降档预计砍 40~60% 时长（评审质量需 A/B 对比几次再定）。
- 每次评审必读 `.claude/skills/pl-review/SKILL.md`，内联进 prompt.md 可省固定 1~2 个 turn 和首轮 context。
- pi session 文件在 agent workspace 的 `sessions/` 下无限累积，且**每次构建全量上传 artifact**——分析评审过程时直接去 workspace 拿 session JSONL 比翻 TC artifact 快。

## 排队瓶颈

`DefaultAgent` 是唯一 Linux agent，AiReview 链与 CodeGraph 链共享它，串行执行。
review 步是 LLM/IO 等待型（编译才吃 CPU），**同机加第二个 agent 即可消除串行**；
workspace 命名 `{agent}_{stream}` 原生支持多 agent 共存。

## 已确认的其他问题

- 同一 CL 会被完整重审（观测到 127675×2、127683×2、125931×4），无按 CL+编译结果哈希的评审缓存。
- 结果发布回调步带 `|| true`，回调失败被吞掉时提交方永远等不到结果——用户报"评审卡住/慢"时先查这一步。

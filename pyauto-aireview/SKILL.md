---
name: pyauto-aireview
description: >
  pyAutomation AI Review 端到端开发、排障、性能分析与运维导航。凡涉及 AI Review dashboard、P4V Request Review、shelved CL、Review ID、PLN_FlowAiReview/PLN_TaskAiReview、Pi Agent Review、tc_callback、backend LLM fallback、评审排队/卡住/慢/失败/误判、编译或 warning 证据、reviewer 决策、reopen/refresh、自动批准、代提交队列、CL 消失、飞书通知，或需要在 ws:autoserver-deveops、ws:maindev、@auto-server、@winbuilder*_maindev 间定位责任时都应使用。先建立 Review/CL/Flow/Task/Agent 身份映射，再按证据拆时间线；代码与运行时必须路由到各自工作区或机器。
compatibility: Windows, Perforce, TeamCity REST, Flask/SQLAlchemy, Vue, Pi CLI, Orca workspace routing, A2A agents
---

# pyAutomation AI Review

AI Review 负责从 shelf 发起、编译与模型评审、人工/系统决策，到 P4 代提交及作者 workspace 收口。它不是一般 A2A task，也不是所有 TeamCity 构建的状态机。

跨系统证据、异步一致性、环境与执行边界按需读 [pyauto-shared](../pyauto-shared/SKILL.md)；这里保留 AI Review 业务规则。

## 五分钟上手

先读 [quickstart](references/quickstart.md)，再选一张图：

- [端到端主链](references/diagrams/lifecycle.mmd)：组件如何交接。
- [独立状态轴](references/diagrams/status-axes.mmd)：编译、AI、审批、提交为何不能混成一个“成功”。
- [失败归因](references/diagrams/failure-routing.mmd)：页面标签如何回溯原始原因。

主线：`RequestReview → backend job → Flow(Sync/Unshelve/Build/Collect/Runner/Publish) → callback或fallback → decision → submit job → P4与DB收敛`。

图是导航，不替代条件与状态权威；图的范围和源码锚点见所属 reference。

## 只读当前问题需要的参考

| 问题 | 参考 |
|---|---|
| 对象、流程与生命周期 | [architecture-lifecycle](references/architecture-lifecycle.md) |
| API、表、worker、callback、配置、刷新与测试 | [backend-module](references/backend-module.md) |
| 构建链、参数、Agent、Report/Notification 与耗时 | [teamcity-pipeline](references/teamcity-pipeline.md) |
| TeamCity 交互、首次择机/续评钉机、容量等待与 tick | [teamcity-interaction](references/teamcity-interaction.md) |
| Collect / MergeGate、MainDev/Wwise 完整视图与 stream 参数耦合、Runner / Publish / Memory / Pi、AS warning 误分类 | [review-toolchain](references/review-toolchain.md) |
| reviewer、jury、自批、代提交、mixed stream、P4错误与通知 | [decision-submit-notification](references/decision-submit-notification.md) |
| 排队、慢、失败、错配、缺日志、错误 verdict | [diagnostics](references/diagnostics.md) |
| 源码/运行时责任及工具迁移边界 | [workspace-agent-routing](references/workspace-agent-routing.md) |
| 改码、隔离测试、pending CL与发布验收 | [implementation-validation](references/implementation-validation.md) |
| 现行能力、历史行为与未来设计 | [known-gaps-roadmap](references/known-gaps-roadmap.md) |

TeamCity 通用 REST/参数查询复用 [teamcity-tool](../teamcity-tool/SKILL.md)；发布复用对应部署技能，不在本页复制命令。

## 六个不变量

1. **Review ID 是业务锚点。** 原 shelf CL、提交后 CL、Flow、各 Task、Agent 和当前 callback 代际分别记录；CL 可能 rename。
2. **核 callback 映射再归因。** 从具体 Task 参数只提取 `review_id` 等白名单字段，不输出 token/nonce/完整 URL。
3. **时间线先统一时区。** 后端常为 UTC、TC 日志常为 `+0800`；前置依赖等待不是 Agent starvation。
4. **绿色不等于真实评审成功。** Runner/Publish 可以 error + exit0；bypass 可写占位 approve。检查本轮 manifest/result/callback，不只看 TC SUCCESS。
5. **编译、AI、审批与提交独立。** AI participant 不是人工票；approved 是代提交前的过渡态，P4与DB都收敛才是 submitted；纯二进制 risk0 也不代表模型批准。
6. **源码、部署、本轮事实分开。** 工具路径和能力以实际 Task入口/版本核实，不能把 pending 修复、迁移计划或一台构建机成功画成全线上事实。

## 首查与停止条件

- **具体 Review 故障**：先取详情/activities/ai_summary，核当前轮 CL、状态、结果来源与 Flow。需要时才展开失败 Task、callback映射和本轮 artifact。
- **慢/时序问题**：再拉业务与 TC 两条时间线，拆排队、依赖、provider、工具和 backoff；普通配置问答不强制拉全链。
- **warning 误报**：区分真正命中、证据不可用、Collect 失败和工具链保护；页面叫 AS warning 不证明匹配器命中。详见失败图与 Publish 参考。
- **提交未知**：先核 approved round、submit job、P4明确回执；不按作者、描述或最近 CL猜结果。
- **机器补证**：先由 owning workspace 确定缺失变量，再派精确机器；证据足以回答请求和最小验收即停。

## 容易混淆的边界

- informer 的 warning 过滤与失败策略不同，Report/Notification 参数不继承；通知侧 Pi 与评审 Runner 的模型调用独立。见 TeamCity 参考。
- 定案 callback 与编译错误分析短路是两个契约；`reject` 不保证零 LLM，缺回调时仍须检查各入口。见 backend 参考。
- refresh 无 shelf 的失败不代表旧轮停止；先核本轮 activities，不把旧轮出分当刷新成功。
- 指定 reviewer 不必然禁用作者受控自批；strict jury、系统自动批准和纯二进制跳链各有独立条件。见决策参考。
- severity 与“本 CL 是否负责修”及总分是不同维度；放行不降低严重度，最终严重度约束风险下限。见 backend 结果契约。
- 飞书通知不唤醒本地 watcher；当前构建内 Pi 也不能据此假定拥有协调者的 A2A 能力。

<memory category="common-patterns">
- **导表判定的证据边界**：MainDev `Main/RawData/dt_metadata.json` 的工作簿 `hash` 是整个 xlsx 的 MD5，`size` 是字节数；真实导表可同时改变两者，不等于 hash-only。
- 工作簿 key 集不变只证明 metadata 未新增工作簿登记，不证明既有 xlsx 无新增 sheet/业务行；`tag_defs_cache`、`tag_info_cache`、`tuple_cache` 相等也不证明全项目无 tag 注册变动，仍须核完整 CL 的注册代码等变更。
- 导表还可能包含 RawData `.xlsx` 与 `Export/DataAsset/.../*.txt` 快照；同一 CL 的快照与 `.uasset` 不保证一一配对。仅允许 hash-only 与 `.uasset/.csv` 会排除这类真实导表，不能为迎合样本而静默放宽规则。
</memory>

<memory category="troubleshooting">
- `PLN_FlowAiReview` 中，Unshelve 失败可使编译节点根本未启动、未分配 Agent；若 TaskAiReview 仍要求与该编译节点同机，即使前置均已结束、允许编译失败后继续，评审仍可永久排队，Flow 无法收口。这是同机锚点缺失，不是 Agent 忙碌。
- 同机约束与失败策略须配对：TaskAiReview 应锚定 Unshelve 同机，Unshelve 失败直接终止链；对编译节点保留顺序依赖及失败后继续评审的行为，不再以可能未启动的编译节点作为同机锚点。
- 配置入口：`ws:autoserver-deveops` 的 `Teamcity_PLN/.teamcity/patches/buildTypes/TaskAiReview.kts`；生产与测试配置须保持上述依赖语义一致。
</memory>

<memory category="troubleshooting">
- 首次评审优先用配置允许的通用兼容候选投递，由 TeamCity 在实际可运行时择机；`get_agents()` 是瞬时状态快照，不是槽位预留或整链兼容性证明，不应据此提前钉死单机。
- 已绑定原生 Pi 会话的 shelf 更新续评有跨轮 Agent 亲和性：`pyAutomation/backend/server/applications/ai_review/ai_worker.py::_trigger_extra_properties()` 读取 `pi_session_agent`，将 `DefaultAgent` 与 `override.dep.*.DefaultAgent` 同设为原 Agent 的精确正则，并携带 `AI_REVIEW_PI_SESSION_AGENT`；不按忙闲改选机器。
- 根因是 `DevOps/AiReview/AiReviewRunner.py` 依赖构建机本地原生 session 文件；未恢复原会话就跨机续接会报 `SESSION_INVALID`。单删机器限制不能保住续接语义，清空会话换机也不是原会话续评。
- 因此其他 WinBuilder 空闲仍可能不兼容：链首 Sync 等被绑定机器，下游等依赖。排查时核 Flow 与 Sync 的有效 Agent 参数及 Review 会话绑定，区分此约束与“同机锚点从未获得 Agent”。
- 已确认的正常容量等待应持续 tick，不因机器全忙耗尽执行预算、误降级或重复投递；无兼容候选/查询失败与容量等待分开。具体查询、轮询版本边界和验收要求独立记录在 [TeamCity 交互](references/teamcity-interaction.md)。
</memory>

<memory category="common-patterns">
- 普通网页 diff 来自建评审时落库的 `ai_review_files.diff_content` 文本快照，不是作者或构建机的实时 diff；删除 shelf 不会使已存 diff 同步消失。
- “整文件对比”则实时读取 P4 shelf；shelf 已空时该接口可失败，即使同一页的普通 diff 仍能显示。
- 快照不是完整文件备份：文本仅在差异未截断且基线匹配时可尝试重建，不能据此保证恢复；它不提供二进制内容备份。存储上限与 API 见 [backend-module](references/backend-module.md)。
</memory>

<memory category="troubleshooting">
- SKILL 索引类漏检根因（Review 834 / MainDev CL 134117 查明）：pl-review 规则虽有 SKILL.index.json 专项（hash 比对、手改打回），但对 `.GUI/data` 三个行号拆分文件零条款；Collect/MergeGate/Runner/Publish 与后端 evaluate_ai_policy 全无任何索引一致性确定性检查（grep 零命中），唯一防线是 LLM 自觉。
- 规则只链接未内联的契约文件（references/skill-index-format.md）时，低思考档位模型（kimi-k3 thinking=low）实测从未 read 该契约、也未取索引文件 diff，仅 wc -l 查行数即放行——关键契约必须内联进规则正文，或由确定性检查兑底。
- 续评轮会短路：声明「manifest 一致，沿用首轮结论」即不再重新核对，首轮漏检在续评中必然延续。修复方案见 ObsidianVault 仓 `.claude/plans/AiReview-SKILL索引一致性确定性检查.md`。
</memory>

<memory category="troubleshooting">
- SKILL_INDEX_CHECK=unavailable 降级根因（Review 1097 查明）：DevOps 侧确定性检查自 CL 1851（2026-09-22）在线，但 Collect `_run_builder_probe`（`AiReviewContextCollect.py:995-1001`）用 #head 生成器跑 `--out-dir` 探测，而 MainDev head 生成器无 argv/--out-dir 处理 → 探测 fixture 被就地写入 `.GUI/data` → fail-closed 判 `builder_unsupported`。根因是生成器 --out-dir 能力（原 CL134180）pending 被删、从未入库；修复 = 重建生成器 CL（--out-dir rootDir 零写 + --strict），落地后 unavailable 降级直接消失。
- 五态契约无闸门（现行规则自 CL 134397 入库）：`unavailable`/`skipped` 态只规定人工四点核对义务，无 severity floor、无「未验证→不得 approve」条款；检查点 1 失败无 severity/verdict 映射（四点中仅检查点 4 手改痕迹写了直接打回）。模型在 unavailable 下披露「未核对」后给 low 严格符合规则字面——压低 verdict 须在 Publish 做确定性兜底（unavailable+触索引 → 强制 high+reject/risk100），只改规则文本不够。
- 幽灵条目事故实证（检查点 1 描述的事故真实发生）：audio-grill、audio-qc-workbench、yue2-workbench 三个 SKILL.md 从未在 depot（p4 fstat 实证），系脏工作区扫描进索引；下一班重生成（SKILL.index.json#564 / CL 136104）全部静默消失。凡是「新增条目但 file 本体不在本 CL」必须 p4 fstat 核 depot 存在，确认不在 = 至少 high+reject。
- 修复计划已更新于 `.claude/plans/AiReview-SKILL索引一致性确定性检查.md`（MainDev 生成器重建、pl-review 规则 6 处修订、Publish 确定性兜底、2026-09-22 起触索引且 approve 的窗口审计）。
</memory>

<memory category="troubleshooting">
- 代提交失败通知轰炸的根因二分（Review 726 等查明）：直提失败（approve 期间 head 前进 out-of-date、作者 client 仍开着文件）是正常业务（约占 60%），按设计进 `_auto_merge_submit` 兜底；真正致灾的是兜底自身两个缺陷。
- `p4_adapter.prepare_merged_cl()` 的 sync 步用裸 `admin.run`，而 P4Python 默认 `exception_level=2`——warning 级输出 `file(s) up-to-date.` 也抛异常、炸掉整个合并（bot workspace haveRev 有历史残留时几乎必触发）。同文件 `_run_capture`（exception_level 临时置 0）就是干这个的但此处未用；正确性由 `_verify_have_revs` 兜底。
- 作者原 CL 仍持有 +l 独占文件时，bot workspace unshelve 报 `can't edit exclusive file already opened`，auto-merge 同样必败，需独立处置策略。
- `notify_submit_failed()` 收件人 = 作者 + 全部 role=1 admin + 评审群，无去重/节流，每次失败必发；用户点重试再失败会再发一轮（Review 726 曾 4 分半连败 4 次发 4 轮）。admin 收到高频 DM 是失败率 × 无节流的乘积，不是通知配置错误。
</memory>

<memory category="troubleshooting">
- 生产 `AI_REVIEW_GROUP_CHAT_ID` 为空（2026-10-06 @auto-server 实测）＝群通知从未启用，全部通知只发私信卡片；“群里没收到通知”先核此键，不是卡片发送失败；`notify_submit_failed()` 收件人中的“评审群”因此实际是空操作。
- ai_review 后端存在硬编码凭证（LLM key、MySQL 密码、飞书 secret），是已确认缺陷不是样板：轮换凭证必须改源码并重启服务；复刻或改造时必须改 env 注入。
</memory>

<memory category="code-locations">
- ASD-STE100 中文复刻手册（2026-10-06 交付）：`luckey/02_notes/toolchain/pyautomation-ai-review-manual.md`——27 项 feature 及验收、12 表与全部配置键的生产生效值、TC buildType 依赖、8 步验收清单；带 文件:行号 的事实底稿在 `.local/aireview-manual/source-facts-report.md`。
</memory>

<memory category="troubleshooting">
- 代提交队首阻塞根因（Review 878 堵 927 查明）：评审原 CL 在 P4 已查询不到时，submit worker 把“CL 消失”误判为临时故障，约每 30 秒无限重试并死占队首，后续全部代提交（927、930）被堵。处置 = 管理端正常业务接口结束队首该单，队列即自动放行（927→CL 134731、930→CL 134732），无需手工重提或改库。
- 重试分类契约：不可恢复错误必须明确失败并释放队列——原 CL 缺失走对账路径，确定性合并冲突（shelf 基线落后 head，如 qa-testcase-workflow/SKILL.md shelf 基于 #13 而 CL 134282 已至 #14）结束自动尝试转人工；仅临时性故障适合有限重试。源码修复由并行会话提交为 CL 1859（179 测试通过），是否已部署以线上版本核实。
- 文件存在先行提交只说明有合并风险，不构成合并冲突证据；是否冲突以实际 unshelve/merge 结果为准，不能据此提前判死该单。
</memory>

<memory category="troubleshooting">
- 代提交完整性门禁 blocked 死循环根因（Review 1157 / CL 136348 查明）：作者把文件撤出 shelf 时，门禁拿前轮 manifest 留存的 shelf sha256 核该文件当前 head 内容，不一致即 fail-closed 拦截（`head content differs from the removed shelf revision`）；SKILL.index.json 这类自动化高频维护文件（head 持续前进）即使撤出本身安全也必触发。
- 唯一放行通道 `POST /ai_review/reviews/<id>/confirm_removals` 要求 reviewer 确认；自批单参与者只有作者 + `__ai__`，无人有资格确认 → 永久卡住（设计缺口）。运行时解锁 = 先加一名人工 reviewer 再调 confirm_removals，确认后自动重触发代提交，无需重跑 review。
- 两个补偿缺陷使 blocked 单永续循环：`submit_retry_sweep`/`_reconcile_ghost_submit` 补入队前不查 `integrity_state==blocked`，blocked 单被当幽灵单每 10 分钟重复补入队，每次拦截新记一条 `integrity_gate_blocked` 活动并刷新 update_time 续期宽限（1157 已 130+ 条且仍在循环）；且 blocked 状态零通知，作者完全无感知。
</memory>

<memory category="troubleshooting">
- 续评文件流失放行根因（Review 892 查明）：续评续接前轮原生 Pi session，且本轮 `review_input.md` 明文允许"此前轮次的 findings 与代码分析结论可复用"；但输入只含当前 shelf 文件清单，无结构化跨轮 added/removed 对账，文件减少全靠模型自行发现。
- 已确认的误判模式：模型为文件减少编造解释，把本轮 `baseline_cl` 当作"被移除文件已随该 CL 提交出库"的证据（892 中声称 CL 134463，实为无关关卡资源），随后围绕"上轮唯一 high 已修复"收口 approve 并自动提交。`baseline_cl` 只是本轮评审基线，不构成任何文件去向证明；"已在其他 CL 提交"类声称必须回查 P4 文件级内容核实。
- 排查锚点：后端 refresh 日志记录 `kept:N removed:M`，是文件数变化的权威证据；代提交 CL 与提交时 shelf 一致即可排除"代提交漏交"；TC artifact 的 `runner_manifest.json` 可证是否续接前轮 session（该轮 transcript 未留存，模型实际验证命令无法复核）。
- 跨轮完整性门禁设计方向见 [known-gaps-roadmap](references/known-gaps-roadmap.md) 2.9。
</memory>

<memory category="troubleshooting">
- 快车道 Review 本地不收口根因（Review 1089 / CL 136030→136031 查明）：代提交 `submit -e` 成功后 `review.cl` 被 rename 成提交后 CL 号，而 watcher 发现逻辑 `RequestReview.py::find_review_item_in_items` 只按当前 `cl` 匹配；设计假设提交前必有轮询窗口锁定 review id。
- 后端 `ai_reviews` 表无 `original_cl` 列，`_review_brief` 只下发当前 cl；original_cl 仅存于 `cl_submitted` activity payload，rename 之后列表接口无法再关联作者的原 CL。
- script_rule 快车道（`table_export_fastpath.py`，无 AI/编译）全生命周期约 2 秒 < watcher 10 秒发现轮询间隔，窗口被整体跳过 → finalize_sync 与 cleanup_empty_cl 不执行：本地留空壳 pending CL、相关文件 have 落后 head；watcher 空转到 1 小时超时后弹误导提示「CL 长时间未在网页发起 Review」（实为已提交）。
- AI/编译路径生命周期为分钟级，rename 前必然锁定 id，故仅快车道触发；每个快车道 Review 约 80% 概率复现（2s 窗口 vs 10s 轮询）。正解是发现逻辑按 `cl` 或 `original_cl` 匹配，缩短轮询间隔治标不治本。
</memory>

<memory category="troubleshooting">
- RequestReview 二次发起 shelve -r 覆盖丢文件根因（Review 1167 / CL 136406 查明）：首次 launch shelve 成功后 `revert -w` 把文件还原出工作区（评审期 shelf 是唯一内容副本）；评审中往 CL 补拖文件再点 Request Review，`ensure_shelved` 的 `p4 shelve -r -c <cl> -Af` 以当前 open 集合整体替换 shelf——open 只剩新拖入文件，原 shelved 副本全部销毁。逻辑 bug 非时序竞态；修复并重新分发前，「评审中补文件再点 Request Review」是 team-wide 数据丢失风险。
- 漏洞形状：shelf-only 复用路径只覆盖零 open 文件；「上轮 shelf 留存 + 本轮新 open」的混合状态落 replace 路径即丢数据。launcher 二次发起不查后端同 CL 非终态 review、不走 refresh 通道（refresh 已有 shelf_fingerprint + removal_confirmations 门禁，可强制导入复用）。
- 诊断锚点：launcher 逐 launch 时序在 `%LOCALAPPDATA%\Epic Games\RequestReview\watch.log`；本地「字节快照」只是 SHA-256 摘要、不作内容备份，内容级恢复只剩后端 `ai_review_files.diff_content` 快照（截断/基线限制见前述快照条）。
- 修复方案见 ObsidianVault 仓 `.claude/plans/RequestReview二次发起shelf覆盖丢文件.md`（shelve -r 守卫 + launcher in-flight 检查 + watcher restore 对账）；修复经 dist 自更新链重新分发到各机 P4VUtils 才生效。
</memory>

<memory category="common-patterns">
- 收益/打回量化统计的生产库口径边界（2026-09 只读实测）：`ai_review_activities` 有历史状态/决策/编译/AI 活动，但无 round_id，不能可靠关联逐事件轮次；生产库 2026-10-06 实测已部署 round_manifests/result_versions/removal_confirmations（共 12 表，见 backend 参考），此前“9 表/模型未部署”结论过期，但存量历史事件仍无轮次关联。
- `ai_reviews`/participants/`ai_findings`/`round_token` 都是当前态：findings 刷新会清理替换不能还原历史，`ai_review_jobs`/submit jobs 按 review 单行复用不是尝试历史，当前值不能倒填先前拒绝时的真值；DB 时间为 UTC。
- rejected 状态 ≠ AI 拦截缺陷：作者自拒、代提交失败、合并冲突也产生打回事件；而 AI reject、编译 failed 只阻塞审批轴，不一定产生 rejected 状态。作者自拒也可能由有效 AI 意见触发。
- 打回原因跨 `decision_made` 与 `status_changed.payload.reason` 两个来源，汇总必须按唯一活动 ID 互斥归类且合计=总事件数，关联不上保留 unknown；分类计数不闭合的占比表不得发布。
- Pi/TC 主路径模型 usage 未完整回写，token 为 0 或无值可能是缺失而非零消耗。完整量化方案与基线见 ObsidianVault 仓 `.claude/plans/AIReview-Value-Metrics.md`。
</memory>

## 修改与交付

按 [pyauto-shared 共性边界](../pyauto-shared/references/common-practices.md) 路由及保护凭证；按实施参考核 opened/head/shelf、保留并行改动、分 depot 建专用 pending CL。不自动 submit、部署、重跑或改生产 DB。

返回：对象映射 → 根因与决定性证据 → 修改/测试/CL → 已部署或未部署、已验证或未验证。只在时序问题展开时间线；相邻问题单列，不扩成第二轮调查。

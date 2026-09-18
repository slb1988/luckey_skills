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

<memory category="troubleshooting">
- `PLN_FlowAiReview` 中，Unshelve 失败可使编译节点根本未启动、未分配 Agent；若 TaskAiReview 仍要求与该编译节点同机，即使前置均已结束、允许编译失败后继续，评审仍可永久排队，Flow 无法收口。这是同机锚点缺失，不是 Agent 忙碌。
- 同机约束与失败策略须配对：TaskAiReview 应锚定 Unshelve 同机，Unshelve 失败直接终止链；对编译节点保留顺序依赖及失败后继续评审的行为，不再以可能未启动的编译节点作为同机锚点。
- 配置入口：`ws:autoserver-deveops` 的 `Teamcity_PLN/.teamcity/patches/buildTypes/TaskAiReview.kts`；生产与测试配置须保持上述依赖语义一致。
</memory>

<memory category="troubleshooting">
- 已绑定原生 Pi 会话的 shelf 更新续评有跨轮 Agent 亲和性：`pyAutomation/backend/server/applications/ai_review/ai_worker.py::_trigger_extra_properties()` 读取 `pi_session_agent`，将 `DefaultAgent` 与 `override.dep.*.DefaultAgent` 同设为原 Agent 的精确正则，并携带 `AI_REVIEW_PI_SESSION_AGENT`；不按忙闲改选机器。
- 根因是 `DevOps/AiReview/AiReviewRunner.py` 依赖构建机本地原生 session 文件；未恢复原会话就跨机续接会报 `SESSION_INVALID`。单删机器限制不能保住续接语义，清空会话换机也不是原会话续评。
- 因此其他 WinBuilder 空闲仍可能不兼容：链首 Sync 等被绑定机器，下游等依赖。排查时核 Flow 与 Sync 的有效 Agent 参数及 Review 会话绑定，区分此约束与“同机锚点从未获得 Agent”。
</memory>

<memory category="common-patterns">
- 普通网页 diff 来自建评审时落库的 `ai_review_files.diff_content` 文本快照，不是作者或构建机的实时 diff；删除 shelf 不会使已存 diff 同步消失。
- “整文件对比”则实时读取 P4 shelf；shelf 已空时该接口可失败，即使同一页的普通 diff 仍能显示。
- 快照不是完整文件备份：文本仅在差异未截断且基线匹配时可尝试重建，不能据此保证恢复；它不提供二进制内容备份。存储上限与 API 见 [backend-module](references/backend-module.md)。
</memory>

## 修改与交付

按 [pyauto-shared 共性边界](../pyauto-shared/references/common-practices.md) 路由及保护凭证；按实施参考核 opened/head/shelf、保留并行改动、分 depot 建专用 pending CL。不自动 submit、部署、重跑或改生产 DB。

返回：对象映射 → 根因与决定性证据 → 修改/测试/CL → 已部署或未部署、已验证或未验证。只在时序问题展开时间线；相邻问题单列，不扩成第二轮调查。

---
name: pyauto-aireview
description: >
  pyAutomation AI Review 端到端开发、排障、性能分析与运维导航。凡涉及 AI Review dashboard、P4V Request Review、shelved CL、Review ID、PLN_FlowAiReview/PLN_TaskAiReview、Pi Agent Review、tc_callback、backend LLM fallback、评审排队/卡住/慢/失败/误判、编译或 warning 证据、reviewer 决策、reopen/refresh、自动批准、代提交队列、CL 消失、飞书通知，或需要在 ws:autoserver-deveops、ws:maindev、@auto-server、@winbuilder*_maindev 间定位责任时都应使用。先建立 Review/CL/Flow/Task/Agent 身份映射，再按证据拆时间线；代码与运行时必须路由到各自工作区或机器。
compatibility: Windows, Perforce, TeamCity REST, Flask/SQLAlchemy, Vue, Pi CLI, Orca workspace routing, A2A agents
---

# pyAutomation AI Review

本 skill 是 AI Review 跨 P4V、pyAutomation、TeamCity、MainDev 构建机、Pi、飞书和自动提交的总入口。正文只保留主脉络；进入具体模块前读取对应 reference，不要一次加载全部文件。

## 先选参考

| 当前问题 | 必读 reference |
|---|---|
| 想理解端到端流程、对象身份或状态机 | [architecture-lifecycle](references/architecture-lifecycle.md) |
| 后端 API、表、AI worker、callback、配置或测试 | [backend-module](references/backend-module.md) |
| TeamCity 链、参数、同机 workspace、步骤、artifact 或耗时 | [teamcity-pipeline](references/teamcity-pipeline.md) |
| Collect / MergeGate / Runner / Publish / Memory / Pi | [maindev-toolchain](references/maindev-toolchain.md) |
| 人工决策、jury、自动批准、提交队列、P4 闭环或通知 | [decision-submit-notification](references/decision-submit-notification.md) |
| 排队、卡住、慢、失败、错配、缺日志、错误 verdict | [diagnostics](references/diagnostics.md) |
| 要判断用 `ws:` 还是 `@agent`、在哪台机器取证 | [workspace-agent-routing](references/workspace-agent-routing.md) |
| 要改代码、测试、建 P4 CL、部署或验收 | [implementation-validation](references/implementation-validation.md) |
| 判断现行能力、已退役行为和未落地设计 | [known-gaps-roadmap](references/known-gaps-roadmap.md) |

TeamCity 通用 REST、参数解析和 Agent 匹配继续使用 `teamcity-tool`；服务部署继续使用对应 auto-server deploy skill。本 skill 负责把它们放回 AI Review 业务语义中。

## 系统主脉络

```text
P4V Request Review
  → shelve + 本地交接
  → POST /ai_review/request
  → AIReview + AIReviewJob
  → PLN_FlowAiReview
      Sync → Unshelve/merge → BuildUEWindows/AS/report → TaskAiReview
      Collect → Pi Runner → Publish → tc_callback → Cleanup
  → callback 定案；error/skipped 时 backend LLM fallback
  → reviewer / jury / system decision
  → approved → AIReviewSubmitJob
  → auto-server submit worker → p4 submit -e / auto-merge / 对账
  → submitted、通知与作者 workspace 收口
```

## 先守住六个不变量

1. **Review ID 是业务锚点。** Shelved CL 提交后可能 rename；Flow build、各 Task build、Agent 和 callback 是不同身份，不能凭两个 URL 看起来相近就认定属于同一单。
2. **先核对 callback 映射。** 从具体 Task build 的 `env.AI_REVIEW_CALLBACK_URL` 只提取并报告 `review_id`，其余 token/nonce 必须遮蔽。
3. **业务时间线跨时区。** 后端 DB/activity 常为 UTC，TeamCity 日志常为 `+0800`；先归一时区再判断静默窗口、重试和人工动作。
4. **绿色不等于真实评审成功。** Runner/Publish 会把 Pi 故障降级成 `verdict=error` 并保持构建可收口；bypass 还能写占位 approve。验收要看本轮 session/manifest/result/callback，而不是只看 SUCCESS。
5. **编译、AI、审批、提交彼此独立。** BuildUE 失败后 Pi 仍可分析；AI 结论不是人工票；`approved` 只是等待代提交的过渡态，只有 P4 与 DB 都收口才是 `submitted`。
6. **源码事实与运行时事实分开。** P4 head/当前源码只能说明实现；线上参数、部署版本、Agent 用户、Pi 版本、网络和 artifact 必须在实际服务或构建机核实。

<memory category="troubleshooting">
AS warning 的采集白名单不是失败策略：`TeamCityLogParserInformer.py` 的 `--warning-categories`
只过滤告警，命中 warning 仍正常返回 0。BuildUE 的 Report / Notification 是独立调用，参数不继承；
Notification 默认 `--log-level=Error`，只补类别仍不启用 warning，需同时启用 All 级别。
`job-result=FAILURE` 且无匹配诊断时，informer 自身还会调用 `pi_analyze_errors`；
这条通知侧 Pi 兜底独立于 TaskAiReview Runner，停评审节点不能保证“零 AI”。
</memory>

<memory category="common-patterns">
跳过两类 backend LLM 的回调契约不同：`_run_analysis` 依赖定案 `tc_callback`；
`_poll_compile` 中的 `_analyze_compile_errors` 还要求回调携带非空 `compile_log_analysis`，
由 `service.py` 落为 `compile_analysis` 并标记 `compile_result['analysis_source']='tc_callback'`。
因此仅发送 reject verdict 不保证零 LLM；确定性门禁还须覆盖回调缺失时的两个模型入口，
不能把“回调正常时会短路”当成端到端的零 AI 保证。
</memory>

<memory category="troubleshooting">
AI Review 的清理步骤也参与调度兼容性：`TaskBuildUEWindows` 使用 PowerShell runner 时，
会引入隐式 PowerShell 能力要求，并经 `runOnSameAgent=true` 排除整链上的无此能力 Agent。
因此即使本轮 pyAutomation 名称策略含 Linux `DefaultAgent`，它在线、启用、空闲仍不代表可调度。
runner 与清理命令是不同层：Python runner 包装 Windows PowerShell 清理调用可保留清理行为，
而不引入 PowerShell runner 的隐式能力门；不等于 Linux 获得 Windows 编译能力或线上配置已更新。
</memory>

<memory category="troubleshooting">
`refresh_review()` 的无 shelf 校验在写库前返回错误：不启动新轮、不改变原 AI 状态，也不取消在途 job。
因此“更新报错后仍分析、随后出分”可来自原轮继续执行，不代表刷新成功，也不能直接归为前端卡死。
原 Flow 即使在 Sync/Unshelve/编译/TaskAiReview 均未执行前被取消，原 job 仍可能经 backend fallback 出分；
`ai_result_source=backend_llm` 可与 `chain_failed=true`、`compile_status=skipped` 并存。
按 refresh 请求时间、job/Flow 与 activity/结果来源核对轮次；此分数不证明更新后的代码已经评审或编译。
</memory>

<memory category="core-rules">
两个容易混淆的准入语义：① `make_decision` 的作者分支先于指定 reviewer 授权校验，
所以指定他人 reviewer 不会禁用 self-approve；开关开启且当前轮 AI done、风险低于门槛时，
作者仍能自批。② 纯二进制/无文本 diff 可不调用 LLM 而短路为
`ai_status=done, risk_score=0, ai_verdict=null`；这表示“无可分析内容”，不是模型批准，
却会满足 self-approve 的 AI done/风险条件。system auto-approve 仍受“无指定 reviewer”等独立门限制。
</memory>

<memory category="common-patterns">
`RequestReview.py` 的本地 watcher 只靠 HTTP 轮询发现 Review 状态变化；飞书卡片/消息只是通知副作用，
不会唤醒 watcher 或触发本地拉新。因此“飞书已送达”不能作为作者 workspace 已刷新/收口的证据，
仍应以后端 Review 状态及 watcher state/log 为准。
</memory>

<memory category="common-patterns">
严格评审的 AI-ready 私聊复用普通 reviewer 就绪通知出口：AI 分析定案后，从实时配置加入全部 jury 成员，
与指定 reviewer 重合时按用户去重，并排除作者、跳过无飞书 `open_id` 的成员。TeamCity callback 与
backend LLM fallback 汇聚到同一出口；非 strict 不扩展 jury 收件人，通知失败仍只记日志而不影响业务状态。
</memory>

<memory category="core-rules">
混合 Stream shelf 的提交映射不能由 Review branch、文件多数派或 depot 前缀推导；stream client 的
`import+` 可让同一 shelf 跨多个 depot 根。权威解析链是 `change -o <CL>` 的 Client →
`client -o <source_client>` 的完整 Stream，再创建或复用绑定同一 Stream 的 bot client；只设置
`Stream`、不手写 `View`，并用该 client 的 `p4 where` 校验全部 shelf 文件。client 存在性要用
`clients -e` 判断，因为 `client -o` 对不存在的名称也返回模板；生产 236 是非 Unicode server，
连接 charset 必须留空。`submit -e` 直接消费 shelf、无需 sync，此 client 只是 Stream 映射载体。
</memory>

<memory category="troubleshooting">
P4Python 执行 `submit -e` 时，逐文件原因可能只在 `run()` 返回的 info 字符串中，`errors/warnings`
和默认异常对象只保留汇总，抛出后还会丢失返回值。需要临时使用 `exception_level=0`，同时采集
返回值、`errors`、`warnings`，以 `errors` 非空判失败，并在 `finally` 恢复原级别；stream fallback
不能只匹配异常文本中的 `file not mapped in stream`。
</memory>

<memory category="common-patterns">
AI Review 的 workspace→服务器 diff 不能用 `p4 diff2`：它只比较两个 depot revision，不读取本地 merged 内容。
`p4 fstat` 用于核对 depot/client/have 映射；`p4 diff -du <clientFile>` 比较当前文件与 have revision，
仅在 have 与本轮固定 baseline 一致时适用。显式 baseline 的比较沿用 [MainDev 工具链](references/maindev-toolchain.md) 中的 `p4 print` 路径。
</memory>

<memory category="core-rules">
`pl-review` 的放行/携带者无责与严重度正交：“本 CL 无需处理”不是降级依据。全目录扫描把 depot 外
的备份 xlsx 写入 `dt_metadata.json` 属管线快照污染，至少 `medium`；明确适用的 `high/重要` 规则保底
`high`，引用、否定、示例不触发提级。severity 与总分独立，MainDev Publish、后端 `tc_callback` 与
LLM fallback 必须统一按最终严重度约束风险分下限，既防 high finding 配低总分，也防按文件数聚合稀释高风险。
</memory>

## 标准排障流程

### 1. 建身份表

至少记录：`review_id`、原 shelved CL、当前/提交后 CL、branch/stream、Flow build ID、Sync/Unshelve/Build/Review Task build ID、实际 Agent、callback 中的 review_id、配置 revision。发现用户给出的对象不匹配时，先纠正配对，再分别分析。

### 2. 拉两条时间线

- 业务侧：review 创建、AI job 各 stage、compile_started/finished、tc_callback、AI fallback、决策、submit job、P4 收口。
- TeamCity 侧：真正排队、snapshot 前置等待、每个节点与 step、Pi 消息级空档、artifact publish。

把每个长空档的“上一动作、下一动作、负责组件、是否有 token/tool 输出”写清楚。不要把 snapshot chain sequencing 误报为 Agent starvation。

### 3. 按证据逐层归因

优先级：

```text
本轮 runtime/DB/activity/TC REST/agent log/artifact
  > 当前部署版本与 P4 have/head
  > 当前源码与模块 SKILL
  > 计划、历史笔记和旧事故记录
```

`pi_session.jsonl` 的消息时间、token 数和 tool call 能区分“模型/网关等待”与“工具扫描”；`runner_manifest.json` 能区分 Memory bootstrap、Pi 进程、turn guard 和 timeout；`merge_result.json` 与 provenance sidecar 能判断输入是否可信。

### 4. 只补必要的机器证据

先由拥有源码的 `ws:` worker确定要验证的变量，再去精确 `@agent` 读取日志、版本或 artifact。不要把整个代码调查重复派给构建机，也不要因为本地等待中断而重复 A2A dispatch。

### 5. 报告结论边界

区分：

- **已证实机制**：有时间戳、日志、artifact 或源码分支直接支撑；
- **最可能归因**：例如 proxy 进程在线但缺上游 request history，只能定位到“网关或其上游”；
- **仍缺证据**：明确需要哪个 host、哪个时间窗、哪个日志/API；
- **不属于本问题**：如另一 Review、另一 Agent 的版本偏差。

## `ws:` 与 `@agent` 快速规则

- `ws:autoserver-deveops`：pyAutomation backend/frontend、TeamCity DSL、P4V/DevOps 工具、informer 的源码分析与修改。
- `ws:maindev`：`Tools/AiReview/**`、`pl-review`、MainDev 侧测试和 P4 源码修改。
- `@auto-server`：生产 Flask/DB/Redis、TeamCity server、build-api-proxy、服务日志、部署版本和线上健康。
- `@winbuilder…`：实际 TeamCity agent 用户、workspace、Pi/Node/Python/P4 版本、进程、agent 日志及本地 artifact。

`ws:` 不是远程机器名，`@agent` 也不是 workspace。完整路由、安全和命名约束见 [workspace-agent-routing](references/workspace-agent-routing.md)。

## 修改原则

- 修改前现场核对 P4 opened/head/shelf，区分现行源码、pending CL 和历史计划；不要覆盖并行改动。
- 跨 DevOps/MainDev 的变更分别在对应 workspace 实施、测试并建立各自专用 pending CL；未经明确授权不 submit、不部署、不触发真实 Review。
- 不靠 prompt 声明“只读”代替工具/路径/凭证边界；不打印 callback、API key、P4 密码或完整配置。
- 生产修复先用隔离探针复现真实机制，再做最小变更和真实关键阶段验证；测试绿不等于构建机 headless 环境可用。

## 交付格式

```text
对象映射：Review / CL / Flow / Task / Agent / revision
时间线：业务侧 + TeamCity 侧，最长空档及上一动作
结论：根因、贡献因素、明确排除项、置信度
证据：API/日志/artifact/源码路径，全部脱敏
处置：立即恢复、代码修复、部署/回滚与风险
验证：本地/隔离/构建机/线上分别通过了什么，哪些未验
变更：workspace、测试结果、pending CL；未获授权的动作明确未做
```

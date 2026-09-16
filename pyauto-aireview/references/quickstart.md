# AI Review 五分钟上手

共性约定入口：[pyauto-shared](../../pyauto-shared/SKILL.md)。这页帮助定位，不代替本轮源码/运行时事实。

## 先看什么

1. [主链图](diagrams/lifecycle.mmd) 看组件交接；[架构](architecture-lifecycle.md) 看分支条件。
2. [状态图](diagrams/status-axes.mmd) 区分“编译通过、AI done、人工 approved、P4 submitted”。
3. 带着实际问题看 [失败图](diagrams/failure-routing.mmd) 和 [诊断参考](diagnostics.md)，不要一次读完所有参考。

`.mmd` 是可编辑源；预览由 Mermaid 工具生成，不另维护一份嵌入代码。所有图均为机制摘要：主链省略管理/重开等支线，状态图不是全部合法转换枚举，失败图不承诺修复已部署。

## 六个对象

| 对象 | 用来回答什么 | 易错点 |
|---|---|---|
| Review ID | 哪个业务对象 | refresh/reopen 可复用，仍需区分轮次 |
| 原/当前/提交后 CL | 审什么、最终提交了什么 | submit 可能 rename，不能按作者/描述猜 |
| Flow build | 哪次外部执行链 | composite 不是实际编译/评审进程 |
| 各 Task build | 哪个步骤真的执行/失败 | snapshot 依赖报错可能只是级联 |
| Agent + workspace | 在哪里、用谁的环境跑 | 服务账号/A2A cwd/作者 workspace 不等同 |
| callback 代际 | 结果是否属于当前轮 | 只报告白名单身份，不输出 token/nonce |

## 最小首查

对于具体 Review，先只读详情、activities 与 ai_summary：

```text
GET /ai_review/reviews/<review_id>
GET /ai_review/reviews/<review_id>/activities
GET /ai_review/reviews/<review_id>/ai_summary
```

确认当前轮 CL、状态、结果来源和 Flow关联后，再按症状追加：

| 症状 | 下一份决定性证据 | 去哪里 |
|---|---|---|
| 没有新 build | AI job stage/claim/kick/tc_inflight | backend `ai_worker.py`，不是先查 Agent |
| build 排队或慢 | 前置依赖 finish、本 Task start、session/manifest | TeamCity，再按需补真实构建机 |
| 普通 FATAL 被叫 AS warning | Collect 原错误、发布分支、本轮报告身份 | DSL + Collect/Publish，见工具链参考 |
| TC 绿色但没有结果 | result verdict、callback 是否 applied | Publish + backend activity |
| approved 后未提交／原 CL消失 | 本轮 submit job、P4明确回执及只读对账 | submit worker/P4，未知不重试或猜 CL |
| 服务器完成但作者本地未更新 | watcher state/log 与 HTTP 观察状态 | 作者客户端，不是飞书送达状态 |

## 源码与运行时

- 后端入口：`ws:autoserver-deveops` 的 `pyAutomation/backend/server/applications/ai_review/SKILL.md`。
- DSL：同 workspace 的 `Teamcity_PLN/SKILL.md` 与 `TaskAiReview.kts`。
- 工具：查看 [review-toolchain](review-toolchain.md) 和实际 Task 的三入口；迁移期间区分执行工具根、MainDev 被审根、产物根。
- 规则：MainDev `pl-review` 及模块规则，不因为工具迁移而迁移。
- 生产服务事实：auto-server；构建账号/环境事实：本轮精确 WinBuilder。完整路由见 [workspace-agent-routing](workspace-agent-routing.md)。

## 三句防误判

- `risk=0`、`exit=0`、`HTTP 200`、`TC SUCCESS` 都不能单独证明模型批准或提交成功。
- Collect 失败、AS warning 证据不可用和真实 AS warning 命中分开；改分类不等于放宽保护。
- `error/skipped` 可能触发 fallback；定案 `reject` 与编译错误模型分析也有不同短路契约，不能凭一个结果承诺零 LLM。

找到请求目标和最小验收的决定性证据后停止；不以“再顺便查一个”扩展到所有系统。

---
name: pyauto-shared
description: pyAutomation / py_automation 各系统共性知识、经验与导航。用户泛称 pyAutomation、询问系统划分/上手/跨系统故障、找不到责任模块，或涉及共享的 Flask/Vue、任务队列、回调、配置继承、P4 与数据库一致性、源码和运行时路由时使用。各 pyauto 领域技能链接此入口并按需读取共性参考；明确 AI Review 使用 pyauto-aireview，TeamCity 使用 teamcity-tool，部署使用 auto-server-*-deploy，不用总入口替代领域规则。仅把跨系统稳定机制收进共享知识，不收一次性事故或未经核实的线上状态。
compatibility: Flask, Vue, SQLAlchemy, Perforce, TeamCity, Orca workspace routing, A2A
---

# pyAutomation Shared

这里是各系统的共性层，不是全部业务说明书。**领域入口 → 本页 → 所需共性参考**；不要求每次任务先加载整套平台资料。

## 选择入口

| 问题 | 入口 |
|---|---|
| 不知道属于哪个系统，或跨多个系统 | [系统目录](references/system-catalog.md) · [边界图](references/diagrams/system-map.mmd) |
| AI Review、shelf、warning 门禁、评审到代提交 | [pyauto-aireview](../pyauto-aireview/SKILL.md) |
| TeamCity 参数、构建链、Agent、排队或服务 | [teamcity-tool](../teamcity-tool/SKILL.md) |
| 构建日志 → UE commandlet／VS 调试参数 | [teamcity-extract-commandlet](../teamcity-extract-commandlet/SKILL.md) |
| 后端／前端／全栈部署 | [backend](../auto-server-backend-deploy/SKILL.md) · [frontend](../auto-server-frontend-deploy/SKILL.md) · [full stack](../auto-server-deploy/SKILL.md) |
| LLM 中转、调用记录、用量、网关故障 | [build-api-proxy](../build-api-proxy/SKILL.md) |
| Agent 平台、飞书助手、P4 校验等尚无独立共享技能的系统 | 从系统目录找到 owning workspace 的模块文档，不套用 AI Review 状态机 |

## 共性知识按需读

| 遇到的边界 | 共性参考 |
|---|---|
| UI、API、job、外部执行互相“打架” | [身份、状态与证据](references/common-practices.md#身份状态与证据) |
| callback、重复任务、进程重启、跨系统落库 | [异步与外部副作用](references/common-practices.md#异步与外部副作用) |
| shell 正常但服务失败，配置／版本不一致 | [配置与部署事实](references/common-practices.md#配置与部署事实) |
| 去哪个仓或哪台机器执行 | [所有权与执行边界](references/common-practices.md#所有权与执行边界) |
| 测试、脱敏、提交和验收 | [验证与交付](references/common-practices.md#验证与交付) |

## 最小工作路径

1. 根据业务对象和症状选领域；不凭同一主机、域名或“任务失败”认定同一系统。
2. 记录稳定业务 ID、当前轮次、外部执行 ID；先用最小 API/活动/日志证据定位责任层。
3. 源码问题进入 owning workspace；机器状态进入目标运行时。两端只传目标、约束和必要证据。
4. 独立读取批量执行；请求目标和最小验收有决定性证据即停止，相邻问题只报告。
5. 分开报告源码、部署与本轮运行事实。开发完成不自动授权发布、重跑或修生产数据。

## 共性知识的准入

适合写这里：被多个系统使用的稳定约定、共用基础设施边界、可复用根因与诊断方法。

仍放领域技能：AI verdict、jury、Review 代提交策略、Agent task 生命周期等业务特有语义。不能把一个系统的重试预算、超时或状态名推广给所有系统。

仍放个人记忆／plans：具体事故编号、临时 CL、一次性环境适配、个人偏好、待上线进度和未证实假设。

新增系统技能时：

- 在开头链接 `../pyauto-shared/SKILL.md`，说明需要时读取共性边界；不复制本页全文。
- 在系统目录登记用途、类型、领域入口、源码与运行时归属；没有核实的明确标记。
- 实现细节链接 owning workspace 的模块文档，共性规则在此单点维护。
- 一份材料只维护一个详细源；Mermaid 原图和生成预览不可各自手改。

## 安全底线

- 不复制 key、密码、完整 callback URL、模型原始请求或未脱敏 artifact；共享目录使用逻辑别名。
- 不把文档中的“本机”当执行环境证明，先确认实际 cwd／host／服务账号。
- 不因 UI 成功、HTTP 200、进程在线或 TC 绿色就声称业务闭环成功。
- 未获授权不 submit、部署、重跑业务任务、改生产 DB、发送测试通知或清理活跃 workspace。

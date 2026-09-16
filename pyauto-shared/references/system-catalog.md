# pyAutomation 系统目录

共性知识：[pyauto-shared](../SKILL.md) · [系统边界图](diagrams/system-map.mmd)。每个领域都从共性层继承证据、环境、权限和交付边界；业务规则不互相套用。

## 目录的权威来源

这是一份入口级导航，不是全量接口清单或部署盘点。源码已核注册/路由与模块入口，**未据此确认生产进程、有效配置或机器部署**。

在 `ws:autoserver-deveops` 按需查：

- 后端 `pyAutomation/backend/server/applications/router.py`：实际 RESTX namespace 注册；目录存在不等于已启用。
- 后端 `pyAutomation/backend/SKILL.md`、仓库 `SKILL.index.json` 及最窄模块文档：实现索引；旧模块计数不作为权威。
- 前端 `pyAutomation/frontend/src/router/index.ts` 与 `pyAutomation/frontend/SKILL.md`：页面与权限入口；页面数量不等于后端系统数。
- 通用入口为 Flask namespace 与 `/dashboard` 页面，执行前按当前服务路由确认，不把前端路径加到 API 上。

## 业务领域与公共模块

下表源码均位于 `ws:autoserver-deveops`，除明确列出的 MainDev 边界。后端相对根为 `pyAutomation/backend/server/applications/`；运行事实去 pyAutomation 服务运行时核实，不能从源码认定当前可用。

| 领域／类型 | 用途与典型问题 | 领域入口／权威模块定位 | 特有边界 |
|---|---|---|---|
| AI Review／业务 | shelf 评审、warning、人工决策、代提交 | [pyauto-aireview](../../pyauto-aireview/SKILL.md)；`ai_review/SKILL.md` | Review/job/Flow/Task 独立；游戏规则和被审 workspace 属 MainDev |
| Agent 平台／业务 | Agent 注册、监控、A2A派发、chat、skill选择 | `agent_platform/` 下对应模块 SKILL，尤其 `a2a`、`skill_selector` | A2A task 不是 Review；先查自己的 task/agent/dispatch 身份，不套 Review 表或重试策略 |
| 飞书助手与通知／业务集成 | 助手会话、Pi 调用、消息/通知失败 | `feishu/SKILL.md` 与 assistant 相关参考 | 助手执行与各业务通知出口分开；日志未必在 app.log |
| 构建与分支管理／业务 | 构建投递、分支状态、流水线页面、TC配置 | `teamcity`、`branch_status`、`jenkins_pipeline`、`versioncontrol_pipeline`；前端 branch_status/build_pipeline | pyAutomation 管业务；TeamCity/Jenkins 管外部执行 |
| P4 校验／公共业务能力 | change-submit规则、review gate、校验错误 | `p4_trigger_validate/SKILL.md` | 共享 trigger 不等于 AI Review 专属门禁 |
| P4 定时与提醒／业务 | 自动合并、提交监控、锁提醒 | `scheduler_jobs/p4_auto_merge`、`p4_commit_monitor`、`p4_lock_reminder` 的模块 SKILL | 各任务有自身并发、状态与恢复规则，不统一成 Review submit job |
| Scheduler／公共能力 | 定时触发与补偿、锁/网络监控 | `scheduler_jobs/`；含 teamcity_daily_trigger、p4_lock_monitor、ip_monitor | APScheduler 是执行基础，不是所有领域状态权威 |
| 诊断与代码分析／业务 | 崩溃分析、错误页、代码图 | `crash_error_analysis/SKILL.md`、`codegraph/SKILL.md`、`diff_summarizer/` | 错误分析不必涉及 AI Review |
| 账号与权限／公共能力 | 登录、用户、组、API token、LDAP管理 | `auth/SKILL.md`、`lldap_admin/SKILL.md`、`user_manage/` | 权限来源以当前接口/组策略为准，不能从内网可达推导授权 |
| 服务状态／公共能力 | 健康、busy 与停机前检查 | `server_status/SKILL.md` | HTTP健康、busy和某业务完成是不同问题 |
| 内容/设备/UE辅助／业务集合 | 设备、内容管理、版本与UE工具入口 | `device/`、`content_manager/`、`gameplay_tag_redirects/`、`ugs_pcb/`、`ugs_user_notification/`、`ue_launcher/`、`p4_pl/` | 此处只确认入口集合；具体用途/契约到模块核实，不虚构独立 skill |
| 其他集成／业务集合 | 外部任务、Git和记忆相关入口 | `tapd/`、`tencentgit/`、`memory_agent/` | 接口注册不证明外部服务部署位置或健康 |
| Agent SDK／开发支持 | pyAutomation代理开发SDK及发布 | `pyAutomation/agent-sdk/SKILL.md` | 不等同于同名第三方 Agent SDK 技能 |

`build_notify/`、`dispatching_system/` 在目录中出现但未见注册于已核 router；不直接称其在线、退役或可用。`pyAutomation/computer-cli/` 用途尚未核实。本期不为这些目录新建领域技能。

## 共用工具和外部依赖

| 对象／类型 | 已有入口 | 与 pyAutomation 的边界 |
|---|---|---|
| TeamCity／外部执行系统 | [teamcity-tool](../../teamcity-tool/SKILL.md) | build/step/artifact 是执行事实，业务对象状态由所属系统收敛 |
| UE commandlet提取／工具 | [teamcity-extract-commandlet](../../teamcity-extract-commandlet/SKILL.md) | 只提取日志与本地化参数，不需要 AI Review 状态机 |
| pyAutomation发布／运维 | [后端](../../auto-server-backend-deploy/SKILL.md) / [前端](../../auto-server-frontend-deploy/SKILL.md) / [全栈](../../auto-server-deploy/SKILL.md) | 服务重启、schema和构建生效要独立验收 |
| LLM代理／外部依赖 | [build-api-proxy](../../build-api-proxy/SKILL.md) | 代理请求成功不等于业务结果应用；实际provider/网关以运行参数为准 |
| P4／外部状态权威 | 目标 workspace 的 P4配置与领域 adapter | DevOps Unicode与游戏非Unicode上下文不可混用 |
| MySQL、Redis／数据基础设施 | backend/module文档 | 哪些数据可重建按具体用途确认，不因为用了Redis就全量清理 |
| 飞书、企业微信、TAPD、Jenkins、FTP、OpenObserve、LLDAP／外部集成 | owning module 与对应服务文档 | 源码中的集成不证明现网拓扑，不把所有服务归为 pyAutomation 内部模块 |
| Memory Hub／外部知识服务 | [memory-hub](../../memory-hub/SKILL.md) | 服务部署与业务端调用分开，地址凭证不在总目录复制 |
| RAGFlow／外部知识库候选依赖 | [ragflow](../../ragflow/SKILL.md) | 部署 skill 已有；pyAutomation内同步入口本次未核，不杜撰注册模块 |

## 新系统接入

需要独立高频任务入口、复杂生命周期或明确维护边界时，再建领域 skill；否则先补目录条目/模块参考。

每个新领域的主文件链接 `pyauto-shared`，并在本表登记权威来源。新增共性经验前先确认适用于哪些系统；临时事故和上线进度不要写进这里。

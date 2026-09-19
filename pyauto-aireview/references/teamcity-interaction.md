# TeamCity 交互与 Agent 调度

本页只记录 AI Review 后端与 TeamCity 的投递、队列查询和择机契约。链与工具职责见 [teamcity-pipeline](teamcity-pipeline.md)，业务 worker 见 [backend-module](backend-module.md)；通用 REST 语法见 [teamcity-tool/rest-api](../../teamcity-tool/references/rest-api.md)。源码、已部署版本和具体 build 快照必须分别核实。

## 1. 调度权归属

| 组件 | 负责什么 | 不代表什么 |
|---|---|---|
| 后端 job | 触发一次 Flow、保存本轮关联、tick 观察进度 | REST 接受投递不等于已分配 Agent |
| TeamCity | 解析实际参数、requirements、pool、runner 隐式能力和同机约束，择机执行 | 配置允许某个名称不等于整链兼容 |
| Pi 会话绑定 | Review 对应原生 session UUID 与落盘 Agent | 不能用普通后端分析或清空绑定冒充真续接 |

`teamcity_util.py::get_agents()` 可复用来查询当前 Agent 的连接、启用、授权和占用状态，但它只是瞬时快照，不是预留槽位，也不是整条链的兼容性证明。不要另写一套仅按名称和 idle 判断的调度器。

### 首次评审：优先通用兼容候选

未绑定会话时，`DefaultAgent` 是允许的候选名称策略，不是实际已选机器；与 `override.dep.*.DefaultAgent` 保持一致，让 TeamCity 在执行节点具备运行条件时择机。候选集合由现行配置限定，不能把“此刻空闲的第一台”提前固化成唯一候选。

候选正则不是兼容性校验的替代品。旧快照中的 `^(WinBuilder.*|DefaultAgent)$` 不应直接推广为所有版本的推荐值，也不能据此恢复历史 Linux 链；当前 DSL、具体 build 和实际同机组各自核实。

如果某条链确实不支持通用候选投递，才采用后端 tick 门禁：每 tick 复用 `get_agents()` 并结合兼容性重新判断；无空闲兼容机时返回并等待下一 tick，不阻塞 worker、不提前绑定忙机。查询与投递之间仍可能被其他任务抢占，最终分配以 TeamCity 为准。

### 续评：保留原机与原会话

`ai_worker.py::_trigger_extra_properties()` 读取 `review.pi_session_agent`，将 `DefaultAgent` 和 `override.dep.*.DefaultAgent` 同设为 `^<转义后的原 Agent 名>$`，并携带 `env.AI_REVIEW_PI_SESSION_AGENT`。

原因是 `DevOps/AiReview/AiReviewRunner.py` 依赖原机构建账号下的原生 session 文件；Agent 不符或文件缺失会触发 `SESSION_INVALID`。其他机器空闲也不应默认改选。不要只删正则限制、清空绑定，或用静态分析替代原会话续评。

## 2. 只读交互入口

优先复用 `pyAutomation/backend/server/util/teamcity_util.py`，避免在业务代码散落 REST 调用：

| 入口 | 用途 |
|---|---|
| `get_agents` | 当前 Agent 状态与占用快照 |
| `get_queued_build_snapshot_deps` | 查询具体 queued build 的状态和直接 snapshot dependencies |
| `get_queued_build_compatible_agents` | 查询具体 queued build 的兼容 Agent，而非仅查询 buildType 当前配置 |
| `trigger_build_with_stream` | 已获业务授权的触发入口；只读排障不得调用 |

后两个查询入口属于容量等待判定实现；使用前确认目标分支和部署版本是否包含它们。Composite 自身不占 Agent，不能拿其 Agent 栏或候选列表判断整链资源。

### 身份、依赖与等待原因

以下是相对 TeamCity 服务根的只读查询形态，字段支持以实际服务版本和封装为准：

```text
GET /app/rest/builds/id:<FLOW>?fields=id,buildTypeId,state,status,queuedDate,startDate,finishDate,versionedSettingsRevision(version)
GET /app/rest/buildQueue/id:<BUILD>?fields=id,buildTypeId,state,waitReason,snapshot-dependencies(build(id,buildTypeId,state))
GET /app/rest/builds/id:<BUILD>/snapshot-dependencies?fields=build(id,buildTypeId,state,status,startDate,finishDate,agent(id,name))
```

直接依赖不是完整链：按实际依赖关系递归到链首 Sync，缓存同一轮已查节点，避免重复查询。区分等待前置与等待 Agent，不需要先下载所有日志或 artifact。

### Agent 状态与具体构建兼容性

```text
GET /app/rest/agents?fields=agent(id,name,connected,enabled,authorized,build(id,buildType(id)))
GET /app/rest/agents?locator=compatible:(build:(id:<QUEUED_TASK>))&fields=agent(id,name,connected,enabled,authorized)
GET /app/rest/buildTypes/id:<BUILD_TYPE>/agent-requirements
GET /app/rest/builds?locator=running:true&fields=build(id,buildType(id),agent(id,name),startDate)
```

显式 requirements、单节点 compatible agents、同机组可行集合、当前空闲情况是四种不同证据。需要解释隐式要求时再看具体排队项的 Compatible Agents 页面：

```text
/viewQueued.html?itemId=<BUILD_ID>&tab=queuedBuildCompatibilityTab
```

容量判定实现沿队列依赖找到链首 Sync，再查询它在本轮参数下的兼容候选；这不是任意 DAG 的完整调度算法。不能把不同分支或替代编译路线的全部节点无差别求交集，也不能仅凭共享 Sync 的名称要求宣称整链兼容；同机约束的检查见 [build-chain-parameters](../../teamcity-tool/references/build-chain-parameters.md)。

### 参数白名单与历史占用

从具体 Flow、Sync 和 Task 的 properties/startProperties 提取：

- `DefaultAgent`、`override.dep.*.DefaultAgent`；
- `env.AI_REVIEW_ID`、session 是否存在、`env.AI_REVIEW_PI_SESSION_AGENT`；
- `env.unshelve`、`env.p4_stream`、`env.need_compile`。

排队参数可能仍含公式；启动后再核 effective startProperties。不要输出全量 properties、环境变量、callback URL、token 或 nonce；只从 callback 解析白名单 Review ID。凭证经项目受控配置或 Guard 静默使用，不复制进脚本、命令历史、报告或 skill。

解释“投递那一刻为何没选空闲机”必须补历史，而不是拿当前快照倒推：

```text
GET /app/rest/builds?locator=agent:(id:<AGENT_ID>),sinceDate:(<FROM>),untilDate:(<TO>)&fields=build(id,buildType(id,name),startDate,finishDate,status)
```

时间采用 `yyyyMMdd'T'HHmmssZ`，URL 中 `+0800` 编码为 `%2B0800`。统一 DB UTC 与 TC 时区，核窗口覆盖、分页和跨窗口仍运行的构建；窗口查询不包含的未启动取消项需要按 ID 单查。历史证据不足时标未知。`triggered.type=user` 也可能是后端用所属用户的 token 调 REST，不能据此认定用户在 TC UI 手工点击。

### 按需取日志与 artifact

仅在调度证据不足或需要解释执行失败时，再取对应 Task 的日志和本轮产物，不以 Composite bookkeeping 日志代替失败节点：

```text
GET /downloadBuildLog.html?buildId=<TASK_BUILD>
GET /app/rest/builds/id:<TASK_BUILD>/artifacts/children/Saved/ai_review
```

按 build ID、manifest 和 sidecar 核轮次，不能用工作区里同名文件的最新版本代替本轮 artifact。完整 session、prompt、diff 都可能包含敏感业务信息，按问题最小化读取。

## 3. 如何解读队列

| 观测 | 含义与下一步 |
|---|---|
| Flow 无 Agent，等待链首启动 | Composite 正常行为，转查首个可运行节点 |
| `Build dependencies have not been built yet` | 前置顺序等待，不能直接归因机器忙 |
| `There are no idle compatible agents which can run this build` | 查该节点实际兼容候选、原机会话绑定和候选占用 |
| 其他 WinBuilder 空闲，Sync 精确限制为另一台 | 名称亲和性已排除空闲机，TC 无权换机 |
| 兼容候选为空或均不可用 | 查参数、runner、pool、连接/启用/授权；不能一概叫全忙 |
| 前置已结束，评审仍因同机约束卡住 | 核同机锚点是否曾真正获得 Agent；失败节点未启动与原机忙是两类问题 |

决定性证据通常是：Review 会话绑定 → 本轮 Flow/Sync 有效机器策略 → 首阻塞节点 waitReason → 对应候选在投递时的历史占用。证据闭合后停止，不再逐台机器重复探查。

## 4. Tick、容量等待与超时预算

通用候选投递允许任务先进入 TC 队列，由 TC 随容量释放择机；后端 tick 只观察同一条链，不另选一台重投。若使用后端等待方案，则 tick 每次重查，不能阻塞线程等待。

包含 `_queued_chain_has_capacity` 的后端版本在 composite 仍 queued 时探测链首兼容候选，为确认的容量等待豁免 `COMPILE_TC_TIMEOUT_POLLS`：

| 判定 | 处理契约 |
|---|---|
| 存在可用兼容候选，但尚未获执行容量 | 持续 tick，不因正常等机器耗尽执行轮询预算，不降级静态分析 |
| 无可用兼容候选 | 不套用正常容量等待豁免，保留诊断与既有超时兜底 |
| 查询失败、返回结构不明或兼容性未知 | 不当作“已确认有容量”；容量判定实现保守消耗原预算 |
| 已进入运行或终态 | 回到正常执行轮询、结果/callback 与故障处理 |

`compatibleAgents` 非空不表示现在空闲，也不承诺立刻开工；字段状态需按封装契约判断。函数名中的 capacity 不应被解释为已经预留资源。

链首出列可能是已启动或状态已推进，不能据此断言整链完成、立即降级或重新投递；Composite 状态也不能代替各 Task 的真实执行进度。查询子节点时的出列竞态与业务 Flow 确认不存在须分开处理。

等待旧链结束的 requeue 标记必须使用同一容量等待口径。保留现有 claim/CAS、`tc_inflight` 和 build ID 关联，不因 tick 重入、容量查询或排队过久生成同 CL 的重复链。

后端 fallback 是另一条分析路径，不等于原生 Pi 续接。无兼容候选或探针失败最终触发兜底时，应如实说明结果来源，不能称作原机续评成功。

## 5. 源码与最小验收

目标 workspace：`ws:autoserver-deveops`。

| 源码锚点 | 核查内容 |
|---|---|
| `pyAutomation/backend/server/applications/ai_review/ai_worker.py` | `_trigger_extra_properties`、`_trigger_compile`、`_poll_compile`、`_queued_chain_has_capacity`、`_degrade_compile_wait` |
| 同模块 `service.py::_bind_pi_session_from_tc_callback` | callback 首绑与冲突保留，不能为换机擅自重绑 |
| `pyAutomation/backend/server/util/teamcity_util.py` | 复用认证与队列/Agent 查询封装 |
| `Teamcity_PLN/.teamcity/patches/buildTypes/` | Flow/Sync/Unshelve/Build/AiReview 的实际参数、依赖与 requirement |
| `DevOps/AiReview/AiReviewRunner.py` | 原生会话目录、Agent 校验与 fail-closed |
| `pyAutomation/backend/tests/unit/ai_review/test_agent_dispatch.py` | 首投、续评、容量等待、释放与异常判定的隔离测试 |

最小验收覆盖：

1. 首投仍使用允许的通用候选，续评仍精确回原机；两个机器参数一致。
2. 全忙 → tick 等待 → 容量释放继续，同一 build 不重复投递，正常容量等待不消耗执行预算。
3. 无兼容候选/查询失败不被误判为正常容量等待；旧链 requeue 标记不造成重复构建。
4. 分别记录隔离测试、真实 REST 形态核对、真实全忙到释放的运行验收和部署 revision。

容量等待路径已有隔离测试与只读 REST 形态证据，但本次知识采集所依据的改动未执行真实全忙到释放的端到端构建验收，也未确认已部署。不能把 pending 修改、单测通过或 GET 成功写成线上调度已验证；后续以部署和运行证据更新此边界。

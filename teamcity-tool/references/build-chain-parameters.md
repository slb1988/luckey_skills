# Build chain：参数所有权、解析上下文与验证

适用：多层 snapshot chain 的 Agent 匹配、分支/CL 透传、同机工作区和安全重排。
`override.dep` 的语义适用于 TeamCity 2026.1+；本文的多层行为在 2026.2 验证。
先用 `GET /app/rest/server` 确认实际版本；升级后重新验证参数契约，不把旧版本观察当成永久实现保证。

## 1. 依赖方向与执行方向

```text
依赖声明：Flow → Review → Build → Unshelve → Sync
执行顺序：Sync → Unshelve → Build → Review → Flow 汇总
参数下发：消费者（如 Flow）→ 它直接或间接依赖的前置任务
```

- Composite Flow 不占用 Agent；其 Agent 列为空不能证明实际任务无可用 Agent。
- Snapshot dependency 定义前置关系，不代表“上游完成就自动触发下游”。发起 Flow 才会沿依赖图创建所需前置构建。
- 每条需要共享本地工作区的边都设置 `runOnSameAgent=true`。同机组的候选是各节点兼容条件的**交集**，不是分别任选一台机器。
- 名称/OS/runner 能力、隐式参数要求及项目 Agent Pool 决定兼容性；`connected / enabled / authorized / busy` 决定候选现在能否执行。匹配与空闲是两层问题。
- 将专属能力要求放在专属节点。共享 Sync/Unshelve 不应因为一个 Windows 调用方就增加全局 Windows 或交叉编译工具链要求。

当前 PLN Windows 评审链的实际配置 ID：
`PLN_TaskSyncCyanCookDepot → PLN_TaskUnshelve → PLN_TaskBuildUEWindows → PLN_TaskAiReview`。
Flow 为 `PLN_FlowAiReview`；CodeGraph 的共享 Linux 编译链仍独立存在。
当前 Win64 评审不需要 `env.LINUX_MULTIARCH_ROOT`，该变量属于历史 Linux 交叉编译方案。

## 2. 先定义每个参数由谁提供、在哪里解析

| 参数类别 | 提供者 / 解析位置 | 传递方式 |
|---|---|---|
| 分支、shelved CL、是否编译、模型、回调地址 | 触发方提供，Flow 统一向消费者下发 | `override.dep.<target>.<name>`；源值应在 Flow 上确定 |
| Agent 名称策略 | Flow 或专属 Task 定义；任务 requirement 使用 | 字面正则，例如 `^WinBuilder.*$`，不依赖已选中的 Agent |
| 盘根、Agent 名称、组合出的 workspace 路径 | 实际执行任务的 Agent | 保留目标上下文表达式，必要时定向 `reverse.dep` |
| P4 client Root、运行后产生的路径/结果 | 执行阶段读取并验证 | 校验后供本任务后续步骤使用；不可倒流为已经运行的 Sync 的输入 |

业务分支与 CL 的权威入口只有一个。中间 Task 消费这些值，而不是再次覆盖同名参数。
在 2026.2，多层同时写同一输入的 `override.dep.*` 不能视为自动递归求值的函数调用：
语法合法、配置生成成功，仍可能得到自引用或默认值。换成精确 target 也不等于验证了逐级 relay。
单一入口直接覆盖所有必要消费者，参数来源才可追踪、可断言。

### `override.dep` 与 `reverse.dep` 的职责

| 属性 | `override.dep` | `reverse.dep` |
|---|---|---|
| `%...%` 的处理 | 在声明该 override 的配置上下文中尝试解析，再向前置任务传递 | 保留表达式，交给接收任务的上下文解析 |
| 接收方没有同名参数 | 忽略该目标，不自动创建 | 可以创建目标参数；可能影响 suitable-build 复用 |
| 典型用途 | 已确定的业务输入 | 必须延迟到目标 Agent 上解析的路径公式 |
| 关键前提 | 消费者声明输入，发送方引用可解析 | 表达式引用的每个名字都属于接收方可获得的值 |

源引用未解析时，`override.dep` 也可能原样传递占位符；它不是跨任意多层的解析保证。
`reverse.dep` 不是“禁止使用”，也不是“默认更安全”：选择依据是**应在哪个上下文解析**。
不使用 `%reverse.dep.*.X|fallback%` 充当未经验证的通用 fallback 语法；需要默认值时显式声明普通参数。

## 3. 配置配对：Flow 输入与任务声明

以下是参数片段，放入已有配置的 `params` 中，不是完整 buildType 定义：

```kotlin
// Flow：分支/CL 的统一业务入口；其他业务输入沿用同一模式
param("env.p4_stream", "MainDev")
param("env.unshelve", "0")
param("DefaultAgent", "^WinBuilder.*$")
param("override.dep.*.DefaultAgent", "^WinBuilder.*$")
param("override.dep.*.P4Stream", "%env.p4_stream%")
param("override.dep.*.env.p4_stream", "%env.p4_stream%")
param("override.dep.*.env.unshelve", "%env.unshelve%")
```

消费者必须声明其实际接收的键。当前链的配对如下：

| 消费者 | 分支输入 | CL 输入 | 默认值的作用 |
|---|---|---|---|
| Sync | `P4Stream`、`env.p4_stream` | 无需用于 sync | 声明输入供覆盖；不能拿默认 MainDev 证明透传正确 |
| Unshelve | `env.p4_stream` | `env.unshelve` | `0` 仅表示明确要求跳过 unshelve |
| Windows Build / Review | `P4Stream` | `env.unshelve` | 本地默认输入，不是对前置任务自动转发的承诺 |

所有带名称约束的任务还需声明 `DefaultAgent`，其默认值按该任务自身允许的调用方选择。
要求“任意 WinBuilder”时使用 `matches(teamcity.agent.name, ^WinBuilder.*$)` 的语义，
不是 `equals`；具体 requirement 及有限白名单见 [agent-pinning.md](agent-pinning.md)。

非默认分支/CL 的业务请求从 Flow 发起。独立 Task 默认空跑成立，不代表其自定义参数会传遍前置链。
若要增加一个独立业务入口，应明确它向所有消费者传递的契约，并单独覆盖非默认参数测试；
不要为此在原链所有中间层堆叠同名转发。

## 4. 工作区公式在目标 Agent 上成立

```text
P4 client 名称 = <实际 Agent 名称>_<本次 stream>
Windows 预期 Root = <该 Agent 的 NODE_WORKSPACE>/<client 名称>
```

例如两个不同 Agent 可分别得到 `F:/WinBuilder1_MainDev`、`D:/WinBuilder4_Stable`。
盘符来自各自 Agent，不是 Flow 的固定值。项目或模板里的空 `env.NODE_WORKSPACE`
也是一次显式赋值，会遮蔽 Agent 的真实盘根；检查整个继承层级，而不是给所有机器写同一盘符。

专属 Windows Task 向共享 Sync 传递路径的配对片段：

```kotlin
// Windows Build / Review 自己使用的公式
param("P4SyncRoot", "%env.NODE_WORKSPACE%")
param("P4ExpectedRoot", "%env.NODE_WORKSPACE%/%teamcity.agent.name%_%P4Stream%")

// 定向 Sync；保留完整公式，在 Sync 自己的 Agent 上解析
param("reverse.dep.PLN_TaskSyncCyanCookDepot.P4SyncRoot", "%env.NODE_WORKSPACE%")
param("reverse.dep.PLN_TaskSyncCyanCookDepot.P4ExpectedRoot",
      "%env.NODE_WORKSPACE%/%teamcity.agent.name%_%P4Stream%")
```

这里不能把目标值写成 `%P4ExpectedRoot%`：那会引用接收方的同名参数本身。
也不能用尚未选定的 Agent 名称决定 `DefaultAgent`；调度策略和调度后的路径是不同阶段的输入。

工作区不变量：

```text
Sync 操作的 engine Root
  = Unshelve 的 client Root
  = Build/Review 核验后的 Root
  = Windows 预期 Root
```

Sync 可以在独立 DevOps hashed checkout 中运行 P4 helper；并不要求链上所有
`checkoutDirectory` 字符串相同。Build/Review 使用 MANUAL checkout 时核验其 checkoutDir
也等于 engine Root；不要把 DevOps 自动 checkout 改指向用户的 UE 工作区。

现有 client 的 Root 不符合公式时，保持校验失败，不自动改写 client spec、不猜 fallback、不扩大清理范围。
目录生命周期另见 [checkout-dir-auto-clean.md](checkout-dir-auto-clean.md)。

## 5. 排障顺序：从具体构建到实际执行值

以某一次 Flow build ID 为起点，而不只查看配置页。以下路径中的 REST 资源均在 `/app/rest` 下，
认证方式见 [rest-api.md](rest-api.md)。

1. **展开完整依赖图**：读取配置的 `snapshot-dependencies`，递归访问 `source-buildType(id)`；
   同时对本次构建递归读取 `snapshot-dependencies(build(id,buildType(id)))`。REST 返回的直接依赖列表不能当成完整链。
2. **分开查看兼容性与可执行状态**：核对每条同机边、每个节点的 requirements、Agent Pool、Agent 状态；
   找到最早未启动/失败的实际任务，不能把 Flow 的 Agent 空白或链尾等待当作根因。
3. **查看隐式要求**：`agent-requirements` 只含显式配置，不覆盖 runner 或参数引用产生的隐式条件。
   队列 UI 的 Compatible Agents 详情能指出缺哪个参数、被哪个参数/步骤引用。
4. **追踪参数所有权**：比较 Flow 输入、Task/项目/模板声明、各层 `override.dep`/`reverse.dep` 和队列参数。
   对每个关键键回答“谁写入、在哪里解析、接收方声明了什么”；既查缺失，也查空值遮蔽与重复写入。
5. **核实配置版本**：读取实际 build 的 `versionedSettingsRevision` 与项目 versioned-settings 状态；
   REST/UI 保存、写回 VCS、服务器应用、新 build 采用该 revision 是不同环节。
   “not read only”“generated settings from cache”是设置选择信息，单独出现不等于缓存错误；不要据此清缓存/重启服务器。
6. **核实执行值**：任务实际启动后查 `startProperties`、生成命令和阶段输出；运行中/完成后的
   `resultingProperties` 用于核实 service message 更新。排队时仍带公式的字段不是实际 Agent 报告值。

关键查询：

```text
GET /app/rest/buildTypes/id:<BT>/agent-requirements
GET /app/rest/buildTypes/id:<BT>/parameters
GET /app/rest/buildQueue/id:<BUILD>/compatibleAgents
GET /app/rest/agents?locator=compatible:(build:(id:<BUILD>))
GET /app/rest/builds/id:<BUILD>?fields=id,state,status,agent(name),versionedSettingsRevision(version),startProperties(property(name,value))
GET /app/rest/projects/id:<PROJECT>/versionedSettings/status

# Web UI 路径，不在 /app/rest 下；用于查看逐 Agent 的隐式要求
GET /viewQueued.html?itemId=<BUILD>&tab=queuedBuildCompatibilityTab
```

配置级 compatible agents 与具体排队 build 的候选可能不同；还需区分单节点详情与同机组交集，
以及 API 默认是否过滤 disabled Agent。有候选但未启动时继续查占用、禁用、依赖、Pool/调度限制，
不能直接推断“旧快照”或“参数问题”。参数结果仅输出白名单业务字段，遮蔽 token、密码和回调 URL 中的凭据。

## 6. 验证契约：隔离探针 → 真实关键阶段

隔离探针应是无 VCS、无 P4、无编译、无真实回调和通知的 echo-only 链，只打印白名单参数。
保留生产的参数/依赖/同机关系；没有复制这些关系的单步脚本不能验证 chain。

创建探针时，REST `POST /projects/<locator>/buildTypes` 不保证应用请求里全部复杂子资源。
分别设置并读回断言：`parameters`、`steps`、`agent-requirements`、`snapshot-dependencies`、
`settings/buildConfigurationType`；确认非 composite 节点确有 echo step，Flow 确为 composite。
Snapshot dependency 的请求需要 `source-buildType`，不只传 `id`：

```json
{
  "type": "snapshot_dependency",
  "source-buildType": {"id": "Probe_Sync"},
  "properties": {"property": [
    {"name": "run-build-on-the-same-agent", "value": "true"}
  ]}
}
```

对不熟悉的端点，先查本机 `/app/rest/swagger.json`，创建后 GET 验证，再运行探针。
构建 SUCCESS 只代表 echo 执行成功，**验收对象是打印出来的值**：

| 验证维度 | 断言 |
|---|---|
| 输入保真 | 每一消费者的 stream/CL 等于本次触发值；特意使用非默认分支与非零 CL |
| 跨 Agent | 至少覆盖不同盘根的两台 Agent；名称、盘根、组合 Root 都来自实际机器 |
| 分支矩阵 | 对支持的入口覆盖 MainDev/Stable 等不同分支，不能只跑默认空 CL |
| 同机一致性 | 整个同机组的 Agent 一致；engine Root、编译路径和产物路径一致 |
| 完整解析 | 关键执行字段没有残留占位符/意外空值；没有占位符但落回默认值同样不通过 |
| 路由保留 | WinBuilder 正则不放宽到其他机器，共享任务不被添加专属全局能力门 |

探针通过后再在用户授权范围运行真实链，至少验证 Sync、Unshelve 成功及实际 Root/CL，
然后分别报告编译与 AI 阶段状态。**匹配成功 ≠ 参数正确 ≠ Sync/Unshelve 成功 ≠ 全链成功**。
保留脱敏验证记录，再删除自己创建且已无在途任务的临时项目；不清理无关配置。

## 7. 安全重排：配置快照与业务记录必须一致

已入队的构建携带自己的设置/参数快照；不要假定修改当前配置会更新旧队列。
先核实新配置已应用且目标构建仍需要运行，再决定重建哪些构建，不一律取消整台服务器队列。

由业务平台触发的链有两份关联状态：TeamCity build ID 与业务侧轮询/回调记录。
直接手工复制一条 Flow 但不更新业务侧关联，可能留下继续轮询旧 ID 的记录。

PLN 评审平台的原生入口（按部署中的状态机核验后使用）：

- 已失败且 AI job 已结束、Review 仍进行中：`POST /ai_review/reviews/<id>/trigger_ai` 重新排队，由平台保存新 build ID。
- 在途 job：原生 `refresh` 可标记旧链完成后补跑并保留旧 build ID；如果需要取消尚未启动的旧链，
  先确认该标记/保留语义已经生效，再在授权范围内取消，等待平台生成新链。
- 不自动重开 rejected/archived/submitted 等终态，不自行清库或强改审核结论。
  重排前重新读取状态，不能复活已经被用户取消、替换或结束的请求。

### 交付格式

```text
匹配：实际可用 Agent / 尚未满足的条件
参数：实际 stream、CL、Root；配置 revision
执行：Sync / Unshelve / Build / Review 各自的 state + status
重排：旧 → 新 build 关联，保留的业务记录；未处理的终态
边界：仍在运行或尚未验证的阶段，不把 running 的 SUCCESS 当作最终通过
```

协议参考：[TeamCity — Use Parameters in Build Chains](https://www.jetbrains.com/help/teamcity/use-parameters-in-build-chains.html)。

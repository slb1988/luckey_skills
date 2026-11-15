# MCP tasks 终端后台化（2.1.319 引入）

> 分析对象：Claude Code 2.1.321（Bun 编译单文件二进制，提取产物见 `C:\Users\admin\AppData\Local\Temp\claude-re\v21321\`）。
> 行号说明：本 feature 的实现几乎全部位于**未被 tree-sitter 包装模块捕获的 chunk 文件**里（`claude-app.js` 中 `MCP_TASK`、`/tasks`、`Earlier in this session` 均为 0 命中），因此下文行号一律指**原始 `bundle.js` 的行号**（每个 chunk 一个超长压缩行）；「美化为」指分析时用 jsbeautifier 单独展开的临时副本。模块名用 Bun chunk 文件名（如 `chunk-rbvy6xp2.js`），它们从 import 语句反查得到。

## 功能概述

当 MCP server 把一次 `tools/call` 作为**服务端任务**（MCP tasks 扩展，本版本对应 SEP-2663 协议形态）执行时，Claude Code 不再阻塞等待，而是：

1. 立即把该调用登记进**与 subagent/后台 shell 共用的 taskRegistry**（任务类型 `mcp_task`）；
2. 立即返回一条占位 tool result 告诉 Claude「已转为后台任务 `<id>`，完成后会收到通知」；
3. 后台由 **drive 循环**按服务器给的 `pollIntervalMs` 轮询 `tasks/get`，处理 `input_required`（弹 elicitation 对话框收集用户回答后 `tasks/update` 提交），终态（`completed/failed/cancelled`）时把结果以 `task-notification` 消息注入会话让 Claude 看到；
4. 任务可在 `/tasks` 列表查看/停止（`MCP_TASK.kill` 处理器），sidecar 文件保证 `--resume` 后可恢复或补投结局通知。

同一版本还包含一条并行的「客户端自动后台」机制（`callMcpToolWithAutoBackground`）：即使服务器不支持 tasks 扩展，本地计时器（默认 120s）或「有消息要送达」触发也会把慢调用转后台。两者通过 `share.becameTask` 标志衔接：一旦服务器返回了真任务，自动后台的通知路径即让位给 SEP-2663 驱动。

## 开关与配置

| 开关 | 类型 | 作用 | 锚点 |
|---|---|---|---|
| `CLAUDE_CODE_DISABLE_MCP_TASKS` | bool env | 总开关；置 1 完全不启用 MCP tasks | bundle.js L8633 `PR()`；注册表 L116:331 |
| `CLAUDE_CODE_DISABLE_MCP_TASK_BACKGROUND` | bool env | 服务器建任务后**不转后台**，在 tool call 内联轮询等待结果 | L8633 `rvs()`；调用点 L38263 |
| `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS` | int env | 客户端自动后台计时器覆盖值（0 = 关计时器；夹紧到 [0, 2^31-1]） | L42026 `le()`；注册表 L116:970 |
| `CLAUDE_AUTO_BACKGROUND_TASKS` | bool env | 允许非交互会话也自动后台 | L42026 `le()`/`De()`；L38263 回退分支 |
| `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` | bool env | 全局禁后台 → 自动后台毫秒数归零 | L6003 `kSe()`/`If()` |
| `MCP_SDK_GENERATION` | env (`v1`/`v2`) | 强制选择 MCP 运行时代际；非法值告警并忽略 | L8486 `iN()` |
| statsig `tengu_glowing_lark` | flag | MCP tasks 主门控；**默认值 = 入口为 `cli` 且非 `CLAUDE_CODE_REMOTE` 且非 CCS 租户**（即无 flag 拉取时本地终端默认开，对应 changelog「without feature-flag fetching」） | L8633 `PR()`；`lGt="cli"` 见 L271 |
| statsig `tengu_mcp_task_worker_wake` | flag（默认 false） | 任务后台化时武装「worker wake」调度器 | L8633 `nFn()`；L38267、L42093 |
| statsig `tengu_mcp_auto_background` | flag（默认 true） | 自动后台默认 120000ms 是否生效 | L42026 `le()` |
| statsig `tengu_brindle_causeway` | flag（默认 true） | MCP 运行时默认代际 = v2 | L8486 |
| 「tengu_gleaming_creek server list」 | 远程环境服务器清单 | 仅在 `CLAUDE_CODE_REMOTE && ENVIRONMENT_KIND=anthropic_cloud 等` 下按 host allow/deny 关闭某些服务器的 tasks | L4944 `KTs()`；L38267 日志「Tasks are off for this server…」 |

## 实现架构

### 代际：v1 / v2 双 MCP 运行时

- `iN()`（L8486，`chunk-sa9e2cxe`）按 `MCP_SDK_GENERATION` env → statsig `tengu_brindle_causeway`（默认 true→v2）选择代际，结果 latch。
- `chunk-nhr07scz.js`（L26875）是懒加载访问器：`mcpClientModule()`/`mcpSep2663TaskBinding()`/`mcpTaskWatcherModule()` 等按代际 `import.meta.require` 不同 chunk，并带 `MCP_TREE_ID` 自校验「tripwire」（遥测 `tengu_mcp_tripwire`）。v1 = `chunk-v3fdm6wh.js`，v2 = `chunk-v4c37pc6.js`；watcher：v1 = `chunk-sh1cf6kt.js`、v2 = `chunk-d554jg94.js`。
- v1 内含的是旧 **2025-11-25** 草案协议（L21775 schema：`tasks/get|result|list|cancel`、`notifications/tasks/status`、task 状态 `working|input_required|completed|failed|cancelled`、`io.modelcontextprotocol/related-task`、tool `execution.taskSupport`；L21782 Protocol 类的 taskStore/taskMessageQueue/`requestStream` 轮询；L21789 Server 类 `experimental.tasks`）。**本版本已不再支持该协议的恢复**：`restoreMcpTasks` 把无 `protocol` 字段的旧 sidecar 直接删除（日志明说 "it used the 2025-11-25 tasks protocol, which this version no longer supports; the task was not cancelled on the server"）。
- v2 走 **SEP-2663**：扩展协商键 `io.modelcontextprotocol/tasks`（capabilities.extensions），任务结果 `CreateTaskResultSchema` = `{resultType:"task", taskId, status, ...}`，另有 `_meta["com.anthropic/agent-task"]`（`AGENT_TASK_META_KEY`）携带 `{sessionId?, taskId?, kind?, merged?, modelImmediateResponse?}`。

### 检测与后台化链路

1. **能力声明**（L12101）：v2 客户端能力 = `{roots, elicitation, …extensions:{"io.modelcontextprotocol/tasks":{}}}`（`ays()`，仅当 `PR()` 或 `sessionFollowsTasks`）；`_ut()` 会把「声明 tasks 之前就已列出工具的服务器」的 `_meta` 回显里的 tasks 扩展剥掉（对应 2.1.319「Fixed MCP servers on the older handshake failing to connect… declared an extension that it only uses with newer servers」）。
2. **调用包装**（`composeMcpTool` 的 `call`，L38263 / L38200 两个 fragment）：
   - `Jt = !agentId && taskRegistry !== i4（空调节表哨兵，L6358）&& toolName !== getPermissionPromptToolName()`——仅主线程普通 MCP 工具可后台化；
   - `_n.getMcpAutoBackgroundMs()` 给出计时器（sse-ide/ws-ide、sdk+`disableAutoBackground`、全局禁后台、非交互且无 `CLAUDE_AUTO_BACKGROUND_TASKS` → 0）；
   - 若可后台：组装 `share={becameTask:false}`；**仅当 `!Vt && PR() && !rvs()` 时**才组装 `taskBackground Ut`（即协议级 tasks 只在未禁用后台化时才请求）；调 `_n.callMcpToolWithAutoBackground({run, autoBackgroundMs: Vt?null:_t, share, foregroundCalls, noticeGate, …})`；
   - 回退路径（无自动后台模块/不适用）：`Jt && PR() && !rvs() && MCP_AUTO_BACKGROUND_MS!==0 && …` 时仍设 `Ut`，使 `callMCPTool` 能请求协议任务；
   - `disallowTasks = agentId!==void 0 || (isNonInteractiveSession && Ut===void 0)`。
3. **发起调用**（`callMCPTool` = `jn`，L38267 = `chunk-v4c37pc6.js` 片段）：
   - `Je = disallowTasks || filesRound || isSingleShotPrintSession() || (非交互 && 无 taskBackground)` → 为真则不请求任务；
   - 现代协议 era 且未被 gleaming_creek 排除 → `callTool(…, {allowTask:true})`（files round 另加 `allowInputRequired:true`）；
   - v2 wire codec（L37967）：仅当 `allowTask===true` 且**服务器 capabilities 声明了 `extensions["io.modelcontextprotocol/tasks"]`** 且结果形如 `{taskId, status∈五态}` 才把结果作为 task 返回，否则报 `UnsupportedResultType`。
4. **任务创建返回后**（`Te()` 内）：
   - 若调用已被外层 abort → 立刻发 `tasks/cancel`（5s 超时，常量 `kNt=5000`）后原样返回；
   - 若有 `taskBackground` 且有 registry → `ft()`：**后台化**——`registerOrAdoptSep2663Task`（L39018；若自动后台已占位则 adopt 该条目并改挂 `protocol:"sep2663"`）→ `share.becameTask=true`（自动后台通知路径从此静默）→ `onBackgrounded()` → 可选武装 worker wake（`nFn()`）→ `startSep2663BackgroundDrive` → 返回 `buildSep2663PlaceholderResult` 的占位文本；
   - 否则 → `et()`：**行内等待**——`driveMcpTask` 在本 tool call 里轮询到终态，结果作为普通 tool result 返回（`CLAUDE_CODE_DISABLE_MCP_TASK_BACKGROUND` 的语义即此）。
5. **后台驱动**（`Et`，L39022）：等待/寻找服务器连接（`$t`，默认重连截止 `ze=300000`ms；运输指纹不符/协议 era 倒退/服务器未配置均有专门失败码）→ 调 `driveMcpTask` 轮询 → 失联时按 `be=30000`/`_t=300000`ms 指数退避「慢轮询」，放弃后视 `followAfterGiveUp=!isCcsTenant()` 决定是否继续慢查 → 终态经 `ot()` 结算：更新 registry、写结局 sidecar、注入模型通知、发遥测。
6. **轮询状态机**（`driveMcpTask` = `its`，L39009，`chunk-14haznwn.js`）：请求头 `Mcp-Name: <taskId>`；轮询间隔 `clampPollInterval` = min 250ms / max 30000ms / 默认 2000ms；`working` 继续；`completed/failed/cancelled` 返回；`input_required` 携带 `inputRequests: Record<key,{method,params}>`——逐 key 调 `resolveInputRequest` 收集回答后 `tasks/update {inputResponses}` 提交；服务器拒绝已答 key → `unsupported_input`；连续 5 次轮询失败 → `poll_failed`；abort → 发 `tasks/cancel`（除非 abort reason 是 `TASK_DRIVE_QUIET_STOP` 符号）。
7. **input_required 的服务**（`Hi`，L38267）：`elicitation/create`——form 模式走 `requestDialog` 弹窗；url 模式需 url elicitation 能力；非交互/无对话框抛 `TaskInputUnservableError` → 客户端要求服务器取消任务；`roots/list` 本地应答；其余方法一律「此客户端不服务」→ 取消任务。
8. **取消**（`Ge`，L39022）：校验 taskId 线上界（`mRe=128` / `S4` 正则）→ 按服务器名+运输指纹找已连接客户端 → 要求 `protocolEra==="modern"` → `tasks/cancel`（5s）。`/tasks` 里的停止走 `MCP_TASK.kill`（L34554，`chunk-bgs8yn6t.js`）：abort 两个 controller + `sep2663Cancel()` + 状态置 `killed` + 删 sidecar + `mcp_task_stop` 遥测。

### 客户端自动后台（无协议任务也能后台）

`callMcpToolWithAutoBackground`（`Ie`，L42026）：
- 起子 AbortController 与父级链（`S7`），立刻开始调用；
- 竞速：调用完成 / 「early」（`foregroundCalls` 的 `backgroundNow()`——用户消息到达时由 low-latency-submit 控制器 `ETi()` 触发，L12104/L28032）/ 计时器（`autoBackgroundMs`，null 则无计时器）；计时器到点但 `hasPendingElicitation()` 或 `holdsAutoBackground()` 为真则继续等；
- 转后台：`Icr()` 构造 registry 条目（L38060：`type:"mcp_task"`、`mcpStatus:"working"`、id 形如 `kXXXXXXXX`，描述为 `server/tool`）→ `T.register()` → 挂进度写手（订阅 `mcpCallProgress`，1s 节流更新 `statusMessage` 并推 `LZ` 摘要——与 subagent 进度摘要同一通道）→ 遥测 `tengu_mcp_tool_auto_backgrounded{trigger: timeout|deliver_message}`；
- 完成后 `x()`：更新条目为终态、经 `noticeGate`（`lpr`，hook 忙则排队）注入 `task-notification`（`Fa`，priority `"next"`）。

### 持久化与恢复

- sidecar：`<storageRoot>/<sessionId>/mcp-tasks/mcp-task-<id>.meta.json` 与 `.outcome.json`（L20360；storageV5 或本地文件两路，diskless 会话跳过本地写）。meta 含 `taskId/serverName/toolName/mcpTaskId/pollIntervalMs/spawnedAt/toolUseId/protocol/ttlExpiresAt/transportFingerprint/workerWakeId/cancelReason`。
- 会话启动/恢复入口 `Ohn()`（L28078）：`resetGiveUpsTold`（从会话文本回收已示放弃通知）→ `As()` 把已结束任务的结局通知补投进会话（每次 resume 最多 8 条，passive）→ `restoreMcpTasks`：v2 下 `restoreSep2663Tasks`（L39036）把 parked/新 sidecar 重新登记并重启驱动（`takenUpAgain: after_park|after_restart`）；旧 2025-11-25 sidecar 删除。
- registry 里 sep2663 条目无 abortController 且 sidecar 属于**别的**会话/项目时视为「仍在他处运行」（L20374 `p()`），`/tasks` 的「仍在运行」统计据此过滤；服务器为 sse/http（非 stdio/sdk）且任务不在运行时从运行列表排除（无法原地重连）。

### /tasks 界面

- 命令注册（L10022:721）：`{type:"local-jsx", name:"tasks", aliases:["bashes"], description:"View and manage everything running in the background", immediate:true, thinClientDispatch:"control-request"}`。
- 对话框 `ghn`（L35855）：订阅 taskRegistry 全量 map，按类型分桶（`mcpTasks` = `type==="mcp_task"`），区段常量 `__leader__` / `"System tasks"`(`__self_managed_tasks__`) / `"Earlier in this session"`(`__subagent_history__`)；后者由 `pge(storageV5,…)` 从磁盘读**已完成 subagent** 历史（changelog 2.1.319 同一批）。MCP 行渲染（L41327）：状态（killed→"stopped"，否则 `mcpStatus` 下划线转空格）、`statusMessage`、`polls every Ns`、`input_required && running` → "waiting for your answer in the elicitation dialog"、`protocol==="sep2663" && running` → "runs on the server; survives exiting this session"。页脚在有未答请求时显示 "A request is waiting for your answer"（L41175）。MCP 条目停止走 `MCP_TASK.kill`，详情视图懒加载 `McpTaskDetailDialog`（`chunk-ts3xa2sz.js`）。
- onboarding 文案（L37489）："Run /tasks to see everything in flight. … Subagents also run as tasks — it is all one queue."

### 与 subagent 任务管理的复用关系

- **同一 registry**：任务 map 以 `type` 区分（`local_agent`/`in_process_teammate`/`remote_agent`/`local_bash`/`local_workflow`/`monitor_mcp|ws`/`mcp_task`/`dream`/…），统一 `register/update/get/all`、统一 `LZ` 摘要推送、统一 `Fa({mode:"task-notification", priority:"next"})` 模型通知队列；kill 按类型分派处理器（`MCP_TASK` 为其中之一）。
- **同一触发词汇**：`backgroundedToDeliverMessage`（消息到达转后台）、`backgroundedByUser`、`backgroundedByTurnAbort`、超时自动后台，在 Bash（L12318/L26426）与 MCP 调用间共享；`_Te` 每会话 foreground-calls 注册表对两类调用都提供 `backgroundNow()`。
- 人按停 turn 时，`notePersonsStop`/`stopMovedTasks`（L28835）会把「为送消息而转后台」的 `mcp_task` 一并停止/重排，与 shell 任务一致。

## 关键代码锚点（bundle.js 行号）

| 行 | 内容 |
|---|---|
| L8633+L8634 | `chunk-rbvy6xp2.js`：开关模块 `PR()`（总开关+tengu_glowing_lark）、`nFn()`（worker wake）、`rvs()`（DISABLE_MCP_TASK_BACKGROUND）、`kNt=5000`（cancel 超时） |
| L116:331/970、L514 | env 注册表与类型（`N.bool()`/`N.int()`） |
| L8486 | `iN()`：v1/v2 代际选择（`MCP_SDK_GENERATION` / tengu_brindle_causeway，默认 v2） |
| L26875 | `chunk-nhr07scz.js`：代际访问器与 MCP_TREE_ID tripwire |
| L12101 | 客户端 capabilities：`Z3n={"io.modelcontextprotocol/tasks":{}}`、`ays()`/`_ut()`/`dxn()`/`k9t()` |
| L21775 / L21782 / L21789 | vendored MCP SDK（旧 2025-11-25 协议）：schema / Protocol / Server |
| L37967 | v2 wire codec：`allowTask`/`allowInputRequired`、`El()` 任务结果校验、`UnsupportedResultType` |
| L39009 | `chunk-14haznwn.js` 片段：`driveMcpTask`(`its`)、`clampPollInterval`、`AGENT_TASK_META_KEY="com.anthropic/agent-task"`、`TaskInputUnservableError`、`TASK_DRIVE_QUIET_STOP`、`Mcp-Name` 头 |
| L38267 | `chunk-v4c37pc6.js` 片段：`callMCPTool`(`jn`)、`ft()`（后台化）、`et()`（行内轮询）、`Hi()`（input 服务）、`createSep2663TaskBinding`(`Wd`) |
| L38204 | v1 客户端片段（无 tasks 代码；`eu as MCP_TREE_ID`） |
| L38266 | `callMCPToolWithUrlElicitationRetry`(`Ud`)：URL elicitation / needs-approval 重试包装 |
| L38263 / L38200 | `composeMcpTool` 调用点：`Jt` 门控、`taskBackground Ut` 组装、`disallowTasks` |
| L42026 | `callMcpToolWithAutoBackground`(`Ie`)、`getMcpAutoBackgroundMs`(`le`，默认 120000)、`isMcpCallMovableWithoutTimer`(`De`)、进度写手（1s 节流）、完成通知 `x()` |
| L38060 | `Icr()`：`mcp_task` registry 条目构造（`lce`="server/tool"） |
| L39018 | `registerOrAdoptSep2663Task`(`as`) |
| L39022 / L39016 | `startSep2663BackgroundDrive`(`At`)、驱动循环 `Et`、取消 `Ge`、重连 `$t`、结算 `ot()`、放弃通知（`qe`/`it`/`at`）；常量 `ze=300000`、`be=30000`、`_t=300000`、`kt=30000`、`Fe=1000` |
| L39036 | `restoreSep2663Tasks`(`fs`)、`buildSep2663PlaceholderResult`(`ds`)、`noteMergedIntoTask`(`cs`) |
| L39030 | 放弃/结算通知文本构建（"Task outcome unknown: …"） |
| L38076 / L38282 | watcher 两代片段：`boundMcpStatusMessage`、`buildMcpTaskNotification`、`mcpContentToNotificationText`、`restoreMcpTasks` |
| L20360 | sidecar 持久化（meta/outcome schema、`mcp-tasks/` 目录） |
| L20374 | registry 通用助手：类型→标签（`mcp:"MCP task"`）、运行判定 |
| L34554 | `MCP_TASK` kind handler（kill） |
| L35855 / L41327 / L41175 | `/tasks` 对话框、MCP 行渲染、页脚提示 |
| L10022:721 | `/tasks` 命令注册（aliases `["bashes"]`） |
| L28078 | `Ohn()`：会话启动/恢复的任务恢复与结局补投（每次 ≤8 条） |
| L42093 | `mcpTaskWorkerWakeKeepers` 调度器（`nFn()` 门控） |
| L12104 / L28032 | `_Te` foreground-calls 注册表与 `ETi()` 消息到达迁移触发 |
| L28835 | turn 停止时对 deliver_message 型 `mcp_task` 的处理 |
| L20219 | 内嵌 CHANGELOG 2.1.319 原文（功能描述与两个 env） |
| L16322 | "Still backgrounding after the current tool — a question is waiting for your answer."（←键转后台交互文案） |

## 提示词相关（直接给模型看的文本）

- 后台化占位结果（`buildSep2663PlaceholderResult`）：`MCP tool "<server>/<tool>" started server-side task <mcpTaskId>. It was moved to the background as task <registryId> and keeps running on the server; you'll receive a notification with the result when it completes, and you can keep working in the meantime. …`
- 自动后台返回文本（L42026）：`MCP tool "<desc>" is still running after Ns. It was moved to the background as task <id> and keeps running`；消息触发变体 `…was moved to the background as task <id> so that a message that arrived while it was running can reach you; it was not interrupted and keeps running`。若会话「回复后即停」（`Ah()`=stopsAfterReply）会追加结果可能丢失的警告、建议改用后台 agent 发起此类调用，并指明 `To stop it, use TaskStop with task_id "<id>"`；否则 `…you'll receive a notification with the result when it completes… Note: it does not survive exiting this session.`
- 行内等待失败：`MCP server "<s>" task for tool "<n>" was cancelled/failed: <msg>`（"MCP task did not complete"）。
- 畸形任务句柄：`MCP server "<s>" returned a malformed task handle for tool "<n>", so Claude Code cannot track the task or get its result. … Calling the tool again may start another task.`
- input 无法服务：`the task asked the user a question that this session cannot show yet / asked for input of a kind this client does not serve, so Claude Code asked the server to cancel it`。
- 放弃跟踪通知：`Claude Code cannot follow a background MCP task on its server. It is still checking.` / `Claude Code has stopped checking on a background MCP task. Its outcome is not known.` + 按失败码（`server_unconfigured`/`era_mismatch`/`capability_lost`/`update_unreachable`/`reconnect_failed`/`answered_with_errors`/`needs_sign_in`/`ttl_expired`/`identity_mismatch`）给出用户可操作指引（如 /mcp 重连、重新登录）。
- 结局通知由 `buildMcpTaskNotification({registryId, mcpTaskId, serverName, toolName, status, resultText, resultHint, statusMessage})` 构建；resume 补投时前缀 "This notification was written at … delivered now because this session was resumed…"。
- 「并入」提示：服务器在 `_meta["com.anthropic/agent-task"]` 返回 `merged:true` 时，registry 条目 statusMessage 置为 "a follow-up message was merged into this turn"（`noteMergedIntoTask`）。
- 遥测事件：`tengu_mcp_tool_auto_backgrounded`、`mcp_auto_background`、`mcp_task_background`、`mcp_task_complete`、`mcp_task_stop`、`mcp_task_restore`、`tengu_mcp_tripwire`、`tengu_mcp_auto_background` 等。

## 未知与推测

- `k()`/`dn()` 是 statsig 门控函数（观察：调用形态 `k("tengu_*", default)`）；`PR()` 的默认值构成（`入口==="cli" && !CLAUDE_CODE_REMOTE && !isCcsTenant()`）是观察，但服务端 flag 可随时翻转，故「默认开」仅对无 flag 拉取环境成立。
- `In()` = `isCcsTenant`、`cQ()` = `isSingleShotPrintSession`、`q()` = `isDiskless`（均由 L22115 导出别名证实）；`ye()` 在调用点作「非交互会话」判定（**推测**，依据用法）；`uQ()`/`ois()`/`Od()`/`sessionFollowsTasks` 的精确语义未逐一追完（`sessionFollowsTasks` 默认 false，推测为远程/托管会话由主机决定是否跟随任务）。
- L38204 判定为 v1 客户端（`chunk-v3fdm6wh.js`）片段：**推测**——它导出 `callMCPTool` 与 `MCP_TREE_ID` 但全文无 tasks 代码，`eu` 的字面值不在该片段内。
- worker wake（`mcpTaskWorkerWakeKeepers`）细节只读到调度骨架：任务后台化时武装、按 `onWorkerWakeOutcome`（`parked/told/stopped`）推进、状态含 `cancelling`（ttl_expired）/`left_to_fire`；其唤醒的确切执行体（疑似唤醒一个 worker 会话收取结果）未深挖。默认关闭（tengu_mcp_task_worker_wake=false）。
- `hwo`/`be.mark`（tengu_rippling_map）挂在调用 `_meta` 上的标记与 tasks 的关系未追。
- 2.1.325 changelog 的两条——「任务等待回答时告知 Claude 并可指引去 /tasks」「后台 MCP 任务问题上 Esc 变为 answer later」——在 2.1.321 二进制中**不存在**（全量检索 "waiting for your answer"/"answer later" 仅命中静态 UI 文案与无关 remote-control 文本）。2.1.321 已有的只是 /tasks 行内提示与页脚提示；模型侧告知链路推测为 2.1.325 新增。
- `noticeGate`(`lpr`) 的 `HDe(e)`（hookCaller/hookServesModel/pluginUnnamed）判定细节未展开，只知道 hook 忙时通知会被排队重试。
- 方法学提醒：本 feature 几乎全部位于**未包装 chunk**（非 `var X=p(()=>{…})` 形态），extract_bundle.py 当前只把包装模块 beautify 进 `claude-app.js`，因此该文件对本 feature 零覆盖；分析此类 feature 必须直接在 `bundle.js` 里 grep 并按行 beautify（本次的工作副本在临时目录 `chunks/chunk-L*.js`，属可再生临时产物）。

# Remote Control 主机端（`claude remote-control`）

分析对象：Claude Code **2.1.321**（Windows x64，BUILD_TIME `2026-11-09T15:53:28Z`，GIT_SHA `76bc7350`）。
产物：`C:\Users\admin\AppData\Local\Temp\claude-re\v21321\`（`claude-app.js` 美化 app 代码；`bundle.js` 原始缝合文件，Bun 内嵌 ESM chunk 以 `B:/~BUN/root/chunk-*.js` 路径存在，每个 chunk 在 bundle.js 里是若干超长行，前有 `// @bun @bytecode` + `// Version: 2.1.321` 头）。

官方 changelog 对应线索：`claude remote-control`（2.1.321 起支持 `--settings <file>`）、2.1.323 身份保持延长、2.1.325 退出码 4/69 与 `/resume`、`/teleport` disconnect-first、手机权限通知。注意 **2.1.323/325 的行为不在这版二进制里**，下文按版本分开标注。

## 功能概述

Remote Control 把本机一个目录变成 claude.ai/code（web）和 Claude 手机 app 的远程会话宿主：

- `claude remote-control`（别名 `rc`）：前台 bridge 进程，注册本机为 "environment"，服务器把用户在手机/web 上发起/继续的会话派发给本机，会话进程实际在本机跑，手机/web 只是远程客户端（banner 原文："The session keeps running on this machine. Use your other devices as a remote control."）。
- 会话内 `/remote-control`（别名 `/rc`，local-jsx 命令）：把当前 REPL 会话挂到远端/断开（已挂载时描述变为 "Disconnect Remote Control"）。
- 反向用途：同一进程还充当 "tool host"，把本目录的文件/工具能力提供给 claude.ai 云端会话（"offering this folder to cloud sessions"），即「background sessions started on your claude.ai login」可以落在这个目录。

## 开关与配置

自下而上的门禁链（任一不过则拒绝启动，见入口 chunk，bundle.js:20573）：

1. **本地 settings**：`disableRemoteControl: true` → 直接拒绝（`refuseRemoteControlLocally`）。
2. **登录态**：无存储的 OAuth token → 报 `BRIDGE_LOGIN_ERROR`。
3. **组织策略**：`allow_remote_control` 策略拒绝（含 HIPAA latch、policy route 404、policy cache miss 等细分，见 `BridgeHeadlessPermanentError`/transient 分类，bundle.js:27898 区域 `Jo()`）。
4. **服务器最低版本 floor**：`checkBridgeMinVersion`，"Version X or higher is required. Run `claude update`"。
5. **trusted device 预检**：`preflightTrustedDeviceBlocking`；API 层 403 `untrusted_device` 会触发 enroll-and-retry（rc-api 的 `T()` 包装）。

用户态开关与持久化：

- 首次运行交互确认 "Enable Remote Control? (y/n)"，答 y 后写 global config `remoteDialogSeen: true`，之后不再问。
- spawn mode 首次在 git 仓库里交互选择（`[1] same-dir` / `[2] worktree`），保存到项目配置 `remoteControlSpawnMode`。
- 机器身份：global config `remoteControlMachineId`（UUID，由 `getOrCreateRemoteControlMachineId` 惰性生成并复用）。

CLI 参数（`bridgeMain` 解析，rc-chunk `Cc` 函数，bundle.js:27880 起）：

- `--settings <file>`（2.1.321 新增）：经 `getSettingsParseErrorsForSource("flagSettings")` 校验，有解析错误则拒绝启动（"sessions would skip part or all of the --settings file"）；通过 `getFlagSettingsFilePinnedContent` 钉住内容，随 `settingsFile`/`settingsBinding` 传给每个派生会话进程。
- `--spawn=same-dir|worktree`、`--capacity <n>`（默认 `SPAWN_SESSIONS_DEFAULT = 32`）、`--permission-mode`、`--name`、`--continue`（恢复最近会话）、`--session-id <id>`（恢复指定会话）、`--chrome`、`--allow-unattended-tool-calls`（要求 TTY、写 `~/.claude/state` 授权）、`--session-name-prefix`（写入 env `CLAUDE_REMOTE_CONTROL_SESSION_NAME_PREFIX`）。
- 放在 `remote-control` 动词**之前**的 root 选项只有白名单会带入会话（verbose/debug/model/effort/betas/thinking/allowedTools/dangerouslySkipPermissions 等，见 rc-entry 的 `O` 表）；其余（含 verb 前的 `--settings`、`--permission-mode`）直接拒绝启动："not carried over to the sessions Remote Control starts"。

daemon/无人值守形态（worker 注册表 `Hve`，claude-app.js:154937；入口 `qva` 在 bundle.js:14657 所在 chunk）：

- worker kinds：`heartbeat` / `scheduled` / `remoteControl`。子进程从 **stdin 读配置 JSON**（`{config: {...}, initialAccessToken}`），schema 校验失败 exit 2。
- remoteControl worker schema（claude-app.js:154787）：`{dir, name?, spawnMode: same-dir|worktree(默认 same-dir), capacity: 默认32, permissionMode?, sandbox?, sessionTimeoutSeconds?, createSessionOnStart: 默认false}`（strict）。**`sandbox` key 不支持**：报 "The sandbox key is not supported for Remote Control" 并 `process.exit(xK)`（xK=78，EX_CONFIG 语义）。
- `bCt()`（可用性判定）：`heartbeat` 恒可用；`remoteControl` 还需 `Mri()` 为真（具体条件未展开）。
- daemon remoteControl run 函数 `ye`（claude-app.js:154799 起）：初始化 error/analytics sink → 取 access token（无则 exit 1）→ GrowthBook 初始化失败不致命 → 最终调 `runBridgeHeadless`（chunk-5pq6tth6.js），并向父进程 `process.send` 汇报 `rc_busy` / `rc_serving_tools`；支持父进程 message 下发 shutdown cause。

## 实现架构

### 进程与模块形态

- 前台：`claude remote-control` → `enterRemoteControl`（门禁）→ `startRemoteControl` → `bridgeMain`（导出名 `Cc`，chunk-5pq6tth6.js，bundle.js:27846–27898，export 行在 27898 尾：`export{Pn as BridgeHeadlessPermanentError, Cc as bridgeMain, Mc as runBridgeHeadless}`）。
- daemon：`qva` → `ye` → `runBridgeHeadless`（`Mc`），headless 模式无 TTY 交互。
- 会话执行单元：bridge 用**当前同一二进制**（`pinToCurrentBinary: true`，rc-chunk:5027）spawn 子进程跑每个会话；子进程以 remote 模式运行（env `CLAUDE_CODE_REMOTE*` 一族：`CLAUDE_CODE_REMOTE`、`CLAUDE_CODE_REMOTE_SDK_URL`、`CLAUDE_CODE_REMOTE_SESSION_ID`、`CLAUDE_CODE_REMOTE_SEND_KEEPALIVES`、`CLAUDE_CODE_REMOTE_MCP_CONFIG` 等，bundle.js:116/1236 附近的 env 注册表）。

### 注册：environment

`registerBridgeEnvironment`（bridge API client，bundle.js:27839 所在 chunk）：

- `POST {apiBaseUrl}/v1/environments/bridge`，body：`machine_name`、`machine_id`、`directory`、`branch`、`git_repo_url`（脱敏后）、`max_sessions`、`metadata`（`worker_type: "claude_code"`、`machine_id`、`device_uuid`、tool_host advert：`tool_host: "2"` + CLI 版本/平台，或 withdraw 时空串；`dir_browse: "1"`）、可选 `host`（hostProfile：tools/mcp 列表）、可选 `environment_id`（**复用旧 environment**）。
- 响应：`environment_id` + `environment_secret` + `environment_secret_expires_in`（secret 会过期，靠 poll 401 → re-register 续期）。
- 409（errorType `yin`）：同设备同目录已被另一个实例服务 → "This folder is already served by another Claude Code on this device."
- 404：账号未开通 → "Remote Control environments are not available for your account."
- 注册由 `yi({register, interactive, onFailure})` 包装（chunk-53g33wyg）：失败时 `onFailure` 打印原因，服务器给了延迟就提示 "Exiting in about X seconds." 再退出；遥测 `tengu_bridge_registration_failed` / `remote_control_entry=registration_failed`。
- 注销/下线：`DELETE /v1/environments/bridge/{id}`（deregister）或 `POST /v1/environments/bridge/{id}/offline`（markOffline，保留现场时用）。

### 工作获取：长轮询 + 可选 SSE watch

主循环在 `es`（rc-chunk:2635 起）：

- **长轮询** `GET /v1/environments/{id}/work/poll`（参数 `reclaim_older_than_ms`、`poll_interval_ms`）。间隔由 flag `tengu_bridge_poll_interval_config` 可调（chunk-1ejsy0rp.js，bundle.js:27480）：默认空闲 2000ms、部分占用 2000ms、满载 600000ms、`reclaim_older_than_ms` 5000、`session_keepalive_interval_v2_ms` 120000、SSE 连接超时 30000、`forced_stops_per_hour` 3。
- **满载时转为 per-work 心跳**：`POST /v1/environments/{id}/work/{workId}/heartbeat`（响应带 `lease_extended`、`state`），心跳周期到点再回落 poll（"Heartbeat poll_due after N cycles"）。
- **SSE watch（可选，默认关）**：`GET /v1/code/sessions/watch?include_trigger_sessions=true`（`Accept: text/event-stream`，支持 `Last-Event-ID` 续传），`watch_sessions` 默认 false；watch 帧驱动 `Ze.onFrame` 提前唤醒 poll。`sessionsWatch.mintResumeToken` 用 `GET /v1/code/sessions?limit=1` 的 `resume_token` 作 SSE 续传游标。
- work 领取三件套：`POST .../work/{id}/ack`（确认）、`/stop`（`{force}`，主动放弃/关停）、`/heartbeat`。
- work item 的 `secret` 是 **base64url JSON**（schema 在 chunk-1ejsy0rp.js）：`{version:1, session_ingress_token, api_base_url, claude_code_args?, mcp_config?, auto_mode_environment?, worktree?, subdirectory?}`。`session_ingress_token` 是该会话的专用凭证（后续 ack/registerWorker 都用它当 Bearer）。

work 类型分派（rc-chunk:3362 起 switch）：

- `healthcheck`：ack 后即完。
- `session`：派生会话（见下）。
- 带 `data.mode` 的：`tool_use` → `toolHostHandler.handle`（本机作为云端会话的工具宿主）；`host_requests` → 目录浏览（另有独立长轮询 `GET /v1/code/environments/{id}/host_requests?wait_ms=`，目前唯一 kind 是 `list_directory`，结果 POST 回 `host_requests/{id}/result`）；未知 mode → 主动 stopWork(force) 并计 `tengu_bridge_work_mode_unsupported`。

### 会话执行：CCR v2 worker

session work 的处理（rc-chunk:3370–3790）：

1. 已在跑 → 只刷新 access token（`updateAccessToken`）。
2. 容量满 → 拒绝（`Ko()` 走 stopWork，理由 "too many sessions are running"；project-thread 子会话有例外提示）。
3. ack → 初始 heartbeat → 读会话记录做版本 floor/标签检查（`auto_mode_environment`、projectThreadChild 等）。
4. **CCR v2 注册 worker**：`POST {api_base_url}/v1/code/sessions/{sessionId}/worker/register`（Bearer = session_ingress_token），返回 `worker_epoch`（整数，无效则报错）；失败按 408/429/5xx 退避重试。
5. 决定工作目录：same-dir 直接用注册目录；`worktree` 模式建 `bridge-<session>` git worktree（或用 WorktreeCreate hook）；work secret 带 `subdirectory` 时进入用户在 claude.ai 上选的子目录。
6. spawn 子进程：`ui(R, {sessionId, sdkUrl, accessToken: session_ingress_token, workerEpoch, serverConfig, modelArgs, roles, boundResumedTurn, idleExitAfterMs, ...}, dir)`；`sdkUrl = {apiBaseUrl}/v1/code/sessions/{sessionId}`（`F8e()`）。子进程事件上行：`POST /v1/code/sessions/{id}/worker/events`（批量，maxBatchSize 100）+ `workerSocket`（`beat`/`carry`，心跳与事件共用，失败回退 POST）+ `POST .../worker/heartbeat`（带 worker_epoch）。下行（用户消息、权限应答）经同一 SDK 通道由服务器转发。
7. 会话标题取首条用户消息截断，与服务端标题双向同步（`getBridgeSession` / update）。

### 身份标识与保持（bridge-pointer.json）

实现：chunk-yf4zc0sh.js（bundle.js:27811），经 shim chunk-14j8bc84.js（bundle.js:38496）导出 `readBridgePointer` / `writeBridgePointer` / `clearBridgePointer` / `readBridgePointerAcrossWorktrees` / `createBridgePointerWriteQueue` 及常量。

- 文件位置：`join(qm(), pA(dir), "bridge-pointer.json")`（`qm()` 是 ~/.claude 状态目录，`pA` 是目录的 hash 化子路径）。
- 内容 schema：`{sessionId, environmentId, source: "standalone"|"repl", pid?, procStart?, activeSessionIds?(≤64 条), activeSessionIdsPersistedAt?, projectThreadSessionIds?, parkedProjectThreadSessionIds?, ...PersistedAt}`。`pid`+`procStart` 用于区分「旧进程还活着」与「陈旧文件」（`isProcessRunning` + `isSameProcessAsync` 防 PID 复用误判）。
- TTL：`BRIDGE_POINTER_TTL_MS = 14400000`（**4 小时**）；若启用 projectThreadResume 且 projectThread ids 仍新鲜（7 天内），TTL 放宽到 `604800000`（**7 天**）。mtime 超过 TTL 即视为无效并清除；允许 120s 时钟回拨容忍（`_ma()`）。
- `activeSessionIds` 另有 15 分钟新鲜窗口：`PERSISTED_SESSION_RESUME_WINDOW_MS = 900000`（`isPersistedStampFresh`）。
- 运行中每小时（3600000ms 定时器，rc-chunk:4422 `ns()`）重写 pointer 并刷新 `procStart`；写入经 `createBridgePointerWriteQueue` 串行化，写后读回验证，发现别人 pid 的 pointer → "Lost pointer write race … Exiting to avoid a split-brain conflict"（exit 1）。
- 重启接管：`claude remote-control` 启动时读 pointer，`source === "standalone"` 且新鲜 → 注册时带 `reuseEnvironmentId` 请求**复用同一 environment**（服务器返回相同 environment_id 才算成功，否则 warn "Could not reuse the previous environment" 并清 pointer）；`activeSessionIds` 新鲜 → 逐个 `reconnectSession` 重新入队。
- `--continue`：用 `readBridgePointerAcrossWorktrees`（最多扇出 50 个 git worktree 找最新 pointer）恢复最近会话；找到后 `Resuming session <id> (<年龄> ago)`。
- **版本差异**：changelog 2.1.323 的「同目录 4 小时内重启保持身份、最长 30 天」**不在本版**：2.1.321 的客户端 TTL 是 4h（project thread 场景 7d）。30 天上限在本版只作为 resume-interrupted-turn 的 flag 上限常量（`HCr/XCr=2592000000`）出现，与 bridge pointer 无关。30 天身份很可能是服务端 environment 保留策略 + 后续版本放宽的客户端 TTL（推测）。

### 会话接管/移交协议

- **服务器 → 本机接管**：`POST /v1/environments/{env}/bridge/reconnect {session_id}`（`reconnectSession`）把会话重新入队到本 environment；启动恢复、`--session-id` 恢复、pointer 里的 activeSessionIds 都走它。目标会话已归档时先 `unarchiveBridgeSessionIfNeeded`（<300 视为成功；409 = 已被别的客户端激活，"resuming without a mutation to compensate"）。
- **本机 → 云端/归档**：`archiveSession`：`POST /v1/code/sessions/{id}/archive`（CCR v2，`useCcrV2SessionCrud` 开关）或 `POST /v1/sessions/{id}/archive`（旧路径）。
- **优雅关闭分叉**（rc-chunk:3940–4060）：
  - shutdown cause ∈ {upgrade, reload, yield} 且 `persistActiveSessionsOnShutdown`（gate `tengu_daemon_upgrade_defer_busy`，默认开）且本进程 ownsPointer → 把活跃会话 id 写回 pointer，`POST .../offline` 标记下线，**不 archive、不 deregister**，提示 "Environment preserved. Restart `claude remote-control` to reconnect existing sessions."（单会话模式则提示 ``claude remote-control --continue`` 或 `--session-id <id>`）。
  - 否则：SIGTERM 全部会话子进程（30s 宽限后 forceKill）→ 逐个 `stopWork(force=true)` → archive 所有会话 → deregister environment → 清 pointer。
- REPL 侧的表面管理另有 `ui_attach`/`ui_detach` 协议（remote surface 加入/离开会话 roster，`session.detach` 钩子事件，bundle.js:14904 附近）——这是「远端客户端挂上/离开某个会话」的信令层。
- **版本差异**：changelog 2.1.325 的 `/resume`、`/teleport` disconnect-first 语义不在这版二进制；2.1.321 里对应机制就是 pointer + reconnect + ui_detach，没有发现 resume 前主动断开 bridge 的代码路径（未发现相关字符串）。

### 权限询问与手机通知

- 会话子进程在 remote 模式下，权限询问走 SDK 控制通道（control_request/control_response），经 worker→服务器→手机/web 客户端回答；schema 注释明确 "remote transports (mobile/desktop bridge) receive the equivalent signal via delivery ACKs instead"（claude-app.js:37078 等 command_lifecycle 描述）。
- **PushNotification 工具**（claude-app.js:172131 起，`tengu_kairos_push_notifications` 门控，默认关）：`message ≤200 字符`；有 remote transport（`CLAUDE_CODE_REMOTE` 或等价判定）时 `pushSent: true`，并经 `onProgress` 发 `os_notification` 事件（`notificationType: "push_notification"`）交给宿主通知通道；无 transport 时 `disabledReason: "no_transport"` → "Mobile push not sent (Remote Control inactive)."；用户在终端前（presence check）→ `user_present` 不发推送；`/config` 关闭 → `config_off`。
- 「phone notifications showing what Claude is asking permission for」是 2.1.32x changelog 条目；本版能观察到的是 PushNotification 的通用推送通路和 remote transport 判定，权限询问内容进入推送的具体事件名未在本版定位到（推测：随 control_request 事件经 worker/events 通道上行，由服务器侧生成推送文案）。

### 退出码语义（2.1.321 观察值）

| 退出码 | 触发 |
|---|---|
| 0 | bridgeMain 正常跑完（主循环结束后 flush analytics，`process.exit(0)`，rc-chunk:5222）；首次确认对话答 n |
| 1 | 绝大多数错误（注册失败、未登录、参数非法、split-brain、容量/环境冲突等） |
| 2 | daemon 子进程 stdin 配置 JSON 无效 / schema 校验失败 / 未知 worker kind（`qva`） |
| 78（`xK`） | worker kind 不可用（`bCt` 为假）；remoteControl 配置带 `sandbox` key |

- **版本差异**：changelog 2.1.325 的「自我停止 exit 4（single-session 仍 exit 0）、无法注册 exit 69」在本版**不存在**（全二进制 grep 无 `process.exit(4)`/`exit(69)`）。2.1.321 注册失败走 exit 1。

## 关键代码锚点

| 位置 | 内容 |
|---|---|
| `bundle.js:20573`（chunk，导出 `enterRemoteControl`/`refuseRemoteControlIneligible`/`refuseRemoteControlLocally`/`startRemoteControl`/`rootOptionsRemoteControlRefuses`/`rootOptionsRefusedMessage`） | CLI verb 入口与门禁链；root 选项白名单 |
| `bundle.js:26142` | `/remote-control`（`/rc`）slash 命令定义（local-jsx，isEnabled 判定，hidden 逻辑） |
| `bundle.js:27480–27481`（chunk-1ejsy0rp.js） | poll/心跳配置默认值与 flag schema（`tengu_bridge_poll_interval_config`）；work secret schema；`F8e`（sdkUrl）；`rOt`（worker/register） |
| `bundle.js:27811`（chunk-yf4zc0sh.js） | bridge-pointer.json 实现：TTL 4h/7d、15min 活跃窗口、worktree 扇出读 |
| `bundle.js:27839–27840` | bridge REST API client：`/v1/environments/bridge` 注册/注销/offline、`work/poll`、`work/{id}/ack|stop|heartbeat`、`bridge/reconnect`、`sessions/*/archive`、`sessions/watch`（SSE）、`host_requests` |
| `bundle.js:27846–27898`（chunk-5pq6tth6.js，export 在 27898 尾） | `bridgeMain`（`Cc`，27880 起）、`runBridgeHeadless`（`Mc`）、主 poll 循环（`es`）、session work 分派与 worker spawn、优雅关闭 |
| `bundle.js:38496`（chunk-14j8bc84.js） | pointer 模块的 re-export shim（含常量名：BRIDGE_POINTER_TTL_MS 等） |
| `bundle.js:14657–14666` | daemon worker 入口 chunk：`qva`（stdin JSON 配置）、`Hve`、`tbn`/`nbn`（daemon 配置增删） |
| `claude-app.js:154787` | daemon remoteControl 配置 schema（dir/spawnMode/capacity 32/sandbox 禁用…） |
| `claude-app.js:154799–154931` | daemon remoteControl run（→ `runBridgeHeadless`）；`Hve` 注册表在 154937 |
| `claude-app.js:172131–172260` | PushNotification 工具（push/local/disabledReason 逻辑） |
| `claude-app.js:153703` 起 | `--tools` 与 Remote Control/云环境互斥的错误文案 |
| `claude-app.js:204029–204060` | `/send-to-project` 的 Remote Control 门（"Remote Control is off, so this session can't be sent"） |
| `claude-app.js:36758/37078` 等 | SDK command_lifecycle schema：remote 会话的 cancel/discarded 语义、remote transports 经 delivery ACK 收信号 |
| 分析过程提取物（临时） | `work/rc-chunk.pretty.js`（bridge 主体 5567 行）、`work/rc-api.pretty.js`（824 行）、`work/rc-pointer2.pretty.js`、`work/rc-entry.pretty.js`、`work/rc-ccr.pretty.js`、`work/rc-daemon-entry.pretty.js` |

## 未知与推测

以下为**推测**，未在本版二进制中取得决定性证据：

1. **workerSocket 的协议**：有 `beat`/`carry`/`maxBatchBytes` 方法与 POST 回退，疑似 WebSocket 或长连 SSE 客户端封装；创建点未定位（可能在 runner 侧 chunk，未展开）。
2. **30 天身份保持**：changelog 归于 2.1.323；推测是服务端延长 environment 保留 + 客户端后续版本放宽 pointer TTL，本版客户端 TTL 只有 4h/7d。
3. **权限询问的手机推送文案**：推测由服务器根据 control_request 事件生成推送，CLI 侧只负责经 worker 通道上行事件；未找到 "permission" 与 push 直接关联的字符串。
4. **`yi` 注册重试包装**（chunk-53g33wyg）的具体退避参数、以及 `Mri()`（daemon remoteControl 可用性）的判定条件未展开。
5. **`/resume` disconnect-first（2.1.325）**：本版无对应代码；2.1.321 中 resume 远端会话靠 `--session-id`/`--continue` + `reconnectSession`，REPL 内 `/resume` 一个正被 bridge 服务的会话时的行为未追（入口在 REPL resume 流程，不在 bridge chunk）。
6. **`host_requests` 除 `list_directory` 外的 kind**：代码显式 drop 未知 kind，目录浏览是目前唯一实现的宿主请求。
7. `environment_secret` 的轮换：`poll 401 → re-register` 循环里 `M()` 更新 secret 与 pendingRequeues，具体轮换触发条件（`secret_renewal_due` 只是 heartbeat 退出原因之一）未完全追完。

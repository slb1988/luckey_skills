# Code Mode（实验性）：Claude 写 JavaScript 调用工具

> 分析对象：Claude Code v2.1.321（`C:\Users\admin\AppData\Local\Temp\claude-re\v21321\`）。
> **重要方法说明**：该 feature 的绝大部分实现位于**懒加载 chunk**（`B:/~BUN/root/chunk-*.js`），只存在于 `bundle.js`（缝合 bundle）；`claude-app.js` 只含 Poll/REPL 工具的 zod schema 片段与少量接线。下文证据同时引用 `claude-app.js:行号` 与 `bundle.js:行号`（后者配合 chunk 名，可在 bundle.js 中直接 grep 定位）。

## 功能概述

- 官方 CHANGELOG（2.1.323）："Added Code Mode, an experimental opt-in in which Claude writes JavaScript to call its tools"，文档入口 `https://code.claude.com/docs/en/code-mode`（可关闭组织级使用）。
- 代码在 2.1.321 已完整存在但处于 **gated opt-in** 状态：需要 env var + 服务端 GrowthBook flag + 一系列环境资格检查全部通过，并在首次启动时弹出确认对话框。
- 内部代号：实现里大量以 "REPL mode" 称呼；内部源路径为 `src/tools/EvalTool/`（prelude 文件头注释，见下）；UI 显示名 `"Code Mode"` / `"Code Mode (experimental)"`（bundle.js:514，`Yp`/`W_`）。
- 核心形态：模型侧只看到 1~2 个工具——`REPL`（别名 `Eval`，UI 名 `Code`）+ 异步车道下的 `Poll`；模型把 JavaScript 作为 REPL 输入提交，harness 在进程内的一个**持久 `vm` context** 里执行，脚本内通过注入的全局函数调用全部工具（含 MCP）。

## 开关与配置

### 用户侧开关

- **唯一用户开关是环境变量** `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE`（bundle.js:514 `HM`；gate 逻辑 bundle.js:35116 `G()`）：
  - 可来自 shell 环境、`~/.claude/settings.json` 的 `env`、或 `--settings` 传入的 flagSettings；值为 truthy（`"1"`）才算开，空/假值算关，其他值报 `bad_value`（"…must be 1 to turn it on"，bundle.js:4331 `qko`）。
  - 若 managed settings 或 `~/.claude.json` 也设置了该变量，则只接受 `~/.claude/settings.json`（refusal `own_settings`）。
  - shell 里 `"0"`/关 → 静默 `not_asked`；settings 里关 → `not_asked`+`turnedOffIn:"settings"`。
- **无独立 setting key**；accept 后写入 `~/.claude.json` 的两个持久标志：`codeModeCaveatsAcceptedV1`、`codeModeAutoModeCaveatAcceptedV1`（bundle.js:35116 `i6r`/`L()`）。
- 打开/关闭都要**重启进程**：通过设置 `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE_RESTART`（值=原因或 `"retried"`）与 `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE_RESTARTED_FROM`（=session id）后 `execRelaunch({pinToCurrentBinary:!0})`（bundle.js:35116 `_()`；bundle.js:20199 启动处消费并 unset）。
- **会话绑定**：在 Code Mode 中开始的会话只能在 Code Mode 开启时 resume（opt-in 对话框原文，bundle.js:37427：`"A session that you start in Code Mode can be resumed only with Code Mode on…"`）；状态栏显示 `"Code Mode is on · this session can be resumed only with Code Mode on"`（bundle.js:4331 `L5i`）。

### 组织级 / 服务端开关

- **GrowthBook flag `tengu_rustling_blossom`**（导出名 `CODE_MODE_OPT_IN_GATE`，bundle.js:35116 `aii`）：`dn()` 读取；flag 被 disable → refusal `no_flags`；需要 source 为 `payload`/`override`（服务端下发）才过 `gate`（`A()`/`Y()`）。
- **managed/policy settings 把 env var 设为关** → `admin`（"your organization's settings don't allow it"）；读不到组织 settings → `admin_unread`；检查时的凭据与当前不一致 → `credential_changed`。
- **HIPAA / zero-data-retention 组织不提供**：`compliance`（`hs("hipaa")||hs("zdr")`）。
- **OTel 开启时不提供**：`otel`（`CLAUDE_CODE_ENABLE_TELEMETRY` 或 `ENABLE_BETA_TRACING_DETAILED`；理由：Code Mode 尚不为每个工具调用发 OTel 事件）。
- `isCodeModeOffByCloudGroup`（`Rxa`）、`isCodeModeOffByLocalOverride`（`Cxa`）、`staffSwitchName`（`Exa`）在 2.1.321 中均为**空桩**（`()=>!1`/`()=>""`，bundle.js:4553），推测为后续版本的组织策略/员工开关预留。

### 环境资格矩阵（任一不满足即拒绝，`refusalForeseen`/`F()`，bundle.js:35116）

| why | 含义（文案在 bundle.js:4331 `qko`） |
|---|---|
| `runtime` | 需要原生构建（`Vf()` is_native_binary） |
| `no_bash` | Windows 上需要 Git for Windows (Bash) |
| `entrypoint` | 只在交互式终端（排除 `CLAUDE_CODE_REMOTE`、非 cli 入口、thinClient、`ANTHROPIC_UNIX_SOCKET`） |
| `unattended` | 不支持后台任务、队友 pane、Remote Control、`CLAUDE_BRIDGE_REATTACH_SESSION` |
| `no_setup` | CI/`IS_DEMO`/`CLAUBBIT` 跳过启动检查时不提供 |
| `tools` | `--restricted`/`--tools`/`--disallowedTools`/deny 规则把 REPL 排除（`doToolOptionsLeaveReplOut`，`EEa`） |
| `engine` | JS 引擎自检未过（见下） |
| `agent_teams` | 与 agent teams 互斥 |
| `credentials` | 不支持 apiKeyHelper/`ANTHROPIC_AUTH_TOKEN`/自定义 auth header |
| `provider` | 只支持 Anthropic API first-party（且 `Vd()`） |
| `model` | 只支持 **Opus 5.5 / Sonnet 5.5**（`isEvaluatedModel`=`mSn`=`cbt\|\|pzn`；模型目录中两者为 `claude-opus-5-5`/`claude-sonnet-5-5`） |
| `mods` | 与检查工具调用的 mod（带 JS hooks 的插件）不兼容（`installedModChecksToolCallsAtStartup`） |
| `no_flags` | 会话不下载 Anthropic 远端 flags（`DISABLE_TELEMETRY`/`DO_NOT_TRACK`/`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`/`CLAUDE_CODE_DISABLE_FEATURE_FLAGS`） |

### 交互流程（观察）

启动 `E2o`（bundle.js:20194）→ `primeReplEngineCheck`（`EPs`）+ env var 为真时立即跑引擎自检 → `settleCodeModeOptInAtStartup`（`TEa`）计算 gate 状态；onboarding 序列中 `reviewCodeModeOptInInSetup`（`REa`，bundle.js:21524 装配）→ 需要时渲染 `CodeModeOptIn` 对话框（bundle.js:37427，chunk-n20s3dce.js；确认后写 caveat 标志并 `restart_into_mode`）；setup 之后 `closeCodeModeOptInAfterSetup`（`AEa`）复检组织策略/凭据，不通过则 `restart_without_mode`。Telemetry：`tengu_repl_mode_opt_in(_dialog_shown/_accept/_decline)`、`tengu_repl_engine_check`（statig 名 `repl_mode_opt_in`/`repl_engine_check`）；`_yt codeModeTelemetryFields` 往事件里加 `is_repl_mode`、`repl_mode_decision`。

## 实现架构

### 总览（入口 → 数据流 → 输出）

1. **工具面**：Code Mode 开启后，API 请求中的工具列表被裁剪为 MCP 工具 + `REPL` + `Poll` + `StructuredOutput`（`hideCodeModeOnlyTools`=`_J`/`Ve`，bundle.js:4553；`codeModeHidesToolNamesFromApi`=`yte`；`willListHiddenToolNames` 在此版本为桩 `!1`，bundle.js:27183 chunk-1s4c8mn6）。其余内建工具从 API 隐藏，但全部可从脚本内按名调用（`searchTools`/`describeTool` 发现）。
2. **执行**：模型产出 `REPL` tool_use（input `{code, description?, timeout?}`）→ `call()` → `runEngine(xu,…)`（bundle.js ~33621 工具定义）→ 同步车道直接跑；异步车道（auto/bypassPermissions 权限模式 + `isAsyncReplEnabled`=`i5`）先返回回执 `(dispatched #N)`，脚本后台跑，结果经 `Poll` 工具或下一回合前送达。
3. **沙箱**：每次 `REPL` 调用在**同一持久 vm context** 里跑（"State persists across calls"）。
4. **结果**：同步结果渲染成 `<repl-output eval="N" ms="M">`（含 `<log>`/`<result>`/`<error>`）；异步 settle 以 `<event kind="repl-eval">`（或 `repl-status` 状态行）送达；内部每次工具调用向 UI 发 `tool_progress`（`repl_call`/`inner_call` 结构，`script_ended` 结束事件；bundle.js 中 `X3o`/`Y3o`/`jTa`）。

### JS 沙箱：Bun 的 `node:vm`（JavaScriptCore），非 QuickJS / V8 isolate

证据：runtime chunk（bundle.js:33048 起的区域，美化稿 `work/repl-region.pretty.js`）中 `import * as Vn from "vm"`，`w5`=`vm.createContext`、`xt`=`Vn.runInContext`、脚本以 `Script.runInContext(ctx,{timeout})` 执行。Bun 的 `node:vm` 由 JavaScriptCore 实现，因此沙箱是**同进程的 JSC realm/context**，不是独立进程、不是 QuickJS、不是 V8 isolate。

加固手段（全部在 bundle.js ~33048-33900 区域）：

- `createContext({__proto__:null}, {codeGeneration:{strings:false, wasm:false}, importModuleDynamically})`：禁 `eval`/`Function`/WASM；动态 import 一律走 `rejectImport`（提示词明示 "There is no `import`, `require` or `process`: the context is sealed"）。
- **引擎自检**（chunk-d1wesxew.js，bundle.js:27140-27170）：启动时 `vm.createContext` 里跑两个探针脚本——(a) 验证 class 字段初始化/getter receiver 等使用 context 自身 intrinsics（防跨 realm 泄漏），(b) 验证 `await` 之后的 thenable resolve 函数属于 vm context 的 `Function.prototype`（`bun:jsc` 的 `drainMicrotasks` 同步冲刷微任务验证）。结果分类：`passed`/`both`/`thenable_after_await`/`rejected_definitions`/`threw_*`。未过则 REPL 调用抛错："…the JavaScript engine under Claude Code failed Code Mode's engine check. Run Claude Code with the repository's pinned Bun (node_modules/.bin/bun) or use a staff build."（bundle.js:33510 `to()`）。
- **源码插桩 + step 预算**：用 acorn 解析（`ecmaVersion:"latest"`，`allowAwaitOutsideFunction` 等），往块/表达式注入 `__replStep()` 调用（`Zo="{__replStep();"`、`Qo="(__replStep(),"`、`es=";__replStep();"`）；全局计数器按步发放（stride 自适应加倍至 64，每 ≥5ms 读一次钟），**每 turn 预算 300,000,000 步**（`xn()`）+ 每 turn 墙钟（脚本 `timeout`，默认 30s，上限 600s，`Zon`/`REPL_MAX_TIMEOUT_MS`）。超预算/超墙钟抛 `RangeError`；`Function.prototype.toString` 在 context 内被打补丁以隐藏插桩痕迹；stack trace 通过 `(sha256(code)%20000+1)*100000` 的行偏移回映到原始脚本并剥掉 `__replStep`（`Jo()`）。
- 同步段另有 `runInContext` 的 30s `timeout`（`replSyncRunMs`=`gBn`），捕获 `ERR_SCRIPT_EXECUTION_TIMEOUT` 转友好错误。
- unhandled rejection 被 `process` 级 handler 吞掉（"REPL: swallowed an unhandled rejection…"）。
- 每次调用的工具数上限 **50000**（`replToolCallCap`=`NPs`）；脚本结束后残留代码再调用 >20 次（`Pwo`）即永久不应答。

### 工具桥接进 JS（注入的全局）

`Hi()`/`au()`（bundle.js:33510 附近）把工具包成 sealed async 函数挂为全局（`et(ctx, name, sealers.asyncData(...))`），sealer/membrane 层（`su(g,h)`）负责宿主↔context 的值传递与 "sealed" 标记校验。注入面：

- 每个可用工具一个全局函数（`M.toolWrappers[y]`，找不到报 "`X` is not available in this REPL call"）；`tools.list()`/`tools.<name>(input)`（Proxy 实现，见内嵌 `running.ts` prelude）。
- `searchTools(query, max=8≤25)`（结果含截断到 160 字符的 about + 预算 6000 字符的 input schema 摘要，总预算 15000=REPL_PART_CAP/2）；`describeTool(name)`（description ≤4000 字符 + 完整 inputSchema）。
- `$` shell（按平台 `bash`/`powershell`，模板标签式，支持 `.text()/.json()/.lines()/.nothrow()`、超时转后台、`partialId` 分页）；`preview(out[,n])`。
- `file(path)`（`.text()/.json()/.lines()/.exists()/.slice()`）、`write(path,content)`、`edit(path, old, new[, {all,soft}] | [[o,n]...])`、`sleep(ms)` —— 内嵌 prelude 源码注释标明生成自 `src/tools/EvalTool/env/file.ts`、`env/running.ts`（明文嵌在二进制里，offset ~346069975/346071725）。
- `console.*`（进 50MB ring，`console.tail(n)` 读回；超量打 "[console output truncated at 50MB]"）、`self.log`（=进 `<log>` 的输出）、`setTimeout/setInterval`（宿主侧托管，结束后清理）、`atob/btoa`。
- 多代理：`spawnContext/releaseContext/listContexts/contexts.<name>.{tail,result,log}`（底层走 Agent/Task/SendMessage 工具；d.ts 明文 `team.async/sync.d.ts` 嵌二进制）。
- `running`（列出/中止在跑的 eval）。

### 结果回填会话

- 同步：`mapToolResultToToolResultBlockParam`（`ho()`）把 `{result, stdout, stderr, error, …}` 渲染为 `<repl-output eval="N" ms="M">` XML（转义 `&<>`），图片/PDF 以内联 content block 携带：图片 ≤8（`lo`）、PDF ≤4（`co`）、失败页 ≤8（`uo`），总文本 ≤100000 字符（`so`）；每个返回值部件按 `REPL_PART_CAP` 30000 字符首尾截断（`byt getReplPartCap`）。
- 异步：eval settle 序列化为 `<event kind="repl-eval">`（事件字节预算 163840-2048；默认其他事件 49152；bundle.js 常量 `S=163840,aSe=49152,vT="repl-eval",ipe="repl-status"`），经 `Poll` 结果或回合前注入；`Poll` 输出 schema 见 claude-app.js:171150-171230（`content/eventCount/remainingWakeCount/media/toolsUsed/provenance`）；同时派发的上限 `Lbo=8` 个未 settle eval。
- 用户可见进度：每次脚本内工具调用产生 `tool_progress`（`repl_call:{inner_tool_name, inner_tool_input, phase}`），结束发 `script_ended` + `final_tool_use_ids` + `detached_tool_use_ids`。
- REPL 工具 zod schema 在 claude-app.js:171130 与 171174（`gu` 输入 `{code,description,timeout}`、`va` 输出 `{code,result,stdout,stderr,error,stoppedBy,asyncDispatched,neverRan,plainErrorLine,keptByTurnAbort,evalId,ms,late,images…,documents…,notifications,toolsUsed}`）。
- 权限交互：auto 模式下**整段代码**先过 classifier（`toAutoClassifierInput: e=>e.code`，`checkPermissions` 在需分类器时 `passthrough`）；permissionNote 明示 "The line at the top is Claude's own summary of it, and nothing checks it against the code."；hook 改写代码后该段不运行（bundle.js:12343 `y$n` 等一组 "was NOT run" 文案）；auto 无法检查的调用（SendMessage/Task 等）被拒并附解释。

## 关键代码锚点

| 主题 | 位置 | 标识符 |
|---|---|---|
| 显示名/env var 定义 | bundle.js:514（chunk-401gn9kx.js） | `Yp="Code Mode"`,`W_="Code Mode (experimental)"`,`HM/xaa/Paa` |
| gate 状态与拒绝文案 | bundle.js:4331（chunk-d19zh8vm.js） | `TJ`,`aIr`,`qko`,`F5i`(状态栏),`L5i`,`UZe`,`N5i` |
| gate 逻辑核心 | bundle.js:35116（chunk-hsgcthap.js） | `TEa` settleCodeModeOptInAtStartup,`CEa` refusalForeseen,`REa` reviewCodeModeOptInInSetup,`AEa` closeCodeModeOptInAfterSetup,`i6r` answerCodeModeOptInDialog,`EEa` doToolOptionsLeaveReplOut,`aii="tengu_rustling_blossom"` |
| opt-in 对话框 UI | bundle.js:37427（chunk-n20s3dce.js） | `CodeModeOptIn`（重导出 shim 在 bundle.js:36194/37427 行尾 `export{… as CodeModeOptIn}`） |
| 启动接线 | bundle.js:20194（`E2o`）、20199、20209、21524（onboarding 序列） | `EPs` primeReplEngineCheck 调用点 |
| 标志/常量汇总模块 | bundle.js:4553（chunk-fjmewjyf.js；导出表在 bundle.js:26960） | `Wi` isCodeModeEnabled,`Yy` isCodeModeExperimentEnabled,`i5` isAsyncReplEnabled,`yJ` isAsyncLaneMode,`GV` isCodeModeOnlyToolsEnabled,`_J` hideCodeModeOnlyTools,`O_` willHideCodeModeOnlyTools,`Vfe` hasBuiltInEvalTool,`_yt` codeModeTelemetryFields,`pBn` sandboxHostListsBlockCodeMode,`PPs` isCodeModeHeldOffBySandbox,`OPs/mBn` pin/unpinCodeMode,`IPs` codeModeBeforePin,`byt` getReplPartCap；常量 `lAe` CODE_MODE_ONLY_TOOLS={Read,Glob,Grep,Bash,PowerShell,NotebookEdit},`DPs` REPL_PRIMITIVE_TOOL_NAMES(+Write,Edit),`_Pr="repl-tool-code.js"`,`Zon=600000`,`go=30000`,`yo=1000`,`Ke=30000`,`SZe=7200000`,`yBn=30000`,`wo=50000`,`Pwo=20`,`xwo=30000` |
| 引擎自检 | bundle.js:27140-27170（chunk-d1wesxew.js） | `Nrn` engineCheckResult,`SAs` doesEngineResultHold,`wAs` isEngineCheckDone |
| 沙箱/运行时核心 | bundle.js:33048 起的大区域（含 33510） | `import * as Vn from "vm"`,`to()`（建 context）,`au/Hi`（注入全局）,`pu`（装 step 计数）,`Ji`（带超时 runInContext）,`Yr`（工具调用包装+50000 上限）,`Xr`（取消）,`ru`（console ring）,`vr`（searchTools/describeTool）,`ur="__replStep"` |
| REPL 工具定义 | bundle.js:33621（`var mo=cn({…})`，完整定义在美化区域 repl-region.pretty.js:9476） | `po="REPL"`,`X4="Eval"`,`Qsn="Code"`,`Uo` prompt,`Wo` description |
| REPL/Poll zod schema | claude-app.js:171130、171174（REPL 输入/输出）、171150-171230（Poll 输出） | `gu`,`va`,`J` |
| Poll 工具定义 | bundle.js（repl-region.pretty.js:11152 起） | `wi="Poll"`,desc "Wait for pending harness events",maxResultSizeChars 200000 |
| 权限拒绝文案 | bundle.js:12343 | `m$n`,`h$n`,`y$n`,`_$n`,`k$n`,`mco` |
| 结果渲染 `<repl-output>` | bundle.js（repl-region.pretty.js:10307） | `ho`,`Fu` |
| async 事件常量 | bundle.js（`WVe="poll_",aSe=49152,vT="repl-eval",ipe="repl-status",Yko="task-notification",S=163840`） | — |
| 后台代理提示 | bundle.js:38997（chunk-e92hwbfa.js） | `codeModeSendMessageNote` |
| 模型不适配提醒 | bundle.js:35123 | `codeModeModelNotices`（"Code Mode isn't tested on this model · Run /model to switch"） |
| MCP 就绪标记 | claude-app.js:153886/153905（schema）、写入点在 bundle.js（`codeModeRouted:!0`） | `codeModeRouted` |
| Poll 调用接线 | claude-app.js:171390 | `codeModeExperiment: b` |
| 内嵌 prelude/d.ts | 二进制明文：`running.prelude.js-gamvqz19.txt`、`file.prelude.js-234qxsta.txt`、`team.async/sync.d.ts`；zstd 压缩：`core.bash/powershell.async/sync.d.ts-*.txt.zst`（chunk-05rft83w 的 `HELPER_DTS`） | — |

## 提示词相关

- **REPL 工具 prompt**（`Uo(tools, permissionContext)`，bundle.js 美化区域 repl-region.pretty.js:4118 起）：Code Mode 开启时告知 "Your two tools are `REPL` and `Poll`; there are no other tools."（异步车道）或 "Your one tool is `REPL`"（同步车道）；"The REPL is one persistent JavaScript context…"；成本模型（每次 REPL 调用=一次完整模型往返，脚本内部操作近乎免费，鼓励批量+`Promise.all`）；输出模型（最后表达式+`self.log`；`preview()` 避免大输出进上下文）；`## Declarations` 段附 `HELPER_DTS` 的 TS 声明（按 bash/powershell × async/sync 选 `core.*.d.ts`，有 Agent 工具时附 `team.*.d.ts`）；MCP server 名单（≤40 个，`Pl=40`）+ `searchTools` 用法；示例脚本（`jo`）。Code Mode 关闭时退化为旧版 "REPL is your programming interface to Claude Code's tools…" 文案。
- **description**（`Wo`）：开 `"Execute JavaScript to read, write, edit files and run shell commands"`；关 `"Execute JavaScript code with access to Claude Code tools"`。
- **opt-in 对话框**（bundle.js:37427）：解释 "Claude works by writing and running JavaScript that calls its tools"、实验性质、resume 绑定、auto 模式只检查整段代码一次、不检查代码随后发起的每个工具调用。
- **内存/记忆指引改写**：`memorySectionForWire`（`Awo`）把 "with the Write tool" 改成 "with `write(path, content)` in a REPL script"（bundle.js:4553）。
- **错误提示工程**（bundle.js:12343 等）：大量面向模型的纠错文案（`\uXXXX` 逃逸拒绝、hook 改写后不重跑、并发 cap、finished code 不可再调用等）。
- **引擎侧声明**（prelude 注释）：`// Generated from src/tools/EvalTool/env/{running,file}.ts by bun scripts/generate-script-globals.ts` —— 证实内部工具名 EvalTool；step 计数器注释引用内部 `REVIEW.md, REPLTOOL-07`。

## 未知与推测

- `de()`（遍布所有相关模块的前置门）未能解析到唯一定义（minified 名在各 chunk 复用）；**推测**为"该 feature 是否编入/启用"的构建级开关。
- `Sc()`：同步/异步车道与 spawnContext 注入的分判条件，**推测**为交互/非交互（或 Cowork）入口判别；未能定论。
- `SAs(e)=e!=="passed"&&!Vf()` 中 `Vf()` 在该 chunk 的含义存疑：若 `Vf`=`is_native_binary`，则官方构建上引擎自检失败不拦截（held off）；但拒绝文案 "use a staff build" 暗示员工构建有豁免。**推测**：`Vf` 在该 chunk 实为 staff/dev 构建判定。两读必居其一，未定论。
- `hM()`（Poll 工具与异步车道的启用条件）依赖若干 session flag，未展开。
- `core.*.d.ts`（`$`、file/edit/write、timers 的完整 TS 声明）以 zstd 压缩嵌入（`*.txt.zst`），本次未解压；`team.*.d.ts` 与 `running/file` prelude 已按明文取得。
- `replBridge*` 系列标识符属 Remote Control/跨机桥接（`tengu_ultraplan_dialog_choice` 等），与 Code Mode 的 REPL **不是同一事物**，勿混淆。
- 2.1.321 与官宣 2.1.323 的关系：**推测** 321 已含全部代码但 flag 未放开/文案未发布，323 只是打开服务端 gate 或修文案；可做 321↔323 二进制 diff 验证。
- `willListHiddenToolNames`、`isCodeModeOffByCloudGroup`、`isCodeModeOffByLocalOverride`、`staffSwitchName*` 在本版为空桩，**推测**为后续版本预留的"工具名展示/组织策略"分支。

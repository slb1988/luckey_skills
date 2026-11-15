# 权限系统新语义（guardrails）：denyInsteadOfPrompting / blockWritesOutsideWorkingDirectories / autoAllowBashIfSandboxed / 账号 email 检查

> 分析对象：Claude Code v2.1.321（`C:\Users\admin\AppData\Local\Temp\claude-re\v21321\`）。
> **产物分布说明**：这四个 feature 的 schema 描述在 `claude-app.js`，但**实现主体几乎全在 `bundle.js`**（缝合 bundle 的 chunk 区域，`claude-app.js` 未覆盖）。下文锚点以 `bundle.js:行号` 为主（minified 单行、行内检索定位），辅以 `claude-app.js:行号`。
> 官方 CHANGELOG 校对：`bundle.js:20219` 内置 changelog（截至 2.1.319）；上游 CHANGELOG.md（2026-01 拉取）用于 2.1.320+ 的条目。

## 功能概述与版本时间线

| 版本 | 条目 | 本二进制（2.1.321）中的形态 |
|---|---|---|
| 2.1.314 | Added `permissions.blockWritesOutsideWorkingDirectories`：Write/Edit/NotebookEdit 在任何权限模式下拒绝写工作目录之外 | 完整存在 |
| 2.1.317 | Added a check that asks before a web or shell tool call sends your account email address to the network | 已被 2.1.321 的改动取代（见下） |
| 2.1.319 | Added `permissions.denyInsteadOfPrompting`：会触发权限提示的 tool call 直接拒绝、turn 继续；覆盖终端会话、子代理与 teammate | 完整存在 |
| 2.1.321 | Changed the account email check to refuse only a shell command that holds your email and names a User-Agent, **without asking** | 当前形态：内建插件 `cc-plugin-privacy` 硬拒绝 |
| 2.1.325（晚于本二进制） | sandboxed Bash 默认改走正常权限流（`sandbox.autoAllowBashIfSandboxed: true` 才保持免提示）；managed settings 开 sandbox 时需在最高优先级来源显式设 true；email 检查扩展到"脚本内客户端身份、文件写、web fetch、MCP 调用" | **不存在**：v321 中 autoAllow 默认仍为 `true`（`??!0`），email 检查仍只覆盖 shell 类工具 |

---

## 1. `permissions.denyInsteadOfPrompting`（2.1.319）

### 读取与来源门控

- schema：`permissions.denyInsteadOfPrompting: bool`（`claude-app.js:8729` 附近；settings schema 全文描述在 `bundle.js` L513 行所在模块，见锚点表）。
- 官方描述（schema `describe`，观察）："Never wait for a person to answer a tool permission prompt: a call that would prompt is denied at once, the model is told, and the turn carries on. … Allow rules, the permission mode, auto mode's classifier and PermissionRequest hooks decide first… it only ever denies, and allows nothing. Claude's questions and plan mode's tools are not offered to the model, and an MCP server's request for input is cancelled unless an Elicitation hook answers it. … Read from user settings, `--settings` and managed settings; project and local settings are ignored, and true in any of those sources wins."
- 判定函数 `ete()`（`bundle.js:6049`，同一模块在 `bundle.js:5541` 有重复副本）：
  ```js
  function ete(){
    if (In()) return !1;              // In = isCcsTenant（云端 tenant worker，见"未知与推测"）
    return $o().some((e)=>!Lf.has(e) && Se(e)?.permissions?.denyInsteadOfPrompting===!0)
        || wne().some((e)=>e.permissions?.denyInsteadOfPrompting===!0)
  }
  ```
  其中 `$o` = **getEnabledSettingSources**、`Lf` = **REPO_DIR_SETTING_SOURCES**（语义来自 `bundle.js` 的具名 export 映射：`$o as getEnabledSettingSources`、`Lf as REPO_DIR_SETTING_SOURCES`），即从已启用来源中排除 project/local 仓库来源。`wne()` 是第二个来源枚举（未逐一钉死，见推测节）。
- 应用点：`SAr(context)`（同模块）把结果写进 `toolPermissionContext`：**开启时同时置 `shouldAvoidPermissionPrompts: true`**（`shouldAvoidPermissionPrompts: t || e.avoidsPromptsByNature===!0`）。启动装配处在 `HXo`（`bundle.js:16526`）：`if(aVe())M=kJr(M); M=SAr(M);`。
- `toolPermissionContext` 序列化表（`bundle.js:35498`）把 `denyInsteadOfPrompting` 标为 `"not_serialized"`：每次由 settings 重算，不随会话状态持久化。
- **restrictive 注册表 `M7`**（`bundle.js:510` / `claude-app.js:8726-8735`）：`{path:["permissions","denyInsteadOfPrompting"], restrictive:!0}`。在 managed/remote settings 消毒函数 `nu()`（同模块，`qaa()` 调用）中，`restrictive===!0` 且值为 `false` 的键被删除——**managed settings 只能打开它、不能关掉它**。

### 权限管线中的判定入口（观察）

管线的 ask→deny 转换发生在 hooks 之后、对话框之前，共五个落点：

1. **主管线 `$9e`**（`bundle.js:11590`）：
   ```js
   let N = xve(e, vve() ?? lQt(e,n) ?? await FKr(...), MC(r)!==void 0),
       V = N.behavior==="ask" && (N.refusal!==void 0 || se(r).denyInsteadOfPrompting===!0)
             ? await Qae(y,e,n,N,h,r) : N
   ```
2. **`Qae()`**（同处）：进入条件 `S.shouldAvoidPermissionPrompts || s.refusal!==void 0`（因 `SAr` 连带，开启本设置即满足）。内部顺序：
   - `s.refusal!==void 0 && s.hooksMayAllow===!1` → 过一道 `Tso` 后按结果返回；
   - **PermissionRequest hook 仍可回答**（`ghr`），除非 ask 是 personOnly / `localDisplayOnly` / host-worded / mcpSkill / `askRequiresUserInteraction`（`Que()`/`hke()`）时跳过 hook 直接拒；hook 返回 allow 则放行（`lvs` 记账）——印证描述中"answer from a PermissionRequest hook instead"；
   - 有 refusal 则返回 refusal；
   - 否则产出 deny 并打点：`if(w) g("permission_deny_instead_of_prompting")`，`decisionReason={type:"asyncAgent", reason: w ? vqn : "Permission prompts are not available in this context", ask:Zwt(s)}`，`message: w ? kOt(s).message : tMn(n.name)`。
3. **`sAi()`**（`bundle.js:11590`，被 hook 后处理 `XFe`（`bundle.js:12108`）调用）：`r.behavior!=="ask" || 设置关` → 原样返回。特例：`DKr`（mod 自身发起的调用且非 hookServesModel）→ `GW()` 拒绝文案；非交互会话无 `--permission-prompt-tool`（`ye()&&rT()===void 0`）、host 声明拒绝 ask（`dxt(r)`）、MCP 调用在 plan/dontAsk 模式下 → 打点 + `r.refusal ?? kOt(r)`；否则回落 `Qae`。
4. **网络提示类**（`bundle.js:35838`，sandbox 网络访问的 `ask`/`#o`）：`toolPermissionContext.denyInsteadOfPrompting===!0` → 每 host 打一次 `permission_deny_instead_of_prompting`，直接返回 `!1`（拒绝）。外层包装 `mx`（`bundle.js:28845`）在拒绝时 `emitPermissionDenied(Foe, qz(), void 0, kOt({behavior:"ask", message:`Allow network connection to ${n.host}?`}))`。
5. **sandbox 网络分类器 `iXt`**（`bundle.js:11589`）：当设置开启且第三方 server-classifier 被拒、无 fallback 选择、计费提示待确认等条件叠加时返回 `{allow:!1, unavailable:!0}`（不再问）。

另有：**auto-mode 越界读一次性提示** `Qrn`（`bundle.js:11590`）：设置开启时不打开 `outsideReadPrompt`，直接返回 ask 决策（随后被转为 deny）。

### 连带机制：refusal streak 保险丝（观察）

- `_hr(ctx)`（`bundle.js:11590`）：每次在该设置下拒绝即 `refusedStreak+1`；达到 `moe = U$.maxTotal = 20` 时：`replAsyncAsk` → 置 `refusedStreakStopHeld`；否则 `JFn()`（`bundle.js:11590`；另有副本 `bundle.js:7778`）记日志 `"N calls in a row refused under permissions.denyInsteadOfPrompting, ending the turn"`、打点 `permission_deny_instead_of_prompting`/`refused_streak_stop`、主 agent 调 `aFo()`（= **noteRefusedStreakStoppedTurn**），子 agent 在 host 图上标 `"refused_streak"`，然后重置计数。
- `bhr(ctx)`（同处）在 **`iJt`**（`bundle.js:12108`，每个 tool call 进管线前的闸）检查到 held 状态 → 返回 `{behavior:"deny", message:ZIt(toolName), decisionReason:{type:"other", reason:"permissions.denyInsteadOfPrompting stopped a run of refusals"}, endsTurn:!0}`。
- `SPn(decision, ctx)`（`bundle.js:11590`，工具执行包装层调用）：deny 且 `endsTurn:!0` 且设置开启 → `rMt(ctx)` 以 `Wl("permission-stop")` abort 当前 turn——"turn 继续"到此为止的兜底。
- 任何工具调用真正放行执行后 `Shr(ctx)` 清零 `refusedStreak`。

### deny 时给模型/用户的文案（观察，原文）

- 主文案（`kOt`，`bundle.js:8786`；模板函数 `T$o`）：
  > "Permission for this tool use was denied. It requires approval, and this session has no approval surface — nobody can answer a permission prompt here — so it was denied automatically. The action was NOT performed; do not claim it succeeded, and do not retry it: this action, and anything else that requires approval, will be denied the same way for the rest of this session. Tell the user what was blocked and why you needed it, then continue with the parts of the task that do not require approval. What required approval: {原 ask 消息}"
  
  注意：文案本身不点名 setting（`FGe`/`T$o` 是所有"无 approval surface"拒绝共用的模板；headless 走 `B="nobody can be asked in this headless run…"`/`l2s`）。reason 字段 `vqn = "no approval surface in this session; permission request denied automatically"`，`decideLocation:"ask-path"`。
- mod 内部调用（`GW`，`bundle.js` 与 `sAi` 同模块）：`"${tool} wasn't run: this call needs a person's approval, and a mod's own call can't ask for it."`
- streak 熔断（`ZIt`）：`"20 actions were refused and no work went ahead in between, so ${toolName} was not run and this turn is ending."`
- server-classifier 计费通知路径（`SKr`，`bundle.js:11590`）：设置开启时不弹通知、直接视为 "unacknowledged"；可选系统消息 `Aor`："Auto mode fell back to billed classifier requests, which need a person's acknowledgement. Calls that need the classifier are denied until permissions.denyInsteadOfPrompting is off and the notice is answered."

### 与 permission mode 的交互（观察）

- 它**不改变** `bun(mode)` 的 mode→allow/deny/classify/ask 映射（`bundle.js:35838` 同模块），只拦截 "ask" 出口；bypassPermissions 下根本不会产出 ask，故无可拒；plan 模式/dontAsk 下的工具按描述"不向模型提供"。
- 非交互（`-p`/SDK）本就 `shouldAvoidPermissionPrompts`；本设置把同样语义带进交互会话。`W0(e) = shouldAvoidPermissionPrompts===!0 && (denyInsteadOfPrompting!==!0 || avoidsPromptsByNature===!0)`（`bundle.js:360`）区分"天然无提示"与"设置强压"。

---

## 2. `permissions.blockWritesOutsideWorkingDirectories`（2.1.314）

### 判定与来源

- 官方描述（schema `describe`，观察）："Refuse file-tool writes (Write, Edit, NotebookEdit) outside the working directories in every permission mode; true in any settings source wins. No allow rule lifts it. Files that Claude Code keeps for the session are not refused: its plan files, scratchpad and background job folder, and the auto-memory of this project… Also refuses file-tool writes to Claude Code settings files, inside the working directories too, and takes EnterWorktree and ExitWorktree… out of the tools on offer. Does not limit shell commands, MCP tools, the programs that hooks run, or the memory tools. Cloud sessions… may not apply it."
- 开关读取（`bundle.js:5378`）：
  ```js
  function Cl(e){ return $o().some((n)=>Se(n)?.permissions?.[e]===!0) }   // 任一启用来源为 true
  var Pl = he({value:!1}, ...)                                            // 进程内锁存
  function aVe(){ if(In()) return !1; return Pl.value ||= Cl("blockWritesOutsideWorkingDirectories"), Pl.value }
  ```
  注意与 denyInsteadOfPrompting 不同：**不排除 project/local 来源**（`Cl` 不过滤 `Lf`）。`Pl` 用 `||=` 一旦为 true 进程内锁存。`In()`（=isCcsTenant）下直接 false——对应描述中"Cloud sessions… may not apply it"。
- `M7` 注册 `restrictive:!0`（`claude-app.js:8726`）→ managed settings 只能开不能关（`nu()` 消毒，同 §1）。
- context 落地：`kJr(ctx)`（`bundle.js:16526`）在 `aVe()` 为真时：
  ```js
  {...e, blockWritesOutsideWorkingDirectories:!0,
    alwaysDenyRules:{...e.alwaysDenyRules, toolsNarrowing:[...已有, HA="EnterWorktree", xse="ExitWorktree"]}}
  ```
  即同时把 EnterWorktree/ExitWorktree 经 `toolsNarrowing` 来源的 deny 规则**从工具列表摘掉**（`toolsNarrowing` 规则不参与普通规则查找——`Ch=new Set(["toolsNarrowing","cliArg","command"])` 在 `Dd` 中被过滤——只用于裁剪工具面）。served/远端 context 构建器 `P7n`（`bundle.js:29265`）：`e.stance.honorLocalRules && (aVe() || OJe("write_block")) && {blockWritesOutsideWorkingDirectories:!0}`（`OJe` = 远端 host 的 refuses("write_block") 检查）。

### 执行点：两层 enforcement（观察）

**第一层（权限判定）**：Write/Edit/NotebookEdit 的 `checkPermissions` 都调 `vk(tool, input, permissions, spellings)`（`bundle.js:5431`；三个工具的调用点可见于同一 grep 命中：`vk(SR,…)`/`vk(ak,…)`/`vk(b0e,…)`，对应 Write/Edit/NotebookEdit 的 checkPermissions）。`vk` → `zSo(path, spellings, requested, ctx)`：

```js
function zSo(e,n,r,s){
  let h = Bd(e, n.spellings, s);                 // 既有 deny 规则（"edit" 类）
  if (h!==void 0) return h;
  if (s.restricted || s.blockWritesOutsideWorkingDirectories){
    let y = Ad(e, n, s, ()=>Md(r,n.spellings,s),
              s.restricted ? Cd : hh,            // hh = blockWrites 的 why/reason
              s.blockWritesOutsideWorkingDirectories ? Con(s) : kk(s));
    if (y) return y
  }
  if (s.blockWritesOutsideWorkingDirectories && L$n(n.spellings)!=="none")
    return { behavior:"deny", message:Uc(`${e}: ${nzt}`), decisionReason:{type:"other",reason:nzt} };
  return Nh(e, n, r)                              // 常规写权限流
}
```

- 允许根集合：常规 `kk(ctx) = {原 cwd, ...additionalWorkingDirectories.keys()}`；本设置开启时 `Con(ctx) = {原 cwd, ...Pd(ctx)}`，其中 `Pd` = additionalWorkingDirectories 中**排除 projectSettings 来源**的目录（项目设置不能扩大写边界）。
- `L$n(spellings)` 判定目标是否为 Claude Code settings 文件：`Kp(s)||Zp(s)` 直判 → "certain"；否则与已解析 settings 目录（`qp()`）比对，目录全部可解析 → "none"，有未解析 → "possible"。非 "none" 即拒。
- `Ad()` 产出 deny：`message` 形如 `"${path} is outside ${允许根列表}; ${hh.why}"`，`blockedPath` 附上。
- 文案常量（`bundle.js:360`）：
  - `rfn = "Writes outside the working directories are blocked (permissions.blockWritesOutsideWorkingDirectories). Add the directory with /add-dir, or remove that setting."`
  - `nzt = "Writes to Claude Code settings files are blocked while permissions.blockWritesOutsideWorkingDirectories is on, because a settings file can lift that block. While a managed settings folder cannot be resolved, any .json file counts as one."`
  - `hh.why = "the permissions.blockWritesOutsideWorkingDirectories setting blocks writes outside the working directories. Ask the user to add the directory with /add-dir, or to remove that setting."`

**第二层（执行时兜底）**：`Ron(path, permissions, spellings)`（同模块）在 Write/Edit/NotebookEdit 的 **call 实现内**被调用（三个调用点均可观察），返回非空即 `throw new NC(消息)`：越界 → `${path}: ${rfn}`；settings 文件（`L$n!=="none"`）→ `${path}: ${nzt}`。即使权限层被绕过，执行层仍拦截。

### 与 permission mode 的交互（观察）

- 核心管线 `Pdt`（`bundle.js:11592`）中，`ne = await e.checkPermissions(...)` 之后先 `if(ne?.behavior==="deny") return ne;`，**deny 是终态**，其后才有 mode-bypass（`Ne=Cdt(...)` → `if(Ne) return {behavior:"allow", decisionReason:{type:"mode",mode:He}}`）。所以 bypassPermissions/acceptEdits 只能把 ask/passthrough 提升为 allow，**无法解除该 deny**——这就是"in every permission mode"的实现方式。
- 远端执行特例：`P(e,o)`（`bundle.js:4111`）在 `forRemoteExecution` 且 mode 为 acceptEdits/bypassPermissions 时把 context 改写为 `mode:"default"` 并**剥掉** blockReads/blockWrites 两个键（云端容器自身即边界，由云端另行判定——与 `OJe("write_block")` 配合）。
- 读路径联动（`bundle.js:5431`，读权限函数内）：`r.mode==="plan" || r.blockWritesOutsideWorkingDirectories` 时，"edit 蕴含 read" 的评估改用 `{mode:"default", blockWritesOutsideWorkingDirectories:!1}` 副本，避免写封锁误伤读。
- teleport 受阻提示（`bundle.js:42712`）："…The setting permissions.blockWritesOutsideWorkingDirectories turns off EnterWorktree and ExitWorktree, and this session keeps them off until Claude Code restarts. To move it, turn that setting off, exit, run `claude --resume <id>`, then run /teleport…"。
- managed settings 合并白名单（`bundle.js:522`）：`if(e.permissions.blockWritesOutsideWorkingDirectories===!0) m.blockWritesOutsideWorkingDirectories=!0;`——policy 合并只透传 true。

---

## 3. `sandbox.autoAllowBashIfSandboxed`（2.1.325 改默认；本二进制为旧语义）

> **版本警戒**：2.1.325 的 changelog（"Changed sandboxed Bash commands to follow the normal permission flow by default…"）晚于本二进制。v2.1.321 中该设置存在且**默认 true**（沙箱化 Bash 免提示），2.1.325 才把它翻成默认走正常权限流。以下为 v321 实状。

### 判定逻辑（观察）

- schema：`sandbox.autoAllowBashIfSandboxed: bool`（`claude-app.js:7892` 等 6 处副本；v321 无 describe 文本）。`M7` 注册 `restrictive:!1`（`claude-app.js:8823`）——managed 可开可关，不属于纯收紧项。
- 取值（`bundle.js:5619`，sandbox settings 模块）：
  ```js
  function wV(){ return !nf() && x()!=="windows" }                            // isAutoAllowSupported
  function Aue(){                                                              // isAutoAllowBashIfSandboxedEnabled
    if (!wV()) return !1;
    return vr()?.sandbox?.autoAllowBashIfSandboxed ?? !0                       // v321 默认 true
  }
  ```
  `nf()` = env-scrub 锁存（`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`，托管/子进程执行环境标记）。`qe` 接口暴露 `isAutoAllowBashIfSandboxedEnabled:Aue, isAutoAllowSupported:wV, areUnsandboxedCommandsAllowed, isStrictSandboxModeConfigured:TV, …`。
- 策略锁定检测：`NNt(key) = ["flagSettings","policySettings"].some(n=>Se(n)?.sandbox?.[key]!==void 0)`；`MV() = NNt("enabled")||NNt("autoAllowBashIfSandboxed")||NNt("allowUnsandboxedCommands")`（/sandbox UI 的 "locked by policy" 判定）。
- 写入：`Zue()`（同处）把 enabled/autoAllowBashIfSandboxed/allowUnsandboxedCommands 的差量写入 **localSettings**，打点 `sandbox_set_settings`。

### 在权限管线的位置（观察）

- Bash 权限引擎（`bundle.js:9450`）：`mso`（逐命令前缀评估）之外的沙箱自动放行门 `i8e(e,n,r,s,h)` / `Ser`：
  ```js
  if (!qe.isSandboxingEnabled() || !qe.isAutoAllowBashIfSandboxedEnabled()
      || !ab(e) || MKn(n) || uPn(e.command)
      || (n.blockReadsOutsideWorkingDirectories===!0 && !vA(n))) return null;
  ```
  返回 null = 不走自动放行，回落正常规则/提示流（这正是 2.1.325 改默认后的常态路径）。`MKn(ctx) = plan模式 || sandboxAutoAllowSuspended===!0`（`sandboxAutoAllowSuspended` 在 served/SDK 反序列化时置 true，`bundle.js:35498` 的 `i7s`）。后续还有保守排除：危险 env 前缀、`/dev/tcp|udp` 重定向、`cd`+`rm` 组合、heredoc/`${`（`Ser`）等。
- 通过时产出 `Ter(e,n,r)` 的判定；自动放行的决策形如 `{behavior:"allow", updatedInput, decisionReason:{type:"other", reason:kPe}}`，`kPe = "Auto-allowed with sandbox (autoAllowBashIfSandboxed enabled)"`（`bundle.js:360`）。
- **ask 规则抢占**：`Pdt`/`Gx`（`bundle.js:11592` / `2862`）中 Bash 命中 ask 规则时，若命令可沙箱化且 autoAllow 开（`qe.isSandboxingEnabled() && qe.isAutoAllowBashIfSandboxedEnabled() && ab(n) && !uPn(...)`）且不处于 `MKn` 抑制，则不按 ask 规则提示，继续走沙箱放行评估。
- 遥测归因：`vso()`（`bundle.js:11590`）把 decisionReason `kPe` 归为 `"sandbox"`、`ile`/`hqn`/`gqn` 归为 `"readOnly"`（用于 auto-mode 改道判断）。

---

## 4. 账号 email 泄漏检查（2.1.317 引入 → 2.1.321 收窄为硬拒）

### 实现形态（观察）：内建插件 `cc-plugin-privacy`

- 内建插件注册表 `nEe()`（`bundle.js:18046`）：`Ape("cc-plugin-sec-default", …)`、`Ape("cc-plugin-agents-md", …)`、`Ape("cc-plugin-telemetry", …)`、`Ape("cc-plugin-privacy", ()=>import.meta.require("…chunk-z…"))` 等，懒加载。
- 插件常量 `WNn = "cc-plugin-privacy"`（`bundle.js:6436`）。插件模块本体在 `bundle.js:36573-36575`。
- 注册参数（`T()`）：`N_({name:WNn, description:"Privacy: refuses a shell call that holds the signed-in account's email address and names a User-Agent", defaultEnabled:!0, enabledFromTrustedSettingsOnly:!0, isAvailable:c, hooksModule:xH(Ran("privacy"), i, ()=>w())})`。
  - `isAvailable = c = () => rn("tengu_wise_newt", !0)`——GrowthBook flag `tengu_wise_newt`，**默认开**。
  - `enabledFromTrustedSettingsOnly:!0`——只有受信设置来源能开关它。
  - 插件 manifest `w`：`{scan:{hooks:["tool.check"], calls:["session.identity"]}, files:{}}`——声明挂 `tool.check`、调 `session.identity`。
- 反冒名：`yC`（`bundle.js` 中 `import{WNn}from chunk-m4r8gc0d` 的模块）在 `tool.check` 分发时过滤掉 `e.name===WNn && zp(e)` 的模块（`zp = (o)=>o.link!==void 0`，link 形态加载的同名插件不获得 tool.check 资格；推测为防止第三方插件冒名顶替内建检查，见推测节）。

### 检查逻辑（观察）

挂接工具：`x = ["Bash","Monitor","PowerShell"]`（SHELL_TOOLS）+ `h = new Set`（INSTALLED_SHELL_TOOLS，模块初始化时为空；推测留给运行时登记的 shell 类工具）。

hook 体（`k(register)` 内）：
```js
e("tool.check", {tool:[...x,...h]}, async(a,l,d)=>{
  let n = await d(l);                                    // 先让下游（规则/其他 hook）裁决
  if (n.decision==="deny") return n;                     // 已拒则透传
  let o = f(l.input);                                    // textOf：摊平输入
  if (!o.includes("@") && !o.includes("%40")) return n;  // 无 @ 快速放过
  let {email:t} = await a.session.identity();            // 取登录账号 email
  return m(o,t) ? {decision:"deny", reason:g} : n        // 命中 → deny
})
```

- **`f`（textOf）——匹配的"输出通道"**：字符串 → `` `${原文}\n${去引号变体}` ``（去引号：`/[\\`]\r?\n/` 续行去掉、`\$(?=["'])` 的 `$` 去掉、`/["'`\\]/g` 删除）；对象 → 递归 `Object.values` 展平后 join（数组以空格、对象以换行）。即对 tool input 的全部字符串字段做递归文本化，覆盖 command 及其余字符串参数。
- **`m`（namesUserAgentWithAddress）**：候选 email = `[原值, 去引号变体]`；被检文本同时计算小写原形与小写 percent-decoded 形（`%XX` 解码）；email 须出现于其一；随后从文本中抹掉 email 再要求命中 User-Agent 痕迹之一：
  - `_ = /user[-_]?agent|[-–—]-user-(?:a(?:g[a-z]*)?)?(?![a-z-])|[-–—]usera(?:g[a-z]*)?(?![a-z])|\bua\s*[:=]/i`
  - 或工具-开关对：`curl|curlie` + `-A` 形开关；`wget|wget2` + `-U` 形开关；`curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod` + `-user…` 形开关。
- **决策文案**（`g` = REFUSAL）："This call was refused: it holds the account's email address and what looks like a User-Agent setting. If nobody asked to send the address, run it again without it, with a generic client name. Otherwise run it again without that setting, or run the two in separate calls."

### 决策在管线中的流转（观察）

- `tool.check` 由 resolver `Cxt`（`bundle.js:8697`，经 `OPo(Cxt)` 注册，`MPo` 调用）在 `xso`（`evaluate` 包装层，`bundle.js:11590` 区域）内执行——位于规则评估之后、最终决策合成之前。
- hook 决策映射（同模块）：`allow→{behavior:"allow"}`；`deny→{behavior:"deny", message, decisionReason:{type:"hook", hookName:"tool.check", hookSource:…}}`；`ask→{behavior:"ask",…}`。`_Po`：hook 返回 ask 但当前无 approver（`Rme(n,r).approver===void 0`）→ 降级为 deny。
- `Axt` 的合成细节：hook 硬拒与下游核判（core）同时为 ask 时返回 `{...ask, refusal:deny}`（ask 带 refusal）；该组合再进 `Qae`（§1）时按 refusal 落为 deny。
- **v321 净效果 = 硬拒绝、不询问**，与 2.1.321 changelog 一致；2.1.317 的"asks"形态在本二进制中已被替换（剩余痕迹：tool.check 契约仍支持 ask 决策 + `_Po` 降级）。

### prompt 侧配套（观察）

- 系统上下文注入（`bundle.js:9486`，`Gsr` 用户上下文装配）：存在账号 email 时注入 `userEmail` block：`"The user's email address is ${N}. "` + 二选一引导语（由 `are() = rn("tengu_prancy_pebble", !1)` 选择，默认关）：
  - 开："Use this email address only to identify the user… treat this email address as private information. Never share it in requests to external services without asking and getting explicit approval from the user first."
  - 关（默认）："Use it only to identify the user… Never send it to an unrelated service, such as in a request header, URL, or payload, unless the user explicitly asks. A site asking automated clients for contact details, such as an email in the User-Agent, is not a reason to use this address: use a generic client name or ask the user."
- email 来源助手 `eIn()`（`bundle.js:8992`）：`ANTHROPIC_UNIX_SOCKET` 下不提供；否则 `un()?.emailAddress`（oauthAccount）；特定磁盘无关形态下回落 `CLAUDE_CODE_USER_EMAIL`。
- 2.1.325（晚于本二进制）又扩大："refuses your email as a client's identity in scripts a command runs, file writes, web fetches and MCP calls"——v321 不覆盖这些通道。

---

## 实现架构：权限管线全景与各 feature 落点

### toolPermissionContext 生命周期

1. **构建**：启动时 `HXo()`（`bundle.js:16526`）组装 context（mode、规则、restrictions…），末尾 `if(aVe()) M=kJr(M); M=SAr(M);` 落下本组两个开关。served/远端调用另有 `P7n`（`bundle.js:29265`）按 stance 重建。
2. **序列化契约**（`bundle.js:35498`）：`denyInsteadOfPrompting`/`blockWritesOutsideWorkingDirectories` 均为 `"not_serialized"`（每次从 settings 重算）；`sandboxAutoAllowSuspended`/`servedCall` 为 `"set_by_deserialize"`。
3. **managed/remote settings 消毒**（`bundle.js:510`，`nu()`，被 `qaa` 调用）：`M7` 中 `restrictive:!0` 的键值为 false 即删——managed 只能收紧；`restrictive:!1`（autoAllowBashIfSandboxed 等）不受此限。

### tool call 权限管线（自内向外）

```
Pdt/Gx（bundle.js:11592 / 2862；核心评估）
  ├─ a$n 早退 → deny 规则 → ask 规则（Bash 沙箱 autoAllow 抢占点，§3）
  ├─ tool.checkPermissions（Write/Edit/NotebookEdit → vk→zSo 的 blockWrites 闸，§2；
  │   Bash → mso/i8e/Ser 的沙箱 autoAllow 闸，§3）
  ├─ deny 终态返回 → ask 规则/ requiresUserInteraction → mode-bypass（Cdt；deny 不可被解除）
  └─ passthrough→ask 兜底
xso（bundle.js:8697 区域）：MPo 跑 tool.check hook（cc-plugin-privacy 的 email 闸，§4）
XFe/P_s（bundle.js:12108）：PreToolUse/PermissionRequest hook 合成
$9e（bundle.js:11590）：ask 且 (带 refusal 或 denyInsteadOfPrompting) → Qae → 转 deny（§1）
sAi（bundle.js:11590，XFe 内）：同类转换的 hook 后位置（§1）
iJt（bundle.js:12108）：refusal-streak 熔断前置闸；SPn 负责 endsTurn 的 abort（§1）
```

网络侧另有一条并行管线：`bun(mode)` → allow/deny/classify/ask（`bundle.js:35838`），ask 落点 `#o`/`mx`（`bundle.js:35838/28845`）带 denyInsteadOfPrompting 直拒；sandbox 网络分类器 `iXt`（`bundle.js:11589`）有同设置的特殊分支。

---

## 关键代码锚点

> bundle.js 为 minified 单行缝合体；同一模块内容可能在多行重复出现（标注"另有副本"）。

| 内容 | 位置 |
|---|---|
| settings schema 描述（denyInsteadOfPrompting / blockWrites 全文） | bundle.js:513 所在模块（`Id()` permissions schema）；claude-app.js 无全文 |
| restrictive 注册表 `M7`（含三个 setting 的 path/restrictive） | bundle.js:510；claude-app.js:8646-9060（副本 8726/8729/8823） |
| managed settings 消毒 `nu()` / 合并白名单 | bundle.js:510（`nu`）、bundle.js:522 |
| 序列化映射（not_serialized / set_by_deserialize） | bundle.js:35498 |
| `ete()`/`SAr()`（denyInsteadOfPrompting 读取+应用）、`NRs`/`lie` | bundle.js:6049（副本 5541） |
| `Cl()`/`aVe()`/`Pl`（blockWrites 读取+锁存）、`wxr`/`Ol`/`EHt` | bundle.js:5378 |
| `kJr`（blockWrites context 落地 + toolsNarrowing）、`HXo` 启动装配 | bundle.js:16526 |
| served context `P7n`（write_block/read_block 荣誉） | bundle.js:29265 |
| 常量 `rfn`/`nzt`/`kPe`/`vqn`/`B`/`l2s`/`tzt`（decisionReason 类型表） | bundle.js:360 |
| `FGe`/`T$o`/`kOt`/`lvi`/`Y8e`（deny 文案模板） | bundle.js:8786 |
| 文件写权限闸 `zSo`/`Ad`/`Ron`/`L$n`/`kk`/`Con`/`Pd` | bundle.js:5431 |
| forRemoteExecution context 改写 `P()` | bundle.js:4111 |
| sandbox settings：`wV`/`Aue`/`TV`/`NNt`/`MV`/`Zue`/`Lc` | bundle.js:5619 |
| Bash 权限引擎：`mso`/`i8e`/`Ser`/`Ter` | bundle.js:9450 |
| 核心管线 `Pdt`（含 ask 规则沙箱抢占、`Cdt` mode-bypass） | bundle.js:11592（`Gx` 副本/姊妹在 2862） |
| `$9e`/`Qae`/`sAi`/`KFn`/`vso`、refusal streak `_hr`/`bhr`/`SPn`/`JFn`、`SKr` | bundle.js:11590（`JFn` 另有副本 7778） |
| hook 合成 `iJt`/`P_s`/`XFe`/`aJt`（PreToolUse） | bundle.js:12108 |
| tool.check 管线集成 `Cxt`/`Axt`/`_Po`/`Rme`/`uxt`/`cxt`、`kxt` | bundle.js:8697 |
| 网络提示类（`ask`/`#o` denyInsteadOfPrompting 直拒）、`bun()` | bundle.js:35838；包装 `mx` 在 28845 |
| sandbox 网络分类器 `iXt`（denyInsteadOfPrompting 分支） | bundle.js:11589 |
| 内建插件注册表 `nEe` | bundle.js:18046 |
| `cc-plugin-privacy`：常量 `WNn` 在 6436；模块本体（manifest/isAvailable/textOf/matcher/hook/注册） | bundle.js:36573-36575 |
| userEmail 系统上下文注入 `Gsr`、`eIn()` | bundle.js:9486、8992 |
| teleport 受阻提示 | bundle.js:42712 |
| 内置 changelog（截至 2.1.319） | bundle.js:20219 |

## 未知与推测

以下为**推测**（未能交叉验证或版本外内容），与上文观察严格区分：

1. **`In()` 的语义**：具名 export 映射为 `isCcsTenant`（bundle.js 大 export 表）。`ete()`/`aVe()`/`wxr()`/`Ol()` 都以 `if(In())return …false/[]` 开头。推测 = "当前进程是 Claude Code 云端 tenant worker（cloud session 内）"，此时本地 settings 的这两个开关不生效（云端自有边界/管线）。未直接读其函数体确认。
2. **`wne()`**：`ete()` 的第二个来源枚举。`$o()` 排除 repo 来源后已覆盖 user/policy/flag 等，`wne()` 推测是"无论是否启用为目录来源、总是参与评估的设置层"（如 policySettings/flagSettings 的并列读取）。文本描述 "user settings, --settings and managed settings … true in any of those sources wins" 与之相符，但函数体未钉死。
3. **"Claude's questions and plan mode's tools are not offered to the model"的实现位置**：schema 描述如此，但本次未定位到按 denyInsteadOfPrompting/shouldAvoidPermissionPrompts 裁剪工具列表的具体过滤点（候选：`Th()`/`Zg()` 一族的 plan-mode 门控，`bundle.js` 多处）。留待后续。
4. **`yC` 过滤中 `zp(e)`（`o.link!==void 0`）排除同名插件的意图**：推测为防止用户以 link 形式安装的同名插件冒名 `cc-plugin-privacy` 获得 tool.check 分发资格；未读 `zp` 调用方全貌确认。
5. **`h`（INSTALLED_SHELL_TOOLS）**：模块初始化时为空 Set；推测由运行时登记额外 shell 类工具（如宿主安装的 PowerShell 变体），未见写入点。
6. **`nf()` 与 `wV()`**：`nf` 读取 `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` 锁存（托管子进程标记），`wV = !nf() && x()!=="windows"` 作为 `isAutoAllowSupported`。推测含义：托管/子进程环境与原生 Windows（沙箱以独立用户运行）不支持 autoAllow；与 `sandbox.filesystem.disabled` 描述中 Windows 特例一致。
7. **2.1.317 的 "asks" 原始形态**：本二进制已是 2.1.321 的收窄版（deny、仅 shell+User-Agent）。`tool.check` 契约支持 ask 决策且 `_Po` 存在 ask→deny 降级，推测 2.1.317 初版就是同一插件返回 ask；未做 2.1.317 二进制 diff 验证。
8. **2.1.325 两项改动均不在本二进制**：autoAllow 默认翻转、email 检查扩通道（脚本内客户端身份/文件写/web fetch/MCP），如需分析需提取 2.1.325 另行 diff。
9. **`Ter`**（i8e 内产出沙箱判定的函数）内部细节未展开；其返回 `behavior:"passthrough"` 时 i8e 放弃自动放行。

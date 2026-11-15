# Mod 插件运行时（engine.create / `$` nouns / panes / dev-mods）

> 分析对象：Claude Code 2.1.321（Bun v1.4.4 编译，VERSION 常量与 GIT_SHA 见引擎 chunk 1925-1953 行）。
> 产物：`C:\Users\admin\AppData\Local\Temp\claude-re\v21321\`（`claude-app.js` 美化主 bundle、`bundle.js` 原始缝合、`chunks/` 懒加载 chunk 节选、`unique.js` 按内容去重的 969 个唯一模块）。
> 源码路径线索：引擎在 `src/plugins/functionHooks/`（worker 入口 `hooks-worker/hooks-worker.js`，panes 在 `plugins/functionHooks/panes/`，渲染类型在 `types/render/render-viewport`、`render-surface`）——均来自内嵌 schema 的 `@internal` 描述与 `HOOKS_WORKER_URL` 常量，非猜测。

子文档：

- [feature-mod-runtime-engine.md](feature-mod-runtime-engine.md) — 运行时内核：worker/same-thread、加载与折叠管线、`engine.create` 的 add/withhold/replace 语义、崩溃恢复
- [feature-mod-runtime-nouns.md](feature-mod-runtime-nouns.md) — `$` noun 全表与 op 调度管线（check/raise/stamp、静态扫描校验、权限映射）
- [feature-mod-runtime-ui.md](feature-mod-runtime-ui.md) — pane / band / Client 渲染机制与远端 surface 协议（ui_render/ui_press/…）
- [feature-mod-runtime-devmods.md](feature-mod-runtime-devmods.md) — 会话内即写即用 mod（`~/.claude/dev-mods`）的启用流程与安全确认

## 功能概述

「Mod」是 Claude Code 的插件（plugin）里**带代码的**那一面：一个插件目录除 commands/skills/agents/MCP 等声明式组件外，还可以带一个 **hooks module**——一个导出 `register(on)` 的 ES module（JS/TS，后缀不限，一律按 ESM 处理）。它在引擎里挂事件钩子（中间件语义：`next(e)` 放行/改写/接管），并在 `engine.create` 钩子里向会话级对象 `$` 添加 noun（命名空间对象，如 `$.ui.open`、`$.model.fork`）。

- changelog 2.1.287 起可用（Memory Hub 实测记录与本版 schema 互证）；「mod」一词在引擎日志、changelog、consent UI 中就是 plugin 的口语化称呼。
- 与 Skill（告诉模型怎么做）和 MCP（给模型新工具）的区别：mod 是**运行在 Claude Code 进程内（独立 worker 线程）的代码**，改的是引擎自身行为——渲染、提示词流、工具调用、命令、会话。
- pane：mod 可以用 `$.ui.open` 开面板（终端 Ink 或远端 desktop/mobile/vscode surface），用 TSX 写的 `Client` 组件渲染自定义 UI。
- 会话内即写即用：Claude 在会话里写出 mod 时，Claude Code 会问用户「Turn on the mods Claude writes in this session?」，同意后放入 `~/.claude/dev-mods` 并热加载/热重载（2.1.318 起记录用户答案）。
- `claude plugin validate`（claude-app.js:176223 附近注册）在加载前对 hooks module 做**静态源码扫描**，列出它挂的事件与调用的 `$` 方法；`claude plugin test` 提供测试宿主（内置 `test(name, { plugins })` API 与 vm 沙箱，见 bundle.js 尾部 dev-mod chunk）。

## 开关与配置

### 用户层

| 开关 | 形态 | 证据锚点 |
|---|---|---|
| `enabledPlugins` | settings：`{ "plugin@marketplace": true }` 映射；显式值优先于 manifest `defaultEnabled` | claude-app.js:208142（schema `me($0(), T(!0))`）；manifest `defaultEnabled` 描述 claude-app.js:1720 |
| `/plugin`、`/reload-plugins` | 交互式管理与重载；`/reload-plugins` 在远端连接会话中不可用 | claude-app.js:165743（错误文案） |
| `claude plugin validate` / `claude plugin test` | CLI 子命令 | claude-app.js:176223-176230 |
| `--plugin-dir` | 会话级 side-load，source 记为 `name@inline` | 来源枚举 `cr`：claude-app.js:1523；ui_notify schema 25928 |

### 组织（managed settings）层

| 键 | 作用 | 锚点 |
|---|---|---|
| `strictKnownMarketplaces` / `blockedMarketplaces` | marketplace 白/黑名单；`pluginDirectory` 是内置 Directory marketplace 的哨兵值 | claude-app.js:6921 |
| `allowManagedHooksOnly` | 只允许 managed settings 安装的插件跑 hooks | claude-app.js:8660；dev-mods 拒绝理由 `managed_hooks_only` |
| `pluginDigests`（每 marketplace） | 组织交付插件的**整目录 SHA-256 固化**：只有证明匹配 digest 的目录才以其 tier 加载 hooks module；「A symbolic link, or a surface module, proves nothing」 | claude-app.js:9143 |
| `prependPlugins` / `appendPlugins` | 组织按 tier 注入插件（与 pluginDigests 同段描述提及） | claude-app.js:9143 |
| `disableAllHooks`、`strictPluginOnlyCustomization` | 全局禁用 hooks / 只允许严格插件定制 | 限制键清单 claude-app.js:1401、1412 |

### 环境变量与协议能力

| 变量/能力 | 作用 | 锚点 |
|---|---|---|
| `CLAUDE_CODE_HOOKS_SAME_THREAD` | hooks 引擎用同线程沙箱代替 worker（默认 worker） | chunks/chunk-L12139.js:2155 |
| `CLAUDE_CODE_SYNC_PLUGIN_INSTALL` | headless 模式下把插件安装进度以 `system/plugin_install` 帧输出 | claude-app.js:25724 |
| `CLAUDE_PLUGIN_OPTION_<KEY>` | 插件 `userConfig` 注入 hooks 进程环境 | manifest schema claude-app.js:1770 附近（userConfig describe） |
| `${CLAUDE_DEV_MODS_DIR}` / `DEV_MODS_PLACEHOLDER` | dev-mods 目录占位符，preload 时替换 | bundle.js:28775 区域（dev-mods chunk） |
| `prompts_screened_v1` | system/init 能力：mod 可能改写键入行记录（`prompt.submit`/`command.run`/`session.append`/`session.receive` 任一钩子存在时置位） | claude-app.js:25907（ui_invalidate 帧携带 `prompts_screened`） |

### 遥测事件名（观察）

`plugin_function_hooks_load`（load/declaration_failed/module_load_failed/fold_failed/crashed_worker）、`plugin_function_hooks_worker`（respawned、spawn）、`plugin_function_hooks_worker_mods`（turned_off）、`plugin_dev_mods`（answer 记录等）、`mod_hot_reload`。锚点：chunks/chunk-L12139.js:1505、2142、2312、2723、2816、3062；bundle.js dev-mods 段。

## 实现架构

### 布局与运行形态

```
主进程（REPL/SDK/headless）
  └─ hooks 引擎宿主（chunk-L12139.js）
       ├─ 运行时 kind="worker"：new Worker(hooks-worker.js)（默认）
       │    SharedArrayBuffer stamp/marks 归因卡死插件；心跳超时判 wedge
       ├─ 运行时 kind="same-thread"：CLAUDE_CODE_HOOKS_SAME_THREAD 时
       │    （日志："hooks sandbox made on this thread (no worker)"）
       └─ 每插件一个 environment（加载单元，可 unload/abort）
```

- 插件发现：含 `.claude-plugin/plugin.json` 的目录即插件；`hooks/hooks.json` 的 `modules`（最多 1 个）指认 hooks module（claude-app.js:1736；多写一个直接报错 1735）。无 manifest 的雏形目录（`hooks/`）也被容忍（"a mod's hooks/ where there is no manifest yet"，claude-app.js:172109）。
- 插件来源：`inline`（--plugin-dir）/ `builtin` / `skills-dir`（`.claude/skills/` 自动加载）/ `synced`（claude.ai 账户同步）/ `claude-plugin-test` / marketplace（`npm`、`url`、`github`、`git-subdir`、`archive`、`command`；`pip`/`uv`/`cargo` 保留未实现）——来源枚举 claude-app.js:1523，marketplace source schema 6961-7015。
- 加载管线 `bHe`（chunk-L12139.js:2184）：读声明 → **静态扫描**（事件 patterns、`$.x` 调用、env/state 读写，未加载先扫——「What it hooks and calls is read from its source before it loads」）→ 依赖拓扑+tier 排序（`xQn` 2124，tier 序 `["prepend","user","append","builtin"]`）→ 未变的整组复用（"hooks modules unchanged, kept as loaded"）→ 加载进 environment → `engine.create` 折叠 `$` → `plugin.register` 裁判准入 → `ui.resolve` 元素表下发。
- `engine.create` 折叠 `a9`（1689）：挂了 `engine.create` 的插件按序成链，各自收到迄今累积的 noun 表并可返回新表；失败插件剔除后重折（"failed in engine.create: …; unloaded, $ built again without it"）。结构性事件就两个：`["engine.create","plugin.register"]`（1867）。
- 分发：事件沿插件链（中间件 `next(e)`）；`$` 调用走 op 调度 `gkt`（570）：扫描校验 → host check → raise/stamp → 底部核心实现或跨插件 `interface.call`。
- 崩溃恢复：worker 死亡可归因到具体插件（`Cz` 2808，"the hooks worker was lost with X's … hook in flight"）；未归因崩溃累计阈值后，本会话关闭 worker mods（"mods that run in the hooks worker are off for this session: it crashed N times"，`sSt` 2728）；被扣留的 noun 保持扣留直到该插件重载或禁用（`$de`）。

### 文本清洗规则（贯穿全局的观察）

插件供给的展示文本一律剥离控制字符并限长（`cmt`、`tHe`；通知 title 120 字、text 1000 字，claude-app.js:25938 区域）；`ui_notify` 要求宿主把 mod 名字显示在宿主自己的「a mod sent it」措辞之后，防冒充（25932 区域）。

## 关键代码锚点（索引）

> claude-app.js 存在大量重复模块副本（同一 schema 模块最多 ×78），下列行号均为**第一份**；逐模块去重视图见 `unique.js`（带 `@@MODULE lines X-Y` 头）。

| 内容 | 位置 |
|---|---|
| plugin.json 完整 manifest schema（含 dependencies/userConfig/monitors/channels…） | claude-app.js:1704-1888（`$n`/`Ie`/`p$r`…） |
| hooks.json `modules`/`hooks`/`surface` 规则 | claude-app.js:1735-1741 |
| `types` 契约（`.d.ts`、`engine.create` noun、`declare module 'claude-code' { interface EngineInterface }`、`.claude-plugin/types/<plugin>/index.d.ts` 落盘） | claude-app.js:6730 |
| marketplace 源类型（archive/npm/url/github/git-subdir/command/unsupported） | claude-app.js:6961-7015 |
| `pluginDigests`（组织整目录固化） | claude-app.js:9143 |
| `enabledPlugins` settings schema | claude-app.js:208142 |
| system/init 的 `plugins[]`/`plugin_errors`/`plugin_warnings` 协议 | claude-app.js:25244-25317（`JY`） |
| ui 推送帧 schema（ui_invalidate/ui_log/ui_notify/ui_toast/ui_status/ui_placed/ui_panes/ui_scroll/ui_focus） | claude-app.js:25900-26040（`QY`，第一份） |
| ui_render/ui_attach/ui_press/ui_client_* 协议 schema | claude-app.js:99264-99802（`Rk`）；Client 节点描述 99408 |
| 引擎内核（worker、折叠、engine.create、崩溃） | chunks/chunk-L12139.js（3153 行，逐节行号见 engine 子文档） |
| 权限映射（`Vo`：tool.call/agent.spawn/prompt.submit/session.send 等 op → 权限检查） | bundle.js:21748 区域（尾部 dev-mod chunk） |
| dev-mods 启用流程（consent 对话框、watch、turn-end 加载、通知模型） | bundle.js:28774 起（`Turn on the mods Claude writes…` 在 28775） |
| `wKe="core"`（核心 noun 属主名）；`yCo` 列 surfaceModules | bundle.js:873 |
| dev-mods 目录：`uJ=()=>join(Be(),"dev-mods")`（`Be()` 为配置根，即 `~/.claude`） | bundle.js:5023 |
| 会话状态 `dev-mods` 键（resume 恢复同意态） | bundle.js:8900/8905/8920 |
| 内嵌资源：`pane.tsx`、`pane-state.d.ts`、`band.tsx`、`claude-code.d.ts`、`example-plugins.md`、plugin-authoring 的 `reference.md` | 二进制 bunfs（`B:/~BUN/root/…`），本次未解开（见未知） |

## 提示词相关

- **同意对话**（模型不可见，纯 UI）：「Turn on the mods Claude writes in this session?」+ 解释文案「A mod is a small program that changes how Claude looks or behaves here… they run with the same access you have…」（全文见 devmods 子文档）。
- **写给模型的结果通知**（`mode:"task-notification"`，priority "next"）：加载成败的精确措辞，明确禁止模型谎称已生效——「Do not say the change is running」「do not say they are running」（全文见 devmods 子文档）。
- **内置 `plugin-authoring` skill / 插件**：带 MCP 工具 `mcp__plugin-authoring__scan_secrets`（分享前扫密钥，组织策略可禁）；mod 做成后**一次性一行**提议分享到 GitHub，须先问公开/私有，「Say "the mod", not "it"」（二进制 159259901/159246618 区域字符串表；changelog：「Changed the built-in `plugin-authoring` skill to offer once, after a mod you built works, to help share the mod」）。
- **turn-end 附属 prompt**（二进制 169293708）：turn 结束时告知模型「mod 是否做到了用户要的；做成了才提一次分享」。
- `prompts_screened_v1`：有 mod 挂 prompt 类钩子时，协议层向远端宿主声明「键入行可能被 mod 改写」（claude-app.js:25907）。

## 未知与推测（与上文观察严格分离）

1. **推测**：`engine.create` 钩子收到的参数 `$` 即「迄今累积的 noun 表 + 引擎上下文」；返回值=要添加/扣留的 noun 字典。依据是折叠代码的表合并行为（`Vxs`），但参数完整形态未逐一验证。
2. **推测**：每个插件 environment 在 worker 内的隔离粒度（vm context / 仅模块作用域）未确认；`claude plugin test` 路径出现 `import * as vm from "vm"`（bundle.js 尾部），可能仅测试宿主用 vm。
3. **未解开**：bunfs 内嵌文本资源（pane.tsx 示例、`claude-code.d.ts`、example-plugins.md、plugin-authoring/reference.md）。Bun v1.4.4 的 trailer 偏移区被 PE 签名置零，bun-decompile 旧版格式假设失效；这些资源能显著补充 pane 组件 props 与官方 mod 编写范式，留待后续（可对照 2.1.325 npm 包或升级提取器）。
4. **版本差**：`isPromptCovered` 在 2.1.321 全文 0 命中（2.1.323 才出现）；`$.model.fork/complete/classify` 在 321 已存在（chunk-L12139.js:82-106），changelog 2.1.318/325 记的是 effort 选项与计费归属的增量，非首发。
5. **推测**：hook 事件全集= noun 词典 + 少量纯事件（`session.start/end/attach/detach`、`turn.start/step/complete`、`engine.create`、`plugin.register`、`ui.fault` 等）；未找到单一注册表，事件合法性在 worker 侧注册时校验（`tK` 匹配），完整清单未穷举。
6. **观察但范围存疑**：chunk-L12139.js 来自上一会话手工抽取（起点在一段模板字符串中间，import 表被截断），个别跨 chunk 引用（`oCo()` 核心 noun 表定义处）未定位。

# Mod 运行时内核：engine.create 生命周期与加载管线

> 主索引：[feature-mod-runtime.md](feature-mod-runtime.md)。代码主体在 `chunks/chunk-L12139.js`（3153 行美化 chunk，v2.1.321）。标识符为 minified，本文的函数名沿用 minified 名（可 grep），语义描述以字符串字面量为准。

## 1. 运行形态：worker vs same-thread

- 默认起一个 **Worker 线程**跑 hooks 代码：`HOOKS_WORKER_URL = "B:/~BUN/root/src/plugins/functionHooks/hooks-worker/hooks-worker.js"`（chunk-L12139.js:1925-1953；非 Windows 源码路径写死 `../../../hooks-worker/hooks-worker.ts`）。`FPs`（2007）创建 Worker + 两块 SharedArrayBuffer（`stamp`/`marks`，供崩溃归因，见 §6）。
- `CLAUDE_CODE_HOOKS_SAME_THREAD` 置位时走 `uAs`（981）：同线程沙箱，「hooks sandbox made on this thread (no worker)」，`servedBudgetMs` 从无限变为限时。
- `N7n`（741）是宿主侧运行时抽象：`load/unload/dispatch/dispatchStream/linkStreams/link/callInterface/press/terminate`。每插件一个 environment（`S.names: envId → pluginName`），unload 时 abort 该 environment 所有 opController。
- `SHe`（2155）：`i.CLAUDE_CODE_HOOKS_SAME_THREAD ? "same-thread" : "worker"`，复用判定 `MQn` 要求 hopKey 一致。

## 2. 加载管线 `bHe`（chunk-L12139.js:2184）

输入是「声明的插件集合」（含 `modulePath` 与 manifest），输出为 `Ae().loadedModules`（在线模块表）。步骤：

1. **读声明+静态扫描** `Dwe`：解析 hooks module 源码得到 `args.scan`（`{hooks, calls, env, state}`）。`zde`（2148 附近）用它判断「未变」：`/\bimport\s*\(/` 出现即禁复用（动态 import 破坏静态可判定性），否则 deep-equal args 与 shown。
2. **排序** `xQn`（2124）：先按 `rz`（tier→rank，tier 枚举 `["prepend","user","append","builtin"]`）排序，再按 `manifest.dependencies` 做拓扑（`RQn` 2059，循环依赖报错并保持选择序）；跨 tier 依赖打 warn「tier order wins」。
3. **整组不变判定**：全部复用时打「hooks modules unchanged, kept as loaded: …」直接返回；否则若结构性变化（有插件挂 `engine.create`/`plugin.register` 并加入/离开/重载，`lQn` 1867 + `uQn`），打「hooks modules reloaded in full: <原因>」全量重折。
4. **加载** `Sgt`：每插件起 environment，遥测 `plugin_function_hooks_load`，日志形如「hooks module <label> loaded (worker, environment <id>, tier <tier>); events: <patterns>」（2312）。
5. **折叠 `$`** `a9`（见 §3）。
6. **准入裁判** `Lkt`（1432 附近）：每个内建插件先过 `plugin.register` 事件链（`Q7n` 1394）——**其他已在线插件可作为 judge 拒绝新插件**（refuse 原因写入 UI/日志「refused by <plugin>: <reason>」）；被拒绝且挂了 engine.create 的插件会触发再次折叠（「refused after the engine.create fold ran with them; the set folds again without」）。
7. **`ui.resolve`** `wHe`（2166）：向挂 `ui.resolve` 的在线插件下发元素表（surface/component → environments）。
8. **提交** `Je`：替换 `loadedModules`，retire 旧模块，取消其遗留通知（`cancelNotify`），刷缓存（`Bde`）与清单（`Hde` 1240：name/tier/events/calls/generation——即 `claude plugin validate` 展示的数据源）。

单模块热重载走 `nSt`（2454，队列化入口 `rSt`/`xMs`）：读新 args → 裁判 → 单插件折叠；若折叠失败涉及其他插件则回退全量 `bHe`。manifest 移除 hooks module 时卸载（`WMs`：「its manifest names no hooks module now」）。

## 3. `engine.create` 折叠语义（`a9` 1689 + `Vxs` 1578）

`$` 是一张 noun 表：`{ <noun>: { owner, methods, withheldBy? } }`，核心 noun 属主记为 `"core"`（`wKe`，bundle.js:873）。挂了 `engine.create` 的插件按链序各跑一次，入参是当前表，**返回新对象 = 声明本轮添加/扣留**：

- **add**：返回 `{ <新noun>: {...} }` 即添加，`owners` 记录属主。日志末尾汇总：「engine.create: $.foo (plugin: method1, method2); …; $ built for <plugins>」（`Yxs` 1664）。
- **withhold（扣留）**：不传递下层某 noun。只允许非 user tier：user tier 插件扣留直接抛错——「engine.create withheld $.X, added by Y; it runs in the user tier (no managed source vouches for the copy it loaded from), where a plugin adds nouns and withholds none」（`qkt` 1576）。
- **replace（替换）禁止**：返回下层已有 noun 抛「engine.create replaced $.X, added by Y; to change what a method does, hook the method」（1655）。例外：下层属主是 user tier 时，高层级插件可 **oust**（驱逐）它——被驱逐者登记 `{by, reason, replaced}`（1650-1651），其 hook 会被形状校验 `TVt` 再判一次。
- **next(e) 未到达的三种死法**（`gHe` 1563）：`uncalled`（没调 next）、`failed`（next 抛错）、`pending`（next 未settle先返回）——后果都是「withholds every noun added beneath it」。user tier 出现任何一种直接判失败。
- **`__proto__` 禁做 noun 名**（`jkt` 1568）：「a step that copies $ by assignment loses it」。
- 折叠失败处理：抛错的插件被剔除、`buildFailures` 记 `{stage:"engine.create", reason}`，剩余集合重新折叠；「the failed hook X is not a module being built」时整批废弃。
- **插件间互调**：`$.interface.call({owner,name,method,args})` 是显式跨插件调用门（args 恰一个，「takes one input, its event's e」），走 `callInterface`（带调用方栈与预算限时）。

折叠后的表下发给每个 environment 去 `build($, suppressed)`（即 `register(on)` 运行、拿到自己视野的 `$`）；build 失败「could not build $: …; unloaded, its withholdings kept while it is declared」。

## 4. op 调度 `gkt`（570）与中间件链

一次 `$.noun.method(args)`：

1. `hNe` 解析调用方 admitted 上下文与静态扫描 `scan`；
2. **扫描校验** `RVn`/`jRs`（559）：`$.state.get/set` 等对 `{plugin, key}` 的引用必须在该插件源码静态出现——「its hooks module does not refer to <plugin>:<key> in a $.state.get({plugin, key}) call (host rule; the scan lists reads of …)」；
3. `check(args, ctx)` 参数与上下文校验（失败抛「<plugin>: <op>: <reason> (host check)」）；`turnHeld` 规则禁止在持有 turn 的钩子里调 `session.compact`/`command.run`（建议改到 `turn.complete`）；
4. `raise`/`stamp` 参数规整与埋点；
5. 底部：`bLs(op)` 为真表示这是**可被挂钩的事件**，沿插件链跑中间件（`ALe`，事件名=op 名，如 `ui.invalidate`、`state.set`——连 state 读写都能被其他插件 hook）；否则直接 `run`；
6. **权限映射**（bundle.js:21748 尾部 chunk 的 `Vo` 表）：`tool.call/tool.check/agent.spawn/ui.ask/command.run/config.set/telemetry.*/prompt.submit/fill/suggest/compose/session.compact/send/append` 这些敏感 op 落底时过权限系统（`withheldCore`/`withheldFloor` 参数），`tool.call` 结果剥离 `isReadOnly` 并记录 denials。流式 op（`process.spawn`）走 `sHe`（632）生成器管线。
7. `interface.call` 单独走 `ALe` 到目标插件的底部实现。

`prompt.submit`/`command.run` 会被记日志（`D_t`）并受「prompts_screened」协议位影响。

## 5. 崩溃检测与归因（`Cz` 2808、`JQn` 2925）

- Worker 有 ping/pong 心跳；`JQn` 判定三种死法：启动超时（「did not come online within Xms of time its thread had」）、心跳无应答 wedge（「a hook spinning without yielding」）、总等待超限。
- **归因**：用 SharedArrayBuffer 的 stamp/marks 原子计数推断「哪个插件的钩子卡在栈上」：`dHe`（1301）读 stamp 找栈上插件、`VQn` 找「唯一在飞 dispatch 的插件」；证据级别 stack/resumed/dispatch；结论写日志「the heartbeat verdict names X (evidence: …)」。
- 可归因死亡：`EHe`——「X was unloaded: it crashed the hooks worker; what it withheld ($.a, $.b) stays withheld until it reloads or is disabled」，其钩子的 `.catch` 仍被调用（`F_a` effect）。
- 未归因崩溃累计 ≥ `U_a` 次：本会话**整体关闭 worker mods**（`sSt` 2728：「mods that run in the hooks worker are off for this session: it crashed N times」+ `plugin_function_hooks_worker_mods/turned_off`），native（内置）mod 不受影响；随后 respawn worker 并只重载声明集合（`G7n`）。
- Worker respawn 时校验扣留一致性：「hooks worker respawn: X, which withheld $.Y, did not come back; the withholding held until now」（`Xxs`）。

## 6. 其他观察

- `Hde`（1240）是只读清单：name/tier/events/calls（含 nextTo、env.get/set、state.get/set 读写键）/generation——对应 `claude plugin validate` 的「列出 engine.create adds/withholds/replaces」能力的数据面（2.1.323 changelog 提到 validate 列 noun 变更，本版已有 `uses` 清单 `EO` 1356）。
- 折叠/加载全程在 `e.state.queue` 串行队列里跑，并发触发（文件变化、设置变化、/reload-plugins、依赖变化）被合并。
- 遥测字段 `f4(args)` 含 plugin 身份；失败分阶段：`declaration_failed`（扫描/读文件）、`module_load_failed`、`engine_create_failed`、`fold_failed`、`crashed_worker`。

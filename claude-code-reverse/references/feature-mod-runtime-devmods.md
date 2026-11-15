# 会话内即写即用 mod（dev-mods）的启用流程与安全确认

> 主索引：[feature-mod-runtime.md](feature-mod-runtime.md)。
> 证据主体：bundle.js:28774 起的尾部 chunk（原始 minified 但完整，关键字符串逐字引用）；changelog 2.1.318：「Added a record of your answer when Claude Code asks to turn on the mods it writes in a session」。
> 遥测事件：`plugin_dev_mods`（含 `answer`/`answer_not_shown`/`no_session`/各拒绝原因）、`mod_hot_reload`。

## 1. 目录与监视

- dev-mods 目录：`uJ = () => join(Be(), "dev-mods")`（bundle.js:5023），即 `<配置根>/dev-mods`（通常 `~/.claude/dev-mods`）。每个一级子目录是一个 mod（须含 `hooks/hooks.json` 指认的模块文件才被当作活的；`zo` 枚举子目录时校验该文件存在）。
- 会话状态里有 `dev-mods` 键（folder），resume 策略 `last-wins`/「always」（bundle.js:8900-8920）——**会话重启后已同意的状态会被恢复**（`x5r`：stage="consented" 恢复并直接 mkdir+k()）。
- 用 chokidar（`kC.watch`）监视该目录的 add/addDir/change/unlink/unlinkDir；turn 结束时还会 `utimes` 刷新目录时间（`T`/`Z`），推测用于触发外部观察者或防陈旧。
- 加载走 `joinPluginDir(folder)`——即把 dev-mods 作为 `name@inline` 侧载插件目录接入常规插件系统，再由 hooks 引擎热加载/热重载。

## 2. 状态机

`_R` 原子：`undefined → wanted → consented|present → watching → enabled`；分支 `off`（明确不可用/被拒后不再问）、`wanted` 可回到 watching。

- 会话启动时发现已有内容（`Go`）：直接 `joinPluginDir` 并加载（stage: wanted→watching 后 enabled），记 `loaded_at_start:true`——**会话开始时就存在的 mod 不问**。
- 会话运行中新写入 mod（watch 触发）：进入询问流程（§3）。
- 同意但 turn 正在运行：延迟到 turn 结束加载（UI 提示「They'll load when this turn ends.」，`Io`）。
- 环境变量 `${CLAUDE_DEV_MODS_DIR}` 占位符在 preload 时展开为该目录（`GYo`）。

## 3. 询问对话（确认文案逐字）

无 bypass 时弹出（借 AskUserQuestion 通道，`personOnly:!0`）：

- Header：`Mods`
- 问题：`Turn on the mods Claude writes in this session?`
- 选项：`How does this work?`（explain，最多重问 3 次）/ `Turn them on`（allow→enable）/ `Not now`（not_now→decline）
- explain 文案（`Mo`/`ko`，按时机 now/turn-end 切换）：
  > A mod is a small program that changes how Claude looks or behaves here.
  > Claude wrote these mods, and they run with the same access you have.
  > If you turn them on, they'll load now and reload whenever they change.（turn 运行中则为：Once they're on, they load when this turn ends and reload when they change.）
  > That lasts for the rest of this session, even if it restarts.
  > If you choose Not now, nothing new will load until this session next starts.
  > You can see what's loaded, and turn it off, with /plugin.

- 答案被回显进 transcript（虚拟 tool_use 行）并记遥测（`plugin_dev_mods` answer）；decline 后通知栏显示「Not turned on.」。
- decline 按目录记忆（`Vos`）：同一目录本会话不再问；三次无人选择（unpicked）转 `off`（「the question got no pick three times」）；`no_one_to_ask`（无会话可问）同样转 off 并给模型通知「nobody could be asked」。
- **bypassPermissions / auto 模式不问**：`C()` 为真时直接 enable，通知栏提示「In this permission mode the mods Claude writes turn on without asking.」（`Yo`）。

## 4. 拒绝门禁（`Lo` 表 + 人话原因 `jo`）

任一命中即整个 dev-mods 机制不可用（遥测记录原因）：

| refusal | 人话（jo 表逐字） |
|---|---|
| `diskless` | this kind of cloud session has no disk to load mods from |
| `hooks_modules_off` | hooks modules are switched off in this process |
| `all_hooks_disabled` | the organization disables all hooks |
| `sideload_disabled` | the organization forbids side-loaded plugins |
| `local_dirs_blocked` | the organization blocks plugins from local folders |
| `managed_hooks_only` | the organization allows only managed hooks |
| `hooks_disabled_in_settings` | hooks are turned off in your settings (disableAllHooks) |
| `safe_mode` | the session runs in safe mode |
| `bare_mode` | the session runs in bare mode |
| `dont_ask` | the session is in dontAsk mode |
| `untrusted` | the workspace is not trusted |

（对照：`sideload_disabled`/`local_dirs_blocked`/`managed_hooks_only` 分别对应组织的 side-load 禁令、本地目录禁令与 `allowManagedHooksOnly`。）

## 5. 写给模型的结果通知（task-notification，priority "next"）

加载结果通过 `S()` 以 `Fa({mode:"task-notification", skipAttachments:!0, isMeta:Ylo, passive（非 wake 时）, priority:"next"})` 写给模型。文案（`Uo`/`$o`）刻意精确，**防止模型谎报 mod 已生效**：

- reloaded：「The person enabled mod hot-reloading for this session and the mods under <dir> loaded: they load and reload by themselves as their files change; the transcript names any mod that failed.」（权限模式自动开启时前缀换成「The permission mode turned on」）
- held：「…but the mods under <dir> wait for /reload-plugins (the load would rewrite the prompt cache): they are NOT loaded yet.」
- kept-out：「…the hooks modules of the mods under <dir> had NOT loaded when this notice was written. They count as a person's hooks modules, not an organization's. … You get no further notice about them, so do not say they are running, and /reload-plugins does not load them sooner. A mod with no hooks module did load.」
- unbound：「…did not load (this session cannot reload its plugins; only a restart loads them).」
- failed：「…did not load (the load failed; the transcript says why, and /reload-plugins tries again).」
- declined：「The person declined mod hot-reloading: what this run wrote under <dir> is written but NOT loaded (a mod that loaded when the session started keeps running as it loaded). Do not say the change is running. It loads the next time this session starts…; the person can ask again.」
- unanswered：「The person has not answered the mod hot-reloading question yet; it is asked again once a turn ends. What this run wrote under <dir> is written but NOT loaded yet. Do not say it was declined, and do not suggest --plugin-dir or a restart.」
- off：「Mod hot-reloading is off in this session (<reason>): mods under <dir> are not loaded.」

## 6. 与 plugin-authoring 的衔接

- 内置 `plugin-authoring` skill/插件指导 Claude 写 mod（`cc-plugin-mods-guide`、`cc-plugin-plugin-authoring` 命令别名存在于字符串表）；分享前用 MCP 工具 `mcp__plugin-authoring__scan_secrets` 扫密钥（组织合规策略可关闭该工具，文案：「your organization's compliance settings turn it off」）。
- turn-end 附属 prompt（二进制 169293708）：turn 结束、用户未再发言时，让模型用一两行汇报 mod 运行结果；「If the output shows the mod did what they asked, make the plugin-authoring skill's one-line offer for the mod, unless it was already made or they said no」。

## 未知与推测

- dev-mods 子目录成为「mod」的最小文件集：`zo` 只要求子目录里存在 `hooks/hooks.json` 指认的文件（`qo(lr(o,e,nh))`，`nh` 为被 import 的常量）——**推测**为 hooks.json；Memory Hub 记录的最小形态是 `hooks/hooks.json` + `hooks/register.js`（register(on) 导出），与此一致。
- 「it restarts 也保持」的恢复依赖会话状态里的 `dev-mods` 键；跨会话（新会话）不继承（「That lasts for the rest of this session」与 resume 策略并列，观察）——但「even if it restarts」指的是同一会话的 resume。
- `sOn`（watch 轮询间隔）与 `quietMs=2000`（写入静默期后触发询问）为常量观察；`Efs()`（consented 恢复源）未定位。

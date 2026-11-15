# Pane 渲染机制与远端 surface 协议

> 主索引：[feature-mod-runtime.md](feature-mod-runtime.md)。
> 证据主体：claude-app.js 的协议 schema（`QY` 首份 25318-26224；`Rk` 首份 99264-99802）的 `@internal` 文档级描述——这些是引擎作者写给宿主实现者的协议合同，可靠性高。SDK 控制通道处理代码在 `chunks/chunk-L28916.js`。

## 1. 站点（site）与组件

- 引擎可画的 surface：`terminal`（Ink）、`desktop`、`mobile`、`vscode`（`Uk`，claude-app.js:99440；「Where the engine draws: the terminal (Ink) or a remote surface (src/plugins/functionHooks/types/render/render-surface)」）。
- 站点组件枚举（`ui_scroll`/`ui_focus` 的 `component`）：`Pane`（面板体）与 `AbovePrompt`（**band**——输入框上方的横带，对应内嵌资源 `band.tsx`）。
- 远端可渲染组件包括 `UserMessage / AssistantMessage / ToolUse / ToolResult / ToolGroup / CommandOutput / TurnDuration / InfoNotice / Pane / AbovePrompt / Backdrop / Theme / Input / Select / Button / Markdown / Client`（散见于 ui_render/on_screen/draws 描述）。
- `instance_id` 规则：工具行/对话框=其 tool_use_id，消息=消息 id，命令输出行=其 twin 的 uuid，会话 chip=`'session-mode'`，pane=pane id，主题=`theme`，背景=`backdrop`。

## 2. Pane 生命周期（`plugins/functionHooks/panes/`）

pane 记录（claude-app.js:25970 区域）：`{ id, title, plugin, close_on_escape?, hold_toasts?, background_color?, rows?, columns? }`。

- id：`^[A-Za-z0-9_-]{1,64}$`，由 `$.ui.open({id})` 指定；title 默认=id，文本已被引擎剥控制字符。
- roster（`ui_panes` 应答与推送，`D1`）：`{ panes[], shown_id, focused_id, focus_requested_id }`。`shown_id`「never displacing one the person holds」；`focus_requested_id` 只在 composer 空且闲、无对话框时才被接受，否则回 `ui_pane_focus` null。
- `hold_toasts`：pane 展示期间挂起 toast，关闭后补放；`close_on_escape`：Esc 语义。
- 布局信号：`isFullscreen`（viewport 字段）告诉钩子「surface 是否把 pane 停靠在 transcript 旁」——「a pane a plugin opens unasked is a sidebar and not a takeover」。
- 会话内行放置：`$.ui.place` 把行插到某消息之后（`ui_placed` 推送，`after_uuid`；display-only，compaction 终结之前的行，不重传）。
- pane 的滚动/聚焦只能由打开它的插件发起；远端 surface 上用户自己的滚动不回推。

## 3. 渲染管线：`ui.render` 链与树协议

远端 surface 向引擎发 `ui_render` 请求（`f2n`，claude-app.js:99440-99474 区域）：

```
{ surface, client_id?, component, instance_id, props,
  viewport?: { columns, rows, isFullscreen? },   // 字符单元格
  on_screen?: { first, last, of } | null,        // 视口内可见部分 → 钩子读作 e.props.onScreen
  content_rows?, keyed?,                         // pane/band 布局回报（供 $.ui.scroll 定位）
  bench? }                                        // 计时标记透传
→ 沿 ui.render 钩子链（每个挂钩插件 → 核心）求值
→ { tree, props, rewritten, hooked, client_modules?, drawn_by?, bench? }
```

- **tree**：元素树。核心画的子树是**不透明引用节点** `{type:"engine", ref}`（ledger 进程本地，props 不出进程）；插件画的部分带插件标记（`ui.render` 返回根的 `plugin` 字段由引擎打标，「so a surface can tell one mod's drawing from another's」；标记本身可被上层钩子改写，「the mark does not prove who wrote it」）。
- **props**：纯数据，逐组件校验；`ToolUse.output` 入链前截断 64KB。`rewritten` 标记 props 是否被链改过。
- **drawn_by**：引擎给出的归属清单（「The engine's word, which no hook can set」），供 surface 给绘制打来源标记；空表 = Claude Code 自己画的。vscode surface 逐插件单列，其他地方同沙箱邻居合并。
- **hooked=false**：surface 可停止询问该组件直到下一次 `ui_invalidate`（缓存削减）；无任何 hooks module 时引擎直接答 `{tree:{type:"engine",ref:0}, hooked:false}`，不跑链。
- **失效推送** `ui_invalidate`（`R1`）：`$.ui.invalidate("ui.render")`、插件加载/重载、新 client 声明新 draws 字段时广播；`$.state.set` 命中的实例或挂了 `ui.fault` 的 Client 失败时带 `instances` 精确失效。同一插件的 bump 100ms 内折叠一次。
- **主题**：`$.theme.set/clear` 影响每个 surface 的两个实例（`Backdrop`@`backdrop` 与 `Theme`@`theme`）；`Theme` 组件无钩子可画，引擎自己答（desktop/mobile 得 `{plugin, colors}`）。

## 4. Client：插件 TSX 组件

- 声明形态：`Client({ module: "./board.tsx", key })`（hooks.json 的 `surface` 字段已删除，报错信息指路：claude-app.js:1738）。一个插件的 surface module 清单可从 `yCo` 见（bundle.js:873，含 `modulePath` 与 `source`）。
- 树中的 `Client` 节点（claude-app.js:99408）：`{ module, key, props, width/height/flexGrow, client.plugin }`——**纯数据**；「a surface without a surface-module runtime draws nothing for it; no children」。
- surface 端按 `client_modules` 里的**内容 hash** 经 `ui_client_module` 请求取用模块代码并缓存；hash 变化即重挂载。插件没有已加载 surface module 时其 Client 画一条 fault 线。
- 交互回流：`ui_client_press`（`{plugin, instance_id, client, module, element, component, event}`，event ∈ `press` / `input{kind,value}` / `selec(tion)…`）；`ui_client_fault` 到达后归 `ui.fault` 钩子。
- Client 失败分相（`load`/`render`/`run`），钩子读 `e.phase`（claude-app.js:99565 区域）。

## 5. 按键与输入回流

- `ui_press`：元素带 `press.handle`（闭包句柄，存在插件 environment 内）+ 可选 `key`；Markdown 内链接带 `href`（`pressableLinks` 白名单）。handle/key 不匹配答 `{handled:false}`。
- `ui_attach`：远端 client 声明身份与能力——`answers`（`ui_copy`、`ui_prompt_read/fill/paint/suggest`、`ui_read_selection`）与 `draws`（`Backdrop` 仅 desktop/mobile 有效；mobile 未声明 `Input`/`Select` 则收到空 Box 占位）；重复 attach 按字段替换。
- attach/detach 触发 `session.attach`/`session.detach` 钩子事件，`$.session.surfaces()` 随之变化。

## 6. 终端侧（观察+推测）

- 观察：终端是 `terminal` surface（Ink）；`$.ui.toast` 在通知栏、`$.ui.status` 钉在 prompt 旁、`$.ui.log` 在 transcript 追加暗色行（均署名插件名）。
- 观察：SDK 控制通道实现了 `ui_render`/`ui_press`/`ui_client_module`/`ui_client_press`/`ui_panes`/`reload_plugins` 等 subtype（chunks/chunk-L28916.js，含错误文案「plugin X is not loaded or its hooks module names no surface module」）。
- 推测：终端 Ink 树的渲染复用同一套 `ui.render` 链（schema 明示引擎在终端也走此协议），但 REPL 侧装配代码未细读。
- **版本差**：`isPromptCovered`（2.1.323 changelog：pane 用 props 渲染且有 isPromptCovered）在 2.1.321 二进制中 0 命中——本版 pane 的 prompt 遮挡语义尚未落地为该字段。

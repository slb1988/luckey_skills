# `$` nouns 体系：全表与调用语义

> 主索引：[feature-mod-runtime.md](feature-mod-runtime.md)。
> 主要证据：`chunks/chunk-L12139.js`（noun 注册表 `bRs` 从第 77 行起）、claude-app.js 协议 schema 的 `@internal` 描述、bundle.js:21748 区域的权限映射 `Vo`。
> 形态：mod 代码里 `$` 是引擎注入的对象，`$.<noun>.<method>(args)` 为一次 op。每个 op 条目形如 `{ check(n, ctx), run(n, ctx), raise?, stamp?, stream? }`；`check` 返回错误字符串=拒绝，返回 undefined=通过（错误文案兼作 API 文档，下表大量引用原文）。

## 总表（v2.1.321 观察到的核心 noun）

### model — 模型调用

| op | 签名（check 原文） | 备注 |
|---|---|---|
| `model.complete` | — | 走 `plugin_model_complete` 计费通道 |
| `model.classify` | `takes { text, labels }` | `plugin_model_classify` 计费通道 |
| `model.fork` | `takes { prompt, effort? } (a non-empty prompt)`；effort 必须属于 effort 枚举（`Ei`） | 侧支子会话；2.1.318 changelog：加 effort 选项「so a quick side job can run at …」 |

（changelog 2.1.325：`$.model.complete`/`$.model.classify` 计入成本——与本表的计费通道名互证。）

### tool / agent / command / config — 能力注册与调用

| op | 要点 |
|---|---|
| `tool.call` | 调任意工具；**限制**：不能起后台/订阅类调用（拒绝理由原文：「it starts background work, a schedule or a goal」「a page publish, a watch or a resume of replies arms a watch on the page」）；Agent/AskUserQuestion/Workflow 被专用名词接管（pkt 表：「runs the Agent tool: that is $.agent.spawn」「runs the AskUserQuestion tool: that is $.ui.ask」「$.agent.spawn is the door」） |
| `tool.check` | `takes { tool, input }` —— 预检 |
| `tool.list` | 列工具 |
| `tool.register` | mod 注册新工具（`inputSchema`、可选 `isDeferred`） |
| `agent.spawn` / `agent.list` / `agent.register` | 起子代理（预算 `budgets.spawns`）/ 列 / 注册新 agent 类型（需 `prompt` 非空） |
| `command.run` | `takes { command, args? } (the name without the slash)`；**turnHeld 禁止**：在 `command.run` 等持 turn 钩子里调用被拒——「answer { text } instead, or run it from a later event (turn.complete)」 |
| `command.register` | 注册斜杠命令（`argumentHint`、`immediate`；文本被清洗限长） |
| `command.list` | 列命令 |
| `config.describe` / `config.list` / `config.set` | 配置面（`config.set` 过权限映射） |

### prompt — 输入框/提示词管线

| op | 要点 |
|---|---|
| `prompt.submit` | `takes { text }`；**以 / 开头会被拒**：「a text beginning with / would run a command as the user; run one with $.command.run({ command })」；可选 `asUser` |
| `prompt.fill` | 填输入框；返回 `{ isFilled, refusal?, text, cursor }`；支持 `mode/decorations/cursor`；远端 surface 由 `ui_prompt_fill` 应答 |
| `prompt.paint` | 装饰输入框（不改文本？返回 `{ isPainted, text, cursor }`——推测 paint=装饰性展示） |
| `prompt.suggest` | `takes a non-empty suggestion` |
| `prompt.read` / `prompt.media` / `prompt.compose` | 读输入框 / 媒体 / 组合（细节未展开） |
| `prompt.section` / `prompt.context` / `prompt.attachment` | 注入 system prompt 段落 / 上下文 / 附件——可被 `$.ui.invalidate` 失效 |

### ui — 界面

| op | 要点 |
|---|---|
| `ui.open` / `ui.close` / `ui.panes` | 开/关/列 pane；id 规则 `^[A-Za-z0-9_-]{1,64}$`；`open({focus:true})` 是「请求」，surface 仅在 composer 空且闲、无对话框时才接受（claude-app.js:25981） |
| `ui.render` / `ui.resolve` | 渲染钩子事件与元素表解析（见 UI 子文档） |
| `ui.scroll` / `ui.focus` | 移动站点视口/焦点环；pane 的操作权归打开它的插件（「a $.ui.scroll or $.ui.focus of the pane is that plugin's alone」） |
| `ui.copy` | 剪贴板（远端由 `ui_copy` 应答；无应答方时 `no-clipboard`） |
| `ui.selection` | 读远端页面选区 |
| `ui.place` | 在会话消息流里放行（`ui_placed` 推送；display-only，compaction 会终结其前行） |
| `ui.toast` / `ui.status` / `ui.log` / `ui.notify` / `ui.cancelNotify` / `ui.notice` | toast 有 `timeoutMs` 上限（`ikt`）；notify 支持 `key` 替换、`delay_ms`/`at`（≤7 天）、`until_back`；notice 挂在 tool_use 行上 |
| `ui.ask` | AskUserQuestion |
| `ui.blit` / `ui.view` | 直绘/读视图（细节未展开） |
| `ui.invalidate` | 参数枚举校验：「takes "ui.render", "prompt.section", "prompt.context", "prompt.attachment", "tool.describe", "command.describe" or "config.describe"」——即**可失效缓存面**的完整清单 |

### session / turn — 会话与轮次

| op | 要点 |
|---|---|
| `session.id` / `session.cwd` / `session.root` / `session.model` / `session.turns` / `session.version` | 只读信息 |
| `session.messages` | 读消息（`p_a` 校验） |
| `session.surface` / `session.surfaces` | 当前/全部 surface（attach 后列出） |
| `session.identity` / `session.authorize` | 身份/授权（细节未展开） |
| `session.usage` | 用量查询 |
| `session.send` / `session.append` | 向会话发消息/追加（均过权限映射 `Vo`） |
| `session.compact` | 触发压缩；`takes { instructions }`；turnHeld 禁止 |
| `turn.abort` | `takes { turnId } (the id turn.start carried)` |

### fs / store / state / env / settings

| op | 要点 |
|---|---|
| `fs.read` / `fs.write` / `fs.list` / `fs.exists` / `fs.stat` / `fs.ancestors` | 文件访问（过宿主校验与权限） |
| `store.get/set/delete/keys` | 每插件持久 KV（`GX(e, r.plugin)` 限域） |
| `state.get` / `state.set` | 会话内响应式状态：写入触发读取它的 UI 实例重渲染（`ui_invalidate` 的 `instances` 字段机制，claude-app.js:25912）；**静态扫描约束**：引用 `{plugin, key}` 必须源码可见 |
| `env.get` / `env.set` | 进程环境（读取受扫描声明约束） |
| `settings.read` | 读设置（`Lys` 校验 source） |

### 其他

| op | 要点 |
|---|---|
| `engine.create` / `plugin.register` | 结构性事件（见 engine 子文档） |
| `interface.call` | 跨插件调用：`takes { owner, name, method, args }`；args 恰一个 |
| `mcp.call` / `mcp.connect` | 调 MCP 服务器 |
| `http.fetch` | `takes a URL`（带 pluginName/pluginStorageId 归因） |
| `process.run` / `process.spawn` | 跑子进程（spawn 为流式 op） |
| `clock.now` / `clock.sleep` / `clock.after` / `clock.every` | 时钟与定时 |
| `audio.play` / `audio.speak` | 音频 |
| `telemetry.log` / `telemetry.mark` | 遥测（过 `Vo` 权限映射） |
| `flag.value` / `decision.ask` | feature flag / 决策点（细节未展开） |

## 类型契约（插件间共享 noun 的类型面）

插件可在 manifest 声明 `types: "./xxx.d.ts"`（claude-app.js:6730）：自包含 `.d.ts`，导出其在 `engine.create` 添加的 noun 的类型，并用 `declare module 'claude-code' { interface EngineInterface { … } }` 声明。依赖它的 mod 在每次从**本人拥有的目录**加载时得到铺放到 `.claude-plugin/types/<plugin>/index.d.ts` 的契约副本；`claude plugin validate` 校验该文件。

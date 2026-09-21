# 架构与源码地图

## 四个对象，分别验收

| 对象 | 负责什么 | 不能证明什么 |
| --- | --- | --- |
| UE AngelScript runtime/compiler | 语法执行、async 状态/adapter 合法性、原生 API | 引擎能跑不代表编辑器解析支持 |
| 扩展 client + language server | VSCode 集成、容错解析、类型/作用域、补全/导航/诊断/语义 token | AST 容错接受不代表运行时语法合法 |
| TextMate grammar | 不依赖 LSP 的词法着色 | 颜色正确不代表补全、跳转或类型正确 |
| VSIX | 给接收者安装的清单和完整运行资产 | 安装成功不代表 UI/UE 执行联调通过 |

## 通路

- **语言服务**：VSCode ↔ LSP 是 IPC；LSP ↔ Unreal 是自定义 TCP，获取原生类型、编译信息等。
- **AS 业务调试**：VSCode ↔ 扩展内 DAP adapter，再由 adapter ↔ Unreal。LSP 和 DAP 各建连接；不需要先启动 AS 调试才有补全。
- **扩展源码调试**：VSCode JavaScript debugger ↔ Extension Host/LSP Node inspector。这条通路调的是 TypeScript 编译后的 JS，不是 AS VM。

## 文件入口

| 路径（扩展仓库内） | 职责 |
| --- | --- |
| `package.json` | VSCode 清单、版本、引擎要求、命令及打包入口 |
| `extension/src/extension.ts` | 激活、LanguageClient、server 启动/调试参数 |
| `extension/` | 命令/API 面板、ASDebugSession/DAP adapter |
| `extension/syntaxes/*.tmLanguage.json` | TextMate 词法着色 |
| `language-server/pegjs/angelscript.pegjs` | PEG 语法源 |
| `language-server/pegjs/angelscript.js` | Peggy 生成并提交的 parser，非手工编辑源 |
| `language-server/grammar/node_types.js` | AST 节点编号；新增类型在末尾追加 |
| `language-server/src/as_parser.ts` | 语句、作用域、类型和符号解析、缓存 |
| `language-server/src/database.ts` | 类型/方法数据库及签名格式化 |
| `language-server/src/parsed_completion.ts` | 补全上下文和候选 |
| `language-server/src/inlay_hints.ts` | 参数等 inlay 遍历 |
| `language-server/tests/` | 真实模块回归、缩减 fixture |
| `.vscode/launch.json`、`.vscode/tasks.json` | 开发者本地启动/附加与构建，不属于分发包 |
| `extension/esbuild.js`、`.vscodeignore` | bundle/外部 helper 和 VSIX 文件边界 |

构建产物在 `extension/dist/`、`language-server/dist/`。遇到旧文档的 `out/`、根级 `npm test` 或 watch 脚本，先核对现有清单，不能照搬。

## 最窄深入资料

项目内 `docs/language-server/grammar.md`、`database.md` 解释 parser/database；`docs/guides/custom-syntax.md`、`keywords.md`、`completion.md` 解释跨消费者修改路线。

MainDev 的引擎依据在 `Engine/Plugins/Angelscript/ThirdParty/source/as_parser.cpp`；异步背景见该插件 `references/typed-async-pilot.md` 与 `async-source-debugging.md`。仅在需要核验 runtime 契约时读对应段，不全仓扫描。

`examples/cpp-debug-server/` 是模拟协议/脚本执行的教学服务，并非 UE VM；其 language-smoke 只证明模块级行为。

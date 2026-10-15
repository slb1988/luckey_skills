# 最小定位与修复路线

本轮仅给方案，未操作目标工程或启动进程；以下步骤、命令均待授权执行，历史通过不算本轮证据。

## 1. 先查声明，不先补候选

运行时通过不证明 LSP 支持。大纲缺方法、函数体补全失效，优先怀疑函数声明未解析。实施前核对扩展仓库 `AGENTS.md → AGETNS.md` 与已有变更；将普通实例方法 `async FTask RunAsync(Context T)`、真实调用和半成品 `await UISteps::` 缩成 fixture，不额外加 UFUNCTION。依次观察 FunctionDecl、函数作用域、DBMethod，再查大纲和补全消费者。契约有疑问才只读 MainDev 的 `Engine/Plugins/Angelscript/ThirdParty/source/as_parser.cpp` 中 `IsAsyncFunctionModifier` / `IsAwaitExpression`。

## 2. 最窄实现面

以下路径相对扩展仓库的 `language-server/`：

- `pegjs/angelscript.pegjs`：按函数声明形状识别 contextual async；仅异步函数内将 await 解析为一元优先级的 AwaitExpression，await 语句分支先于泛化变量声明。不能全局保留关键字：普通 `int await`、`await()`、`int async` 及名为 async 的类型仍须兼容；半成品允许缺操作数。
- `grammar/node_types.js`：末尾追加节点，不重排编号。`src/as_parser.ts` 将 `FunctionDecl.isAsync` 传入方法元数据；`ASStatement.inAsyncFunction` 传给 PEG、嵌套块及补全临时解析入口。缓存必须包含上下文：只增删 async、正文不变也重解析，不能仅按文本复用旧 AST。
- `src/database.ts`：保留 `DBMethod.isAsync`、签名及模板实例元数据。`src/as_parser.ts`、`src/inlay_hints.ts` 递归访问 await 操作数并防缺省，恢复符号、类型和参数提示。当前 await 是无值结果，用 `null`，不能沿用操作数类型或把 Action 工厂伪装成 Task。
- `src/parsed_completion.ts`：修复 await 后表达式、命名空间、成员及临时语句上下文；`ASKeywords` 是前缀容错表，不是候选表。若涉及着色，再独立处理 `extension/syntaxes/angelscript.tmLanguage.json`（相对仓库根），避免同名标识符误染；不能用加颜色替代语义修复。

## 3. 验收证据与边界

在扩展仓库根，按现有清单核对后拟执行：

```sh
npm exec --yes --package=peggy@5.1.0 -- npm run pegjs:compile
node language-server/tests/async-await.test.mjs
npm run compile
node examples/cpp-debug-server/tests/language-smoke.mjs
git diff --check
```

只改 PEG 源，用固定生成器及仓库四个 start rules 更新 `angelscript.js`，不手改生成物。回归应走真实 parser/database/completion 等模块，仅原生 API 用 stub；断言方法与大纲范围、命名空间候选、`await T.`、裸 await、缺实参/分号、普通同名标识符，以及只切换 async 的双向缓存失效；同时核对 hover/定义、语义 token、签名/inlay。着色改动另验真实 TextMate/Oniguruma scope。

保留命令输出与断言；esbuild 成功不等于完整 tsc 检查。后续若验 GUI，须证明宿主加载本地扩展、正确 LSP bundle/workspace，再记录大纲和补全效果，不能推称日常安装版已更新。本题不扩到 UE/runtime 改造、adapter 合法性诊断、PLAutomation 入口诊断/模板/quick fix、DAP 联调或 VSIX 安装发布。

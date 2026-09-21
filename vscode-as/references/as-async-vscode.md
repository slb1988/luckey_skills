# as-async-vscode：async/await 编辑体验修复案例

本文件是已完成工作的一次证据归档，供同类语法扩展复盘；不是对当前工作区或未来引擎版本的自动保证。日常方法见 [开发指南](../docs/development.md)，历史包见 [1.9.5 基线](vsix-1.9.5.md)。

## 原始问题与范围

MainDev 的 async/await 运行功能由用户确认已通过，但 VSCode 的 `.as` 提示和显示有缺口。截图对应 `Main/Script/Tests/1000_RuntimeTests/TestCase_10_OptionUI.as` 的 `UOptionUITestCase`：

```angelscript
async FTask RunAsync(UPLAutomationAsyncContext T)
{
    await TestSteps::WaitUntil(...);
    await UISteps::WaitForWidgetActive(...);
    T.Defer(n"CleanupUIFixture");
}
```

这里 `...` 只表示省略原始实参，并非可执行 fixture。真实方法是普通实例方法，没有 UFUNCTION/BlueprintOverride；应使用项目中的真实文件或缩减测试 fixture。

修复范围为扩展的解析、补全、语义消费者和着色，不改 MainDev runtime，不新增 PLAutomation 入口必填诊断、quick fix 或模板。

## 根因与实现映射

旧 PEG 不认识 `async FTask RunAsync(...)` 和 `await Namespace::Factory(...)`，方法及函数体的语义分析丢失。只在 TextMate 中添加单词不能恢复作用域、符号、补全和大纲。

| 文件 | 对应职责 |
| --- | --- |
| `language-server/pegjs/angelscript.pegjs` | contextual async 声明；一元优先级 AwaitExpression；await 语句先于泛化变量声明 |
| 同目录 `angelscript.js` | Peggy 5.1.0 生成物，与源同步提交 |
| `language-server/grammar/node_types.js` | 末尾追加 AwaitExpression，不重排编号 |
| `language-server/src/as_parser.ts` | async 作用域/元数据、await 操作数遍历、无值类型、缓存上下文 |
| `language-server/src/database.ts` | `DBMethod.isAsync`；签名格式化/模板实例保留 async |
| `language-server/src/parsed_completion.ts` | 关键字上下文、await 后表达式/成员/命名空间补全、临时解析上下文 |
| `language-server/src/inlay_hints.ts` | 递归 await 操作数，保留参数 inlay |
| `extension/syntaxes/angelscript.tmLanguage.json` | contextual 着色，避免普通同名标识符误染色 |

## 可复用的关键约束

1. **不是全局保留字**：普通函数中的 `int async`、`int await`、`await()` 仍有效。async 前缀依函数声明形状识别，不能吞掉名为 async 的普通类型。
2. **上下文要进入所有解析入口**：`FunctionDecl.isAsync` 进入 `DBMethod`；`ASStatement.inAsyncFunction` 传给 PEG，向嵌套块及补全临时语句传播。
3. **缓存键不只有文本**：仅加/删函数 async 修饰符时，未改文本的 `await(Child())` 也必须按新上下文重解析。
4. **新节点要被访问**：`AwaitExpression.children[0]` 是操作数，半成品允许缺省；符号和 inlay 都要递归访问，不能只让 PEG 接受。
5. **不要伪造返回类型**：当前 runtime FTask/adapter await 是 void-result；编辑器用无值类型 `null` 表示，不返回操作数类型。工厂仍返回真实 `UPLAutomationAction`，不伪装为 Task，不按命名空间猜 adapter 合法性。
6. **候选表不是容错表**：`ASKeywords` 用于关键字前缀容错；补全候选由 `parsed_completion` 生成。
7. **位置与字段有各自约定**：AST start/end 相对语句，`ASStatement.start_offset` 相对文件；声明还使用 name/returntype/parameters 等字段，不能仅遍历 children。

引擎契约参照 `Engine/Plugins/Angelscript/ThirdParty/source/as_parser.cpp` 的 `IsAsyncFunctionModifier` / `IsAwaitExpression`。容错 AST 接受复杂表达式，不表示 runtime 支持全部组合；合法性和 adapter 判断仍归引擎。

## 回归依据

固化在扩展仓库：

- `language-server/tests/fixtures/async-await.as`：由真实 OptionUI 语法缩减，不执行业务。
- `language-server/tests/async-await.test.ts` / `.mjs`：esbuild 内存加载测试；原生 API 是最小 stub，PEG/parser/database/completion/symbols/semantic_highlighting/inlay_hints 走真实模块。
- 检查 parse/作用域、大纲范围、hover/定义、语义 token、签名/inlay；覆盖半成品 `await UISteps::`、`await T.`、裸 await、关键字前缀、缺实参/分号。
- 交付时通过 21 项 grammar cases、contextual 同名标识符、缓存失效、CRLF 及补全/签名回归；另通过 9 项真实 TextMate/Oniguruma 用例、普通 language-smoke、Peggy 重生成、compile、diff --check。
- 准确复跑命令在 [开发指南](../docs/development.md#改语法和最小回归)，不要把本段历史通过视为当前分支已测试。

## 联调与未验证边界

当次开发宿主曾验证：本地扩展激活、仓库 `dist/server.js` 被运行、workspace 为 MainDev Script、两个 Node inspector 可访问、该 LSP 与 UE 默认 27099 TCP 建连。没有把 PID、当前存活状态或临时日志路径固定到本文。

没有验收：GUI 目视补全/着色、真实 AS 断点/单步、所有 runtime async 组合、接收者机器/其他 OS 联调；没有做全 UE 编译。模块测试、TCP 建连和安装成功不能替代这些结论。

## 源资料与范围陷阱

- 扩展项目：`docs/testing.md`、`docs/language-server/grammar.md`、`docs/development.md`。
- MainDev：`Engine/Plugins/Angelscript/references/typed-async-pilot.md`、`async-source-debugging.md`。
- MainDev：`openspec/changes/productionize-angelscript-async-plautomation/` 是更大规划背景；其中 authoring prompt 的入口诊断/模板不是本次已交付能力。
- 归档来源：本会话 worker 的已验证交接事实及 `.local/orchestration/as-async-vscode/` 三轮任务（修复、开发宿主、打包）。重要事实已转为本文和 docs；原始 prompt、会话 ID、费用不进入共享知识正文。

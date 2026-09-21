# vscode-as 接手资料

本目录保存跨任务可复用的入口和操作方法；`../references/` 保存具体修复/发布证据。完整项目设计仍以扩展仓库自己的 `docs/` 为准，不在两处复制整套文档。

## 阅读顺序

1. [架构与源码地图](architecture.md)：先区分引擎、LSP、TextMate 和 DAP。
2. [开发与验证](development.md)：安装依赖、改语法、运行回归、启动开发宿主和打源码断点。
3. [VSIX 打包与安装](packaging.md)：生成可分发包及隔离安装验证。
4. [async/await 修复案例](../references/as-async-vscode.md)：关键设计、缓存/遍历陷阱、真实样例和未交付范围。
5. [VSIX 1.9.5 基线](../references/vsix-1.9.5.md)：历史包、hash、证据和平台限制。

## 工作区约定

| 逻辑工作区 | 用途 | 本机会话中的示例路径 |
| --- | --- | --- |
| `ws:vscode-unreal-angelscript` | 扩展源码、测试、调试配置和 VSIX | `D:/Github/vscode-unreal-angelscript` |
| `ws:maindev` | UE AngelScript 实际语法/协议及 Script 用例，P4 管理 | `D:/MainDev` |

示例路径不是跨机器约定；先解析 workspace，再在目标仓库操作。下文命令若未注明，cwd 都是扩展仓库根，不能从 skill 目录直接执行。

## 源资料与版本控制

- 项目内优先入口：`AGENTS.md` → `AGETNS.md`、`docs/README.md`、`docs/architecture.md`、`docs/development.md`、`docs/testing.md`。
- `.local/orchestration/as-async-vscode/` 是原会话的本机派发/交接草稿；重要事实已提炼到本 skill，无需该临时目录即可接手。原始派发指令、进程快照和日志不作为长期文档复制。
- 本 skill 随 skills 仓库版本控制；项目源码/测试仍在扩展仓库维护，MainDev 的 P4 变更独立管理。
- 修改事实时同步更新最窄文档；新的修复/包基线另作有证据的 reference，不把旧的验收范围改写成从未发生过的结果。

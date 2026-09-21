# 开发、验证和本地源码调试

命令 cwd：扩展仓库根。先检查项目规则和已有变更，已有依赖可用就不重复安装。

## 依赖与构建

两个子项目独立，不是 npm workspaces：

```sh
npm ci --prefix extension
npm ci --prefix language-server
npm run compile
```

`compile` 使用 esbuild；产物成功不等价于完整 TypeScript 类型检查。需要类型检查时按项目实际配置另验，不能谎称已跑 `tsc`。

## 改语法和最小回归

只改 `language-server/pegjs/angelscript.pegjs` 源，再用固定生成器和仓库声明的四个 start rules 生成：

```sh
npm exec --yes --package=peggy@5.1.0 -- npm run pegjs:compile
node language-server/tests/async-await.test.mjs
npm run compile
node examples/cpp-debug-server/tests/language-smoke.mjs
git diff --check
```

TextMate 改动另跑真实 tokenizer；临时工具包不加入扩展运行依赖，首次执行可能联网：

```sh
npm exec --yes --package=vscode-textmate@9.3.2 --package=vscode-oniguruma@2.0.1 -- node language-server/tests/async-await.test.mjs --textmate
```

- async/await runner 用 esbuild 内存加载 `.test.ts`，原生 API 用最小 stub，其余 parser/database/completion 等走真实模块。
- 改动只涉及打包或调试配置时，不需要重新跑所有语法回归。
- 没有根级 `npm test`；旧 `pegjs:test` 依赖缺失的 `test.as` 且可能改写生成物，不作为默认验收。
- 完整样例/断言重点见 [async/await 案例](../references/as-async-vscode.md)。新语法优先新增同类缩减 fixture，不依赖整个 UE 会话。

## 开发宿主与断点

区分两个窗口：**源码窗口**打开扩展仓库；**Extension Development Host** 打开游戏的 Script 根目录。日常安装版不会自动加载本地源码修改。

### 当前配置名称

| `.vscode/launch.json` 配置 | 作用 |
| --- | --- |
| `Launch Client` | 通用开发宿主，preLaunchTask 为 `npm: compile` |
| `Launch Client (MainDev)` | 隔离宿主，打开 MainDev Script 和 OptionUI 第 34 行 |
| `Attach to Client (CLI Host)` | 附加用 9333 启动的 CLI 开发宿主 |
| `Attach to Server` | 附加 LSP 6009，`restart=true` |
| `Client + Server` | 通用宿主启动 + LSP 附加 |
| `Client + Server (MainDev)` | MainDev 宿主启动 + LSP 附加 |
| `Attach to Running Dev Host` | 附加已有 CLI 宿主及 LSP，不再打开新宿主 |

MainDev 预设中的本机路径必须在新机器核对；不要把它当作 VSIX 对接收者的依赖。

### 可重复操作

1. 没有宿主时：源码窗口 `Ctrl+Shift+D`，选 `Client + Server (MainDev)` 后 `F5`；已有匹配 CLI 宿主则选 `Attach to Running Dev Host`。
2. 语言侧在 `language-server/src/parsed_completion.ts` 的 `Complete` 或 `server.ts` completion handler 打断点；到开发宿主按 `Ctrl+Space` 触发。扩展侧入口是 `extension/src/extension.ts`，已执行的 activate 需重载才重跑。
3. 修改后在源码窗口 `Ctrl+Shift+B`（默认 `npm: compile`），仅在开发宿主执行 `Developer: Reload Window`，必要时重新 attach。不要重载用户日常窗口。
4. 查真实运行证据：本地扩展激活路径、LSP `dist/server.js` 路径、workspace roots。需要 UE 信息时再核验该 LSP 与正确引擎端口的连接。

源映射使用 `extension/dist/*.js(.map)` 与 `language-server/dist/server.js(.map)`，不要配置到 `out/`。

分别 watch 可用 `npm run watch:extension`、`npm run watch:language-server`。根级 watch 依赖未声明的 `npm-run-all`，旧 tsc-watch matcher 也不匹配 esbuild；不为启动环境额外引入未经验证的 watch 链。

## 端口不是一回事

| 地址/端口 | 用途 |
| --- | --- |
| 9333 | CLI 宿主 Node inspector；不是所有 F5 启动都固定用它 |
| 6009 | LSP Node inspector，由 extension 的 debug server options 设置 |
| 27099 | 默认 Unreal 自定义 TCP；不是 Node inspector，LSP/DAP 各自连接 |
| DAP 本地随机端口 | VSCode 到扩展内 ASDebugSession，不能手填成 27099 |

端口已占用时先确认归属；若是已有开发宿主，优先附加，不杀进程或重复起第二套。

## 隔离配置与证据边界

- Windows 预设使用 `%LOCALAPPDATA%/UnrealAngelscriptDev/user-data` 与 `extensions`，不改日常 VSCode profile。
- 原 MainDev 预设曾对可信本地目录使用 `--disable-workspace-trust`；这不是搭建环境的通用必要条件，不复制到全局设置或用于不可信项目，优先保留正常信任确认。
- 日志在隔离 `user-data/logs/<时间>/window*/exthost/`，重点为 `exthost.log` 和 `output_logging_*/Angelscript Language Server`。
- Node inspector 可访问、LSP→UE TCP 建连、模块回归均不证明 GUI 效果或 AS 单步通过。AS 业务断点另用项目的 `type: angelscript` DAP 配置，本页 F5 流程调的是扩展源码。
- Git Bash 调 Windows 程序时注意盘符/反斜杠和 MSYS 参数转换；涉及多个本机路径时优先 PowerShell 或 Python 参数数组。以实际进程参数/日志确认路径，不把拼接成功当成启动正确。

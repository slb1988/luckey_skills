以下仅为操作方案，未实际启动、关闭、编译或改配置。**不能把所有端口改成 27099。**

### 1. 在源码窗口附加已有宿主
保留日常 VSCode 不动；源码窗口打开扩展仓库，CLI 开发宿主打开游戏的 Script 根目录。先核对监听进程归属，确认 9333、6009 确属这套开发环境，不能仅凭端口在监听判断。

在源码窗口按 `Ctrl+Shift+D`，选择 `.vscode/launch.json` 的 **`Attach to Running Dev Host`**，按 `F5`。该复合配置包含 `Attach to Client (CLI Host)`（9333）和 `Attach to Server`（6009，`restart=true`）。不要选 `Launch Client` 或 `Client + Server`，包括 MainDev 变体：它们会另开宿主，可能争用 LSP inspector。

### 2. 断点与触发要在不同窗口
在源码窗口打开 `language-server/src/parsed_completion.ts`，于 `Complete` 的可执行行按 `F9`；也可在 `server.ts` 的 completion handler 下断点。切到**开发宿主**的 `.as` 文件，在目标代码提示位置按 `Ctrl+Space`，回源码窗口查看命中、调用栈和变量；`F10` 单步、`F11` 进入、`F5` 继续。

扩展客户端入口是 `extension/src/extension.ts`；若断在已执行过的 `activate`，单纯附加不会倒放，需要重载宿主重新触发。

### 3. 修改后继续调试
将来修改并保存源码后，在**源码窗口**按 `Ctrl+Shift+B`，执行默认 `npm: compile`，确认成功；然后仅在**开发宿主**按 `Ctrl+Shift+P`，执行 `Developer: Reload Window`。必要时回源码窗口重新附加，再触发补全。不要重载日常窗口；只保存 TS 不会替换进程里已加载的 JS，也无须安装 VSIX。

### 4. 怎样确认跑的是自己的源码
核对启动参数 `--extensionDevelopmentPath` 与扩展实际激活日志，确保指向当前本地扩展目录，而非日常已安装版本；核对 LSP 进程/日志中的入口确为本仓库的 `language-server/dist/server.js`，workspace roots 是目标 Script 目录。

源码映射应对应 `extension/dist/*.js`、`language-server/dist/server.js` 及相邻 `.map`，不是 `out/`。断点绑定、触发后调用栈落在当前 TS，并体现重新编译后的改动，才是运行证据；空心断点先查附加目标、构建产物和映射，不要乱换端口。

### 5. 这不是 AS 业务断点
9333 是 CLI 扩展宿主的 Node inspector；6009 是 LSP 的 Node inspector，由扩展调试启动选项设置。27099 默认是 Unreal 自定义 TCP，供 LSP/DAP 分别连接，不是 Node inspector；VSCode 到扩展内 `ASDebugSession` 的 DAP 本地端口是随机的，也不能填成 27099。

上述流程调的是扩展/LSP 的 TS/JS。要调 `.as` 业务逻辑，应在开发宿主使用项目的 `type: angelscript` 调试配置，连接正确 UE 会话并实际触发业务断点；inspector 可连或 UE TCP 建连，都不能证明 AS 断点、单步已经通过。

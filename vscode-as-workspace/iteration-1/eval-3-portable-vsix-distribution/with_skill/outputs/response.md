以下仅是待执行方案，本轮不安装、构建、试装或发布。**Windows 包不能未经验证直接承诺支持 macOS。**

### 1. 打包者准备与打包
在扩展仓库根核对 `package.json` 的 publisher/name、version、`engines.vscode`、入口及 `vscode:prepublish`，并检查构建脚本、锁文件、`.vscodeignore`。按项目惯例明确更新 patch 版本；构建依赖由打包者按锁文件准备，同事无需源码或 Node/npm。

```sh
npm exec --yes --package=@vscode/vsce@3.7.1 -- vsce package --no-dependencies
```

不要传位置版本参数，避免隐式改版本/提交。预发布钩子会调用 `npm run compile`；已有 bundle 不代表跳过构建。`--no-dependencies` 仅因运行依赖已 bundle 才成立，esbuild 成功不等于完整 tsc 检查。

### 2. 检查包，不只看退出码
将 VSIX 作为 ZIP 检查，以下路径均相对包内 `extension/`：
- main：`extension/dist/extension.js`；debugger program：`extension/dist/debugAdapter.js`，不能残留 `out/`。
- LSP：`language-server/dist/server.js`，客户端应从安装目录定位；parser、节点表及运行依赖应已入 bundle。
- `extension/dist/terminateProcess.sh` 与 `languageclient-LICENSE.txt`：核对 `extension/esbuild.js` 的复制步骤及 helper 的 `__dirname` 读取路径；根 MIT LICENSE 也须保留。
- 清单引用的 resources、语言配置及两个 TextMate JSON 均存在；排除本机 `.vscode`、源码/maps、测试、node_modules、profile 和缓存。

### 3. 隔离验收与平台门槛
PowerShell 中令 `$P` 为实际 VSIX 绝对路径，`$T` 为专用新临时目录：

```powershell
code --user-data-dir "$T/user" --extensions-dir "$T/ext" --install-extension "$P"
code --user-data-dir "$T/user" --extensions-dir "$T/ext" --list-extensions --show-versions
Get-FileHash "$P" -Algorithm SHA256
```

核对安装 ID/版本及 bundle、helper、grammar 与包内字节一致；用相同隔离参数启动 VSCode，打开 Script 根验证修复点。

Windows 包中 helper 的 ZIP mode `100666` 无执行位。由打包者在 macOS 重包，确保复制步骤保留或设置执行位，核对 ZIP 与安装后权限，并验证 LSP 启动、退出、重启及无残留进程；通过后才承诺该 macOS 环境。不因清单无 platform 限制就称跨平台通用。

### 4. 交付与承诺
附包绝对路径、ID、实际版本、字节大小、SHA256、源码修订及验收 OS/架构/VSCode 版本。历史基线是 `Hazelight.unreal-angelscript`、1.9.5、languageclient 8.1.0、VSCode `^1.67.0`；须按当前清单/锁文件复核，不能沿用历史 hash 或把最低声明当实测。

同事通过扩展面板“…”→“从 VSIX 安装”→重载即可。同 ID 会替换旧版，Marketplace 自动更新可能覆盖内部版；由同事决定是否关闭该扩展自动更新，不改全局策略。

可承诺接收者无需开发环境；平台支持以实际验收为限。安装成功不证明 GUI、真实 AS 断点或 UE 联调通过；完整原生 API/调试仍需兼容 UE debug server（默认 27099），VSIX 不含引擎 async 补丁。Linux 未验收，不承诺支持；不上传 Marketplace。

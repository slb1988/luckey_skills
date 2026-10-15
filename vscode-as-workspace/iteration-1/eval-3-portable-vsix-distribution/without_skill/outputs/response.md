# VSIX 分发演练

以下仅为方案，未执行安装、构建或测试；项目实际脚本名、产物路径及兼容版本未知，不作猜测。

## 1. 最短打包流程
发布者准备 Node/npm，按锁文件执行 `npm ci`，运行项目已有的 esbuild 打包脚本。固定并记录 vsce 版本。确认客户端、语言服务器入口都已生成，除 VS Code API、Node 内置模块外，运行时依赖均已打入或随包携带后，才使用：

```sh
npx @vscode/vsce ls --no-dependencies
npx @vscode/vsce package --no-dependencies --out extension.vsix
```

第一条检查拟打包文件；第二条生成包，不发布市场。留意 `vscode:prepublish` 可能再次构建。esbuild 不会自动收集所有非 JS 资源，不能仅凭“已经 bundle”就排除全部依赖。

## 2. 先处理 macOS 风险
`terminateProcess.sh` 的 ZIP mode `100666` 表示普通文件且无执行位，不能据此宣称跨平台可用。核对实际调用及 bundle 后路径：若直接执行脚本，macOS 可能报权限错误、遗留服务器进程；若显式经 `sh` 调用，则不要求脚本执行位。

稳妥方案是在 macOS 或 WSL 的 Unix 文件系统中，将最终资产设为 `0755`，确保后续构建不覆盖权限，再打包并检查归档记录为 `100755`。不能只改源码权限或只看 Windows 文件属性。脚本必须位于打包后代码真正查找的位置；保留原来的 node_modules 路径未必有效。

## 3. 检查清单
核对 `package.json` 的 publisher/name/version、`engines.vscode`、main、激活条件及 contributions；核对锁文件、打包脚本、`.vscodeignore`/files 清单。解压审查 VSIX 中的 `extension.vsixmanifest`、`extension/package.json`、客户端/服务端 bundle、终止脚本及语法等运行资源，排除密钥和无关文件。

记录源码提交、扩展版本、VS Code 最低版本及测试版本、Node/npm、esbuild、vsce、languageclient/服务端依赖版本，以及实际验证的 Unreal/AngelScript 插件版本；交付文件附 SHA-256。

## 4. 验证与安装
用同一 VSIX 在干净 Windows、macOS 环境验证，不借用源码目录或独立 Node：安装后打开相应 Unreal 工程，检查激活、补全、诊断、日志，以及服务器停止、重启和退出后无残留进程。特别检查 macOS 安装后的脚本路径与权限。

同事在扩展面板选择“从 VSIX 安装”，或执行 `code --install-extension ./extension.vsix`，按提示重载；核对实际启用版本并避免旧副本冲突。

## 5. 支持边界
纯 JS 服务使用 VS Code 自带 Node、且全部资源随包时，可做到同事无需源码和独立 Node。当前尚未测试，不能承诺 Windows/macOS 均正常；只对已验证的系统、架构及版本组合声明支持。有原生依赖或外部程序时需分别处理平台产物。VSIX 不替代 Unreal、AngelScript 插件及工程配置，也不自动承诺 Web、远程环境或所有引擎版本兼容。

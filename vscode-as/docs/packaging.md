# VSIX 打包、安装和分发

在扩展仓库根执行，不从 skill 目录打包。先检查 `package.json`、构建脚本与 `.vscodeignore` 的当前内容；[1.9.5 基线](../references/vsix-1.9.5.md) 是可对照实例，不是永远的最新版本。

## 生成安装包

1. 需要时按 [开发指南](development.md) 安装两个子项目依赖。PEG 有变化先重生成 parser。
2. 根清单按项目 patch 惯例更新版本，保持变更范围可解释；不要给 `vsce package` 传位置版本参数，避免隐式 `npm version`/提交行为。
3. 运行：

```sh
npm exec --yes --package=@vscode/vsce@3.7.1 -- vsce package --no-dependencies
```

`vscode:prepublish` 会执行 `npm run compile`。该仓库已经 bundle 运行依赖，因此这里使用 `--no-dependencies`；不能把它当成其他未 bundle 扩展的通用省事开关。

## 清单与运行资产

基线的 ID 是 `Hazelight.unreal-angelscript`，最低 VSCode 为 `^1.67.0`（依据捆绑的 vscode-languageclient 8.1.0）。升级依赖或 VSCode API 后应重新核对；最低声明不等于最低版本已实测。

| 项目 | 应核对的内容 |
| --- | --- |
| 扩展 main | `./extension/dist/extension.js` |
| 语言服务器 | `language-server/dist/server.js`，由扩展使用安装目录定位 |
| AS debugger program | `./extension/dist/debugAdapter.js`，不能残留旧 `out/` |
| JS 依赖 | parser/节点表和 npm 运行依赖已进入 bundle；仅内置 Node 模块和 VSCode 注入模块保持外部 |
| 非 JS helper | languageclient 在 Unix 按 `__dirname` 读取 `terminateProcess.sh`；由 `extension/esbuild.js` 复制到 dist |
| 许可 | 保留 Hazelight MIT LICENSE，helper 随 Microsoft 的 `languageclient-LICENSE.txt` |

`.vscodeignore` 白名单只放清单、README、LICENSE、resources、语言配置、两个 TextMate JSON、扩展/LSP JS bundle 和上述 helper/许可证。不带本机 `.vscode`、源码/maps、示例、测试、文档、node_modules、用户 profile 或缓存。

检查 VSIX 中被清单引用的入口/资源确实存在。只看打包命令退出 0 不够；JS bundle 成功也不能证明外部脚本/资源已收齐。

## 隔离试安装

PowerShell 示例；把版本换成实际生成版本，使用专用新目录，不改变日常扩展：

```powershell
$version = "1.9.5" # 示例，替换成当前包版本
$vsix = Join-Path (Get-Location) "unreal-angelscript-$version.vsix"
$testRoot = "$env:LOCALAPPDATA/UnrealAngelscriptVsixTest/$version"
code --user-data-dir="$testRoot/user-data" --extensions-dir="$testRoot/extensions" --install-extension "$vsix"
code --user-data-dir="$testRoot/user-data" --extensions-dir="$testRoot/extensions" --list-extensions --show-versions
Get-FileHash "$vsix" -Algorithm SHA256
```

验收包 ID/版本、安装后关键 bundle/helper/grammar 与包内一致。需要启动才能确认的问题再运行隔离宿主；安装成功不等于接收者 UE 联调已通过。

## 给同事的最短说明

- 发送 `.vsix`；VSCode 扩展面板 `…` → **从 VSIX 安装** → 选择文件 → 按提示重载。也可 `code --install-extension ./unreal-angelscript-<版本>.vsix`。
- 不需要源码、Node/npm 或开发宿主；打开项目 Script 根目录，完整原生 API 和 AS 调试仍依赖兼容的 UE debug server（默认 27099）。VSIX 不安装引擎 async 补丁。
- 同 ID 安装会替换旧版，而非与官方扩展并存；后续 Marketplace 自动更新也可能覆盖内部版。说明风险，让接收者决定是否关闭**该扩展**自动更新，不改全局策略。
- 报告包绝对路径、ID、版本、字节大小、SHA256、实际验收平台及最低版本声明。不擅自发布 Marketplace 或上传外网。

## 跨平台限制

Windows 生成的 1.9.5 包中 Unix helper 的 ZIP mode 是 `100666`，没有执行位。该包仅做过 Windows 隔离安装验收，不能宣称 Linux/macOS 可直接分发。

需要其他平台时，在目标平台重新打包/验证 helper 权限与语言服务器退出、重启行为，再给出该平台支持结论；不要因为清单未设 platform 就推断已通过跨平台验证。若增加新的外部资源，也要重新核验白名单和运行路径。

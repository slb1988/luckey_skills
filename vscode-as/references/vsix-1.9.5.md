# 内部分发 VSIX 1.9.5：历史基线

这是一次产物记录，不表示该包仍是最新、已上传或已在所有机器安装。发布/分发操作流程见 [packaging](../docs/packaging.md)。

| 项目 | 当次证据 |
| --- | --- |
| 扩展 ID | `Hazelight.unreal-angelscript` |
| 版本 | `1.9.5`，包含 async/await 编辑器支持，未发布 Marketplace |
| 文件名 | `unreal-angelscript-1.9.5.vsix` |
| 生成位置 | `D:/Github/vscode-unreal-angelscript/unreal-angelscript-1.9.5.vsix`（本机路径） |
| 大小 | `406102` bytes，约 `396.58 KiB` |
| SHA256 | `83e3b81851934fa4474cb2696dbf17b311c99b698f574b1cdfe7a62cac40d873` |
| VSCode 最低声明 | `^1.67.0`，根据 languageclient 8.1.0 要求，不是最低版 GUI 验收 |
| 实测环境 | Windows x64、VSCode `1.138.0` |
| 隔离安装 | `%LOCALAPPDATA%/UnrealAngelscriptVsixTest/1.9.5` 下独立 user-data/extensions |

## 已完成的包级验证

- `@vscode/vsce@3.7.1` 正式打包触发 `vscode:prepublish → npm run compile` 成功。
- 最终 17 个 ZIP 条目，清单所指入口与资源存在；async/await PEG、TextMate、扩展/LSP bundle 包含在产物中。
- 修正 `main` 为 `./extension/dist/extension.js`，debugger program 为 `./extension/dist/debugAdapter.js`；LSP 使用安装目录内 `language-server/dist/server.js`。
- 白名单排除本机调试配置、源码/maps、测试/示例/文档、node_modules 和缓存。
- `extension/esbuild.js` 复制 languageclient 外部的 `terminateProcess.sh` 与 Microsoft 许可证；保留根 MIT LICENSE。
- 独立目录安装成功，`--list-extensions --show-versions` 列出 `hazelight.unreal-angelscript@1.9.5`；安装后 bundle、helper、grammar 与 VSIX/构建产物字节一致。
- 未替换日常扩展、未关闭 VSCode/UE、未改 MainDev、未提交或推送扩展源码。技能的 Git 提交不等于扩展源码已经提交。

## 限制与接手检查

- Windows 打包导致 Unix helper 的 ZIP mode 为 `100666`，没有执行位；Linux/macOS 未验收。面向它们时在目标平台重包并验证 helper 权限及 LSP 退出/重启。
- 未目视验收 VSCode UI、未运行真实 AS DAP 断点、未在其他接收者环境联调。
- 接收者无需 Node/npm 或源码，但完整能力依赖兼容 UE debug server；VSIX 不是引擎 async runtime 补丁。
- 同 ID 会替换旧版，Marketplace 后续更新可能覆盖内部分发版。
- 二进制保留在产物目录，不加入 skill 仓库。再次分发先核对文件存在/hash；重新构建或修改内容后重新记录版本与 hash，不能沿用本表证明新包。

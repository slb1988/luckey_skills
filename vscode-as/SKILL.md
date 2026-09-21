---
name: vscode-as
description: >-
  Unreal AngelScript 的 VSCode 扩展开发、排障、本地源码调试与 VSIX 分发。
  用户提到 vscode-unreal-angelscript、Hazelight.unreal-angelscript、.as 文件代码提示/补全/悬停/跳转/大纲/高亮、
  AngelScript async/await 编辑器支持、PEG/Peggy、TextMate/语义 token、Launch Client、Extension Development Host、
  Attach to Running Dev Host、AS 语言服务器、扩展打包/从 VSIX 安装，或运行时正常但编辑器不识别时使用。
  涉及 MainDev 与扩展仓库协作时区分引擎语义、LSP 和 DAP；不要用本 skill 替代 UE 编译器实现或通用 VSCode 运维。
---

# VSCode AngelScript

把运行时语法、编辑器语义、开发宿主和分发包作为四个独立验收对象。先定位缺失层，再做最小修复；不以“能着色”“编译成功”替代另外几层的证据。

## 按任务读取

| 任务 | 先读 |
| --- | --- |
| 首次接手、找源码/职责 | [docs/README.md](docs/README.md)、[架构与源码地图](docs/architecture.md) |
| 改语法、提示、高亮 | [开发与验证](docs/development.md)、[async/await 案例](references/as-async-vscode.md) |
| 启动本地环境、打 TS/LSP 断点 | [开发与验证：开发宿主](docs/development.md#开发宿主与断点) |
| 可安装插件、给同事分发 | [VSIX 打包与安装](docs/packaging.md) |
| 复盘 async/await、追查历史包 | [案例与边界](references/as-async-vscode.md)、[1.9.5 发布基线](references/vsix-1.9.5.md) |

仅加载当前分支所需资料。项目源代码、清单及最新项目文档优先于本 skill 的历史快照。

## 执行流程

### 1. 确认目标和边界

1. 用户指定 `ws:` 时使用 `workspace_resolve`。异工作区通过 Orca 的单个 worker 在返回路由执行，不把整个目标工程读入协调者；命令以实时 orchestration 指南为准。
2. 主要修改目标是 `ws:vscode-unreal-angelscript`。`ws:maindev` 提供实际语法/真实样例；运行时已经通过测试时先只读它，避免把编辑器修复扩大成引擎改造。
3. 进入目标仓库后先读项目规则并检查 VCS 状态；该扩展仓库的 `AGENTS.md` 指向拼写为 `AGETNS.md` 的规则文件。保留已有未提交改动，不新建工作树或切分支来掩盖状态。
4. 遵守用户本次指定模型；复用已保留的实施 worker 上下文。不要因为使用本 skill 自动切模型、运行 review 或提交源码。
5. MainDev 是 P4 工作区，不对它做 Git 操作。确需写入时按用户授权执行，归入独立 pending CL，不留 default，不自行 shelf/submit。

### 2. 用一个真实样例定位

- 从截图/真实 `.as` 提取声明及一个调用表达式，做最小 fixture；读取运行时实际支持的语法，不凭其他语言推断。
- 先问 AST/作用域是否形成，再查类型数据库、补全和语义消费者；最后处理独立的 TextMate 词法着色。
- 普通代码正常、异步函数内部提示整体消失时，优先检查函数声明解析，而不是只给补全列表增加关键字。
- 半成品输入、上下文关键字和作用域改变但语句文本未变，是编辑器与编译器的重要差别；按实际改动选对应回归，不铺无关矩阵。

### 3. 修改最窄实现面

- PEG 源修改后用仓库固定版本重生成 `angelscript.js`，不手改生成物。
- AST 新节点检查符号、类型、补全、签名和 inlay 的相关消费者；添加节点不要重排已有编号。
- 类型推断遵守引擎契约：当前 FTask/adapter await 是无值结果，不能把操作数的 Action/FTask 类型当成 await 返回类型。
- 关键字提示、TextMate、语义 token 不是同一张表；分别改真正负责的路径。
- 批量独立读取/查询；不反复读取未变化材料。请求结果与最小验收已有决定性证据即停止，邻接问题只报告。

### 4. 按层验证并交付

| 修改/请求 | 最小验收 |
| --- | --- |
| PEG/作用域/补全 | 代表 fixture 的针对性真实模块回归，必要的生成与构建 |
| TextMate | 真实 TextMate/Oniguruma token scope，而非仅检查 JSON 含关键字 |
| 本地开发环境 | 宿主加载本地扩展、实际 LSP bundle 路径与 workspace；联引擎才检查对应连接 |
| VSIX 分发 | 正式打包、入口/运行资产存在、独立目录试安装和版本核对 |

明确区分：模块测试、esbuild 构建、宿主启动、TCP 建连、GUI 目视效果、AS 断点执行、跨平台验收。只报告实际完成的层；esbuild 不是完整 `tsc` 类型检查。

## 安全默认值

- 使用独立开发宿主或隔离试安装目录，不关闭用户现有 VSCode/UE，不全局卸载已装扩展。
- 已有宿主就 attach；不要重复启动占用同一个 LSP inspector 的宿主。
- 不默认为用户安装到日常扩展目录，不发布 Marketplace，不上传源码/VSIX。分发时提醒同 ID 替换和自动更新风险。
- 参考资料中的具体版本、包 hash、路径和验证结果是快照。临时 PID、当前监听状态、Orca dispatch ID、费用不写成长期知识。

## 示例

**输入**：MainDev 的 `async FTask RunAsync(...)` 能运行，但 VSCode 里没有大纲、`await UISteps::` 后无提示。

**处理**：在扩展工作区核验 runtime 语法，复现声明/作用域与半成品补全；修改 PEG/AST/消费者并补真实模块回归，再单独验证 TextMate。保留引擎不动；需要用户使用时另提供开发宿主或 VSIX，而非声称安装版已自动更新。

## 结果格式

- 根因与修改：关键文件、保持不变的边界。
- 验证：实际命令/关键输出，区分已验收与未验收层。
- 使用：准确窗口/调试配置/重载步骤，或 VSIX 路径、ID、版本、大小、SHA256、安装条件。
- 状态：是否安装/提交/发布、平台限制、必要的下一步。不要用长报告替代结论，用户要求交接资料时再更新相应 docs/references。

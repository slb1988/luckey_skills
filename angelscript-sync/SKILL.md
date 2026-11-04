---
name: angelscript-sync
title: AngelScript 双向增量同步
description: 按用户指定方向，在 ws:maindev（Perforce）与 ws:unrealengine-angelscript（Git）间同步 Engine/Plugins/Angelscript，以及 ProjectM 的 PLAutomationFramework、PLASTestFeature、PLScriptAsync、PLGameCore 和通用 AS 测试/Core/Tasks；记录 P4 changelist、逐文件来源与 Git hash，保留去业务适配，汇总后一次复制并验证编译/测试。用户提到 AngelScript 插件迁移、项目层代码同步、框架/异步测试迁移、从 MainDev 拉取、回灌 MainDev、Git 到 P4、双向同步、继续上次同步、补齐遗漏或更新同步基线时使用。仅同步 Engine SKILL.md 文档且不涉及插件代码时使用 merge-engine-skills。
tags: [UnrealEngine, AngelScript, Perforce, Git, Sync]
---

# AngelScript 双向增量同步

一次任务只执行一个方向；双向支持不代表同时覆盖两边。用户决定源和目标，不根据上次方向、文件时间或哪边较新自行选择。

## 入口与边界

1. 从本轮用户指令提取方向，例如 `maindev → unrealengine-angelscript` 或反向。没有明确方向就先问，**不复制、不 checkout、不修改同步基线**。
2. 按范围读取 [Engine 基线](references/sync-state.json) 或 [ProjectM 基线](references/project-sync-state.json)，项目层同时阅读 [映射与上下文](references/projectm-context.md)；需要逐文件对照时再读 [项目文件清单](references/project-sync-manifest.json)。它们是上次观测，不是当前状态证明；区分已验证迁移版本、当前观察到的 head、未提交改动，不混用两层游标。
3. 对两端调用 `workspace_resolve`，用当前返回路径，不依赖历史盘符。目标与当前工作区相同则本地执行，否则用 Orca 在目标现有工作区派一名 worker；同机源可只读访问，不另建 worktree。跨机时明确源快照的传输方式，不假定另一端文件在本机。
4. coordinator 只传方向、范围、已知基线和验收；目标规则、P4 配置、构建环境由 worker 在对应上下文读取。执行时以证据为先，批量查询独立信息，不重读未变内容；完成迁移和最小编译验收后停止，邻接问题只报告。

按用户指定范围选择 profile，不因技能同时支持两层就自动同步全部：

| Profile | 范围与边界 |
|---|---|
| Engine | `Engine/Plugins/Angelscript/`，含 Source、ThirdParty 有效源码、插件描述、SKILL.md/references；不是全 Engine 镜像。 |
| ProjectM | 三个通用框架插件、抽取接口组成的 `PLGameCore`、所选 AS 测试/Core/Tasks；`Main/` → `ProjectM/` 的路径和有意适配见项目上下文。不是整款游戏迁移。 |

相邻插件只加入本次实际依赖或用户明确指定的文件。历史 `AngelscriptGAS` 的四个配套文件列在基线中；它们不是每次覆盖整个 GAS 插件的授权。排除 Binaries、Intermediate、Saved、DerivedDataCache、版本库元数据及其他实际构建缓存；不要因目录名是 ThirdParty 或 Git 忽略就误排除有效源码/构建输入。

## 1. 固定本次快照与保护已有改动

- 先查两端范围内的 `git status` / `p4 opened`、提交点和源文件状态；不得回滚或夹带无关改动。
- 默认取已提交源快照。用户要包含未提交改动时另列清单并固定文件哈希；源/目标有重叠未提交修改时先确认或合并，不能直接覆盖。
- 在 P4 工作区执行 P4 查询，核实 `p4 where` 的真实 depot 映射。若要求最新，先用 `sync -n` 与 have/head 检查；不能把落后的本地内容标成已同步到最新 CL。
- P4 字符集只在命令/连接级指定，不执行全局 `p4 set`。本次 MainDev 实测为 `none`；以后按服务器要求核实，不把其他 Unicode 服务器的 `utf8` 配置套过来。
- 同时变化的源文件和目标文件不能靠“选定方向”消除冲突。比较上次对应版本，区分源新增变化与目标独立修改；有冲突就合并或请用户裁决。

## 2. 一次收集完整的变化清单

详细查询模板见 [命令与清单约定](references/commands.md)。

### MainDev / P4 → Git

- 按插件路径查最新 **submitted** CL，分别记所有作者和 `sunlaibing` 的最后相关 CL。作者历史是定位线索；除非用户明确只要其提交，否则不漏掉其他作者的相关更新。
- 有可信基线时查询 `(已同步 CL, 本次截止 CL]`，汇总 CL 中属于范围的文件并去重。不要复制 `p4 describe` 中同一 CL 的范围外文件。
- 再检查源有效文件与目标的实际差异，补上历史漏迁或 Git ignore 隐藏的新文件。无基线时做范围内完整差异，不猜一个 CL 当起点。
- 本次复制最终选定快照的每个文件一次，不逐 CL 反复覆盖。

### Git → MainDev / P4

- 固定 Git 源提交；用已验证的 Git 对照点到该提交的范围内 diff 收集增删改，明确包含的未提交文件另列。
- 初次反向同步不等于复制 Git 端整个目录。先以已验证的对应内容建立对照，再取 Git 端新增差异，避免把刚从 P4 导入的同一变化再次回灌。
- Git 端原有专属文档、`.gitignore` 和工作区辅助文件不自动成为 P4 新文件。按本轮范围与用途决定；源里“存在”不等于本轮“新增”。
- 对照期间 P4 也发生变化时做三方比较。没有可重建的基线则报告并建立内容对照，不盲选 Git HEAD 或 P4 服务器最高 CL。
- 项目层按逐文件来源映射回灌 Git 对照点之后的增量，不把去业务移植后的全文件覆盖回 MainDev；`PLGameCore` 的接口映射回实际原插件，不猜造源端同名插件。既有游戏功能的排除不等于获准从 MainDev 删除它们。

### 清单约定

使用逐文件清单，至少区分 `add / modify / delete / conflict / preserve / exclude`，记录相对路径、来源版本、源哈希与目标复制前状态。目录项数不能代替实际文件数。

- 目标独有文件默认保留；只有源版本历史证明本次删除/重命名且目标未独立修改时，才按清单处理删除。禁止目录镜像清理（如 `robocopy /MIR`）。
- 检查缺失的新源码及必要 `.mmd` / `.svg` 等资料。`git status` 看不到不代表没有，用 `git check-ignore -v` 查原因。
- 先解决冲突与范围问题，再冻结清单执行一批复制；复制前确认源哈希/目标状态没有漂移。清单放本次工作记录，不把机器绝对路径或临时日志写进共享技能正文。

## 3. 目标侧准备、批量复制与必要修复

| 目标 | 做法 |
|---|---|
| Git | 不切分支、不 reset。只在清单内处理遗留只读属性；普通复制更新目标 mtime，不保留源旧时间戳。有效新文件被忽略时，在最窄目录修 ignore 或精确强制添加，保留规则对缓存的保护；“出现在 status”不等于已提交。 |
| P4 | 为本次改动建立独立 numbered pending CL；既有文件先 `p4 edit -c <CL>`，新增/删除按清单 `add/delete -c <CL>`。收尾只对清单做 reconcile/核对，不留 default，不动其他 CL，不主动 shelf/submit。不要用 chmod/attrib 绕过 P4 checkout。 |

批量复制使用不保留旧 mtime 的方式（Python `shutil.copyfile` / `copy`，不要 `copy2`；不要 `cp -p`）。复制后校验哈希；合并或兼容修复导致与源不同的文件须记录理由，不能谎称全部字节一致。

若反射头布局变化但 UHT 被旧时间戳误导，刷新本次变化的相关目标源文件或用目标构建系统受支持的方式重新生成；不手改 `*.generated.h`，不默认清空整个引擎缓存。

本次直接引入的编译兼容问题应修到成功，不止汇报错误。历史例子：`FAngelscriptCompilationDelegate` 增加 `ECompileType` 参数，`AngelscriptGASModule.cpp` 的 `GetPostCompile().AddLambda` 也要匹配。补迁匹配版本或做最小修复；不能据此每次全量覆盖兄弟插件。若依赖修复超过本轮范围或涉及不兼容设计，先报告阻塞并确认。

## 4. 最小验收与收尾

1. 核对清单每个有效文件：复制/合并完成、删除有依据、目标专属与用户改动保留；新文件未被 ignore 漏掉。不要重复全仓探索。
2. 在**目标工作区**实际构建相关 Editor target。`unrealengine-angelscript` 已验证命令：
   ```text
   Engine\Build\BatchFiles\Build.bat UnrealEditor Win64 Development -WaitMutex -NoHotReload
   ```
   ProjectM 的 C++ 改动使用实际 `ProjectMEditor` 目标，AS 用例使用相应测试入口，见项目上下文；旧 UnrealEditor 构建不能替代项目层验收。`maindev` 作为目标时按其现行规则选实际 Editor/项目构建命令，不照搬 Git 端命令。
3. 保存构建真实退出码、`Result: Succeeded` 和日志路径。不要经 `| tail` 丢掉退出码；旧 DLL 存在或以前构建成功不能证明本次通过。区分实际编译/链接与纯 metadata/no-op 增量。
4. 检查最终 `git status` 或 `p4 opened -c <CL>`，明确本次新增/修改/删除与待提交状态。不自动 commit/push/submit/shelf，除非用户授权或目标现行规则另有明确要求。
5. 只有文件验收及本轮适用的构建/测试通过后，更新对应 profile 的状态资源与文件清单。失败仅记录本次失败与 pending 状态，**不推进上次成功游标**；只做文档/版本核查时不得宣称重新执行了历史构建测试。

### 基线更新原则

- 始终记录本次方向、范围、源截止版本、目标原版本/最终版本、必要适配例外、构建结果和验证日期。
- P4→Git：区分源插件最新相关 submitted CL 与全服务器最新 CL；Git 未提交就保留 `pending`，不把当前 HEAD 写成包含新变化的提交。
- Git→P4：记录源 Git hash 与独立 pending CL；pending CL 不能冒充目标 submitted CL。用户之后提交后，核对实际提交内容再填最终 submitted CL。
- 两个方向分开记录。P4→Git 的成功不代表 Git→P4 已执行；已验证对应内容可以作为首次反向比较起点，但对照点的未提交例外仍要核实。
- 一个最高 CL 不能证明所有文件已对齐；项目层按范围记录 CL，并保留选定文件的 P4 depot/#rev、对应 submitted CL、源内容哈希与目标 Git blob/内容哈希。游标之后的历史查询负责增量，逐文件验收负责完整性。
- 相同内容、换行差异、有意适配、目标专属接线和无法解释的差异分开记录。未知来源、脏源文件或未被目标提交包含的内容不能标为已提交的一致基线。
- 下次先核对记录的 Git hash 可解析且在预期历史中、所需 P4 #rev 可取回，再检查当前两端相对基线的增量；记录的 snapshot 不能用当前 HEAD 无条件替换。
- 更新此技能仓库的状态文件遵循该仓库提交规则；这不自动授权提交任何引擎仓库。

## 输出

简明汇报：`方向；源 P4 CL / Git hash；补迁与修复；目标构建及日志；Git/P4 提交或 pending 状态；基线是否更新；阻塞项`。没有实际差异就如实说，不制造改动。

演练样例在 [evals/evals.json](evals/evals.json)。演练只用模拟输入，不对真实工作区执行反向同步或提交。

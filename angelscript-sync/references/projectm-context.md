# ProjectM 通用自动化与异步移植上下文

此 profile 的目标是可独立于游戏业务使用的框架、异步机制和测试，不是 MainDev 游戏镜像。同步方向仍由用户每轮指定。当前版本真值见 [项目状态](project-sync-state.json)，逐文件来源和内容签名见 [文件清单](project-sync-manifest.json)；不要从本页的说明推断某个最新 CL 已经迁入。

## 代码层次与路径映射

| 源（maindev） | 目标（unrealengine-angelscript） | 同步语义 |
|---|---|---|
| `Main/Plugins/PLAutomationFramework/` | `ProjectM/Plugins/PLAutomationFramework/` | 通用 Action/Sequence、async Case、UI 输入/查询、动态注册/CLI；剔除下表的游戏业务。 |
| `Main/Plugins/PLASTestFeature/` | `ProjectM/Plugins/PLASTestFeature/` | 已迁的测试扩展插件，保留与通用框架/异步机制的接线。 |
| `Main/Plugins/PLScriptAsync/` | `ProjectM/Plugins/PLScriptAsync/` | 通用异步任务、取消/作用域/时间域及相应回归支持。 |
| `Main/Plugins/LogCore/Source/LogCore/` 与 `Main/Plugins/ProjectLungfishCore/Source/PLCoreGame/` 中选定文件 | `ProjectM/Plugins/PLGameCore/` | 组合移植，不是源端同名目录。具体文件来源以清单为准。 |
| `Main/Script/Tests/UnitTests/ScriptAsync/` | `ProjectM/Script/Tests/UnitTests/ScriptAsync/` | 明确要求整目录迁移；原 ZIP 是归档，不解压加入活跃编译。 |
| `Main/Script/Tests/Core/` 的选定部分 | `ProjectM/Script/Tests/Core/` | Core/Tasks 是任务组合与测试支撑，不是每个 `.as` 都是可直接发现的单测。 |
| `Main/Script/Tests/UnitTests/UI/UITaskCallback_Test.as`、四个 `0100_FunctionTest` 用例 | `ProjectM/Script/Tests/` 下同一相对路径 | 只迁选定通用用例，不自动扩大到所有 UI/游戏集成测试。 |

`PLGameCore` 当前集中三类共享能力：

- LogCore 的 `LogUtils` / `LogScopeStepInterface`。
- PLCoreGame 的虚拟光标。
- PLCoreGame 的 `WidgetNode` / `WidgetTree` / `WidgetQuery` 实现及查询测试。

它不提供真实游戏存档、建筑、背包、角色、项目 ASC 等业务系统。接口移入新模块后，导出宏、include、Build.cs 模块依赖、`.uplugin` 插件依赖和 ProjectM 的启用关系共同构成有效接线；同步源码时不能恢复源模块名而不处理这些对应关系。

## 已授权的去业务边界

以下是持续的移植边界，不是“还没同步到”的遗漏；没有新的明确授权时，不从源全量覆盖恢复。

| 项目专属部分 | ProjectM 处理 |
|---|---|
| `PLBuildingStreamTestBlueprintLibrary`、`PLPendingDestructionTestLibrary` | 不迁依赖真实存档/建筑状态的夹具声明及实现。 |
| `PLBuildingDormancyEditorSubsystem`、`PLBuildingDormancyEditorLibrary` | 不迁世界/玩家存档初始化、角色设定、真实蓝图/地图及项目 WP/GameMode 配置。 |
| UI `SetContainerOpen`、`SetAcceptUnpickableItems` | 不保留背包业务/物品接收规则接口。 |
| `SetActorGodMode` | 不保留强转项目 ASC、项目无敌 Tag/GE 的业务实现。 |
| 原生 `SingleStep.OptionUIPilotEntry` / `UOptionUITestCase` | 目标后续清理已解除这项业务脚本依赖；不要因它仍在源框架中而自动恢复。 |
| Tasks 的 Attr/Eqp/Gas/Inv/InvUI/Player/Time/World | 不迁依赖项目角色、ASC、ActorKey、库存或世界时间的任务。 |
| `InputTask` / `DebugTask` | 使用通用 UE 调用；不恢复游戏蒙太奇 ActorKey 部分及游戏 HUD 默认名。 |

Core 的通用集合包括 Flow/Input/UI/Debug/Level/Perf、Internal 的 UITaskInternal/UIWidgetPredicate，以及它们需要的 base、builder、category、Input/UI helper、Async 夹具。后续新增任务仍按其真实依赖决定，不按文件夹一概全部迁移。

去业务不等于伪造业务成功：新增游戏耦合应明确排除、用真实 UE 能力替换或请求范围决定，不能加入返回默认成功的 stub 或削弱测试断言。

## 项目接线属于目标侧上下文

- `ProjectM.uproject` 的四插件启用关系、目标 async 语言配置和 runner/TestHost 路径服务于独立 ProjectM。
- 本移植的 CommonUI 输入路由使用 `GameViewportClientClassName=/Script/CommonUI.CommonGameViewportClient`。同步 `DefaultEngine.ini` 时保留这项目标配置；不要因 MainDev 使用另一项目 ViewportClient 就照抄覆盖。
- `Plugins/` 与 ScriptAsync 目录内的窄 `.gitignore` 例外用于交付有效文件/归档，不取消产物缓存忽略。
- 这些配置、独立模块接线和迁移说明可能没有 P4 源端一一对应文件，应记录为 `target_only`，反向同步时不自动复制到 `Main/Config`。

## 验收是三套不同的测试入口

| 层次 | 入口/发现机制 | 能证明什么 |
|---|---|---|
| AS 单测 | `UnrealEditor-Cmd.exe <ProjectM.uproject> -run=AngelscriptTest -as-force-preprocess-editor-code -NullRHI` | 目标编辑器代码预处理、AS 编译和单测入口。 |
| 框架 Case / PIE | `UnrealEditor.exe <ProjectM.uproject> /Engine/Maps/Entry -PLAutoRunTests=FunctionTest -PLAutoAutoQuit -PLAutoMaxDuration=180 -as-force-preprocess-editor-code -NullRHI` | FunctionTest 分类通过真实框架执行；以 terminal-state 的 Passed/ExitCode/SelectedTests 为判据。 |
| 原生自动化夹具 | UE Automation runner 的 AsyncSafety、WidgetWait、SourceVM、ManualStateMachine、OwnerDestruction 选择器 | C++/VM 与通用任务支撑的相应用例，不等于所有 AS Case 都执行了。 |

原生发现名沿用 `ProjectLungfish.PLAutomation.*`、`ProjectLungfish.ScriptAsync.*` 和 `ProjectLungfish.ScriptAsyncSafety.*`；工程目录改为 ProjectM 不意味着发现名也改名。具体已验证选择串和历史日志见项目状态。

新增测试在正确目录可见、AS 编译成功与用例真正通过是不同事实。`AsyncDebugProtocolFixture` 编译成功不证明专用交互调试器矩阵完成；ZIP 未解压也不能计为已运行用例。记录实际选中/执行/通过数量，不把既有测试数算成全是新增测试。

## 状态字段的含义

| 资源/字段 | 用途 |
|---|---|
| state 与 manifest 的 `snapshot_id` / `verified_at` | 两文件必须属于同一观测批次，不能新旧拼接。 |
| state `target_version_observations.current_head` / manifest `target_git_head` | 固定的 Git 观察点；两者须一致，不代表未提交内容已进入该提交。 |
| state `target_version_observations.migration_commit` | 已确认包含原迁移的提交锚点；后续清理和正在开发的内容另记。 |
| state `source_version_observations.groups.*.source_observed_submitted_max_cl` | 选定范围当前已提交版本的上界，不是自动可用的成功游标。 |
| state `directions.*.successful_p4_cursor` / `successful_git_cursor` | 为 null 时没有可证明的完整历史游标，不从观察到的最大值补造。 |
| manifest `source.p4.have_revision` / `have_submitted_cl` | 可取回的当前源文件版本；与 `original_import_revision` 区分。 |
| manifest `target.git_head_blob` / `git_head_sha256` / `workspace_sha256` | 分别为 Git blob ID、已提交内容 SHA256 和本地内容 SHA256；不能跨算法或跨工作区/提交状态直接比较。 |
| state `pending_updates_and_uncertainties` / `target_version_observations.pending` | 本次尚未迁入的源更新、未知来源和目标并行修改，更新前先处理。 |

manifest 的 `adapted` 是内容不同的分类，包含保留的移植差异，也可能包含待迁源更新或目标未提交开发；它本身不证明差异已被授权或验证通过。批准的边界以本页和 state 的 `preserve_adaptations_and_exclusions` 为准。

## 下次更新如何保持版本对应

1. 先确认方向和本次 profile。读取项目状态中的源范围、已验证对照点与 pending/unknown 项；Engine 的 CL 144419 历史点不能作为项目三插件与 AS 测试的共同游标。
2. 按路径或 group 过滤读取文件清单，不把整份逐文件 JSON 灌入上下文。用已证实的版本重建源/目标对应：源 `headChange` 是当前观察，`#have` 对应的 submitted CL 才是实际源快照候选；原始导入版本未知的适配文件，先恢复历史对应或明确比较后建立新对照，不把当前源版本倒填为迁入时版本。
3. 正向按各范围游标和实际文件来源收集后续增量，再把增量合并到现有移植版本；保留模块重定位、去业务逻辑及目标配置。目录新增文件要分类，不将 excluded 项误作漏迁。
4. 反向先计算已记录目标提交之后的真实增量，再映射回原 P4 插件/脚本文件；不能把精简后的 ProjectM 全文件反盖 MainDev，也不能把 `PLGameCore` 整目录作为同名源插件新增。源端业务删除、无来源新文件或多源合并冲突需用户确认。
5. 当前 Git HEAD 未包含迁入文件时，仅记录工作区验证与其内容签名；待用户实际提交后核对 tree/blob 再登记已提交 hash。不要自动提交引擎仓库来制造“干净”基线。
6. 变更后的最小验收通过才推进对应成功游标；只做版本记录时保留历史测试结果的时间/来源，不宣称重跑。方向间不共享“已执行”的状态。

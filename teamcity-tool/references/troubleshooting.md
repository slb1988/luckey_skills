# TeamCity 构建失败排障

> 从 SKILL.md 移出。TeamCity 服务自身的行为陷阱见 [gotchas.md](gotchas.md)。

UE 构建报 `A conflicting instance of Global\UnrealBuildTool_Mutex_<hash> is already running`（UBT 退出码 ConflictingInstance）时：mutex hash 对应**引擎根目录**，含义是同机有另一个 UBT 实例在对同一引擎目录工作，冲突方不一定是 TeamCity 任务。排查顺序：(1) 每台构建机只有一个 agent，用 REST API 查该 agent 在撞锁时间窗内的所有 build（见 rest-api.md）排除 TC 内部冲突；(2) 若 TC 侧无并发 build，元凶在 TC 之外——最常见是有人在这台机器上开着 UnrealEditor+Live Coding 或 UGS 客户端自动编译，P4 sync 落地文件变更会触发它（特征：撞锁总发生在 sync 完成后几秒内）；(3) 上机看 `<EngineRoot>\Engine\Programs\UnrealBuildTool\Log.txt` 拿冲突方的完整命令行和启动时间，或用 Sysinternals `handle64.exe -a UnrealBuildTool_Mutex`（管理员）循环抓持锁进程。缓解：UBT 撞锁几乎秒失败（~0.3s）但持锁方常只占几秒，在 build 脚本里对 ConflictingInstance 加 sleep 30s 重试 3~5 次即可自愈。

## PLN_TaskBuildUELinux "莫名全量重编"（2026-08-24/25，#179/#189/#200，已根治）

现象：CL 变动很小甚至无变动，构建却突然全量重编引擎 4500+ actions，且反复出现。拆解方法：下载日志（`/downloadBuildLog.html?buildId=<id>`）grep `Invalidating makefile|Creating makefile|to run N action`，UBT 会直接给出失效原因。

**根因（三层叠加）**：
1. **两个 Editor 型 target 共享中间目录**：UBT 中所有 `TargetType.Editor` 的 app 名都是 `UnrealEditor`（`UEBuildTarget.GetAppNameForTargetType`），引擎模块中间产物写到 app 级目录 `Engine/Intermediate/Build/Linux/x64/UnrealEditor/`。评审链编裸 `UnrealEditor`、日常链编 `ProjectLungfishEditor`，写的是**同一个** `SharedDefinitions.Engine.Cpp20.h`。
2. **两个 target 的 GlobalDefinitions 不同**：`ProjectLungfishGame.Target.cs` 注入 `ENABLE_STATNAMEDEVENTS=1`、`UE_PLATFORM_IO_DISPATCHER_ENABLED=1`、GameFeature 插件配置等 → 同一文件在两种内容间随链切换反复改写（SharedDefinitions 的 variant 后缀只区分 RTTI/Cpp20 等少数轴，不区分 GlobalDefinitions 差异）。
3. **makefile 有效性是时间戳检查**：`TargetMakefile.IsValidForSourceFiles` 中 `LastWriteTimeUtc > Makefile.CreateTimeUtc` 即 invalid（不看内容）。于是每次链切换，双方都互相引爆对方 makefile：评审链引擎构建 4571 全量，随后的日常链项目构建再 2000+ 增量（#179 项目侧 `SharedDefinitions.Engine.RTTI.Cpp20.h modified` 即对侧实锤）。日常链彼此连续时内容不变（write-if-changed），所以平时 40s 秒过——掩盖了机制。

**修复（CL 1256 @Teamcity_PLN，kts rev#7）**：TaskBuildUELinux 统一只编 `%project_name%Editor`（引擎模块作为依赖一并编译，shelved CL 的 Engine/ 改动同样被覆盖），删掉裸 UnrealEditor target 构建和 `Saved/Build.version` marker 短路。单一写者后文件不再翻转，UBT 增量判断恢复精确。切换后**第一次构建会有一次性全量**（内容最后一次翻转），之后评审链 docs-only shelf 回到秒级。

旁证与排除：
- 曾怀疑 Build.cs/uplugin 提交（126003/126170）导致内容变化——但项目插件的 Build.cs 不影响裸 UnrealEditor target 的 Engine 模块 define，该假设不成立；它们只解释了日常链的合理增量（#180 `PLCoreGame.Build.cs modified` 1019 / #184 608 / #199 `source file added` 995 actions）。
- GPF 每构建两次重写 `UnrealEditorGPF` 目录的同名文件（Make 与 VSCode 生成器内容不同，FileHashCache 会话内告警 "Re-writing a file that was previously written with different content"）——GPF 目录与真实 target 目录隔离（IntermediateEnvironment 后缀机制：GPF/GCD/IWYU 等），不直接参与失效，但同源证明了生成内容随环境变化。
- `Engine/Build/Build.version`（depot rev#15 @121188 后未变）的 mtime 被工作区重拉刷新也会造成 `Build.version is newer` 型全量（#179 的引擎侧原因），属一次性遗留。

背景机制备忘：链为 Task_Sync_CyanCook_Depot（P4SyncWorkspace.py 脚本 sync）→ Task_Unshelve（revert+unshelve，不 sync）→ TaskBuildUELinux，两链共用工作区 `DefaultAgent_MainDev`。注意两个同名文件：脚本 marker 曾是 `<workspace>/Saved/Build.version`；UBT 追踪的是 `Engine/Build/Build.version`。

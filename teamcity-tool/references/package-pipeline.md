# TeamCity 打包管线(PL_BuildProjectWindows / PL_BuildUgsBinaries)

> 源 skill:`D:\MainDev\.claude\skills\teamcity-package-pipeline\SKILL.md`(ProjectLungfish 项目内的工作副本,随项目 P4 版本化)。本文件是其在 vault 的镜像参考,改动应先在项目内完成再同步过来。

## 基础设施地图

| 资源 | 位置 | 访问方式 |
|---|---|---|
| TeamCity 服务器 | http://192.168.2.13:8111 | REST API,Bearer token(cyancook 账号) |
| CI 脚本(build.xml / *.py) | `//depot/DevOps/...` @ 192.168.2.13:1666 | `p4 -p 192.168.2.13:1666 -u jenkins_bot`(可读) |
| TeamCity versioned settings(Kotlin) | `//depot/Teamcity/.teamcity/` @ 192.168.2.13:1666 | REST 修改自动提交 |
| 游戏 P4 | 192.168.2.236:1666(镜像) | 本机 .p4config |
| pyAutomation 服务 | http://192.168.2.13:5000 | 文件归属人/CL 提交者/Feishu open_id |
| 构建机 | WinBuilder1(打包)、WinBuilder3、WinTest1 | 工作区 `{agent}_{stream}` |

## 通用模式(common-patterns)

- 新 TeamCity agent 已创建时,不要让用户手工配分支构建:直接从 `PL_BuildProjectWindows` / `PL_WpBuild` 复制出每个 P4 分支一个 buildType(如 `PL_BuildProjectWindows_MainDev`、`PL_BuildProjectWindows_Rel-0.2`),设置 `p4.stream`/`p4.streamName`/`p4.client=%teamcity.agent.name%_%p4.streamName%`,并用 Agent Requirement 绑定到目标 agent。
- TeamCity 按分支创建游戏 P4 workspace 时,Agent 名必须稳定且无空格(在 agent 的 `conf/buildAgent.properties` 配 `name=DefaultAgent` 一类名字),workspace/client 名统一由 `%teamcity.agent.name%_%p4.streamName%` 生成,并把非法字符规整到 `[A-Za-z0-9_.-]`。如果 client 名必须精确可控,关闭 TeamCity 自动 checkout,第一步脚本显式 `p4 client -S <stream> -o <client>` / `p4 sync`,否则 TeamCity 可能生成自己的 client 名。
- 拆分 MainDev 打包链时,顶层总控 buildType 命名为 `PL_MainDev_Pipeline` 且使用 Composite + snapshot dependencies 串起阶段;阶段 buildType 命名为 `PL_MainDev_SyncWorkspace` / `PL_MainDev_BuildEditor` / `PL_MainDev_Cook` / `PL_MainDev_Package` / `PL_MainDev_ArchiveOrDeploy`。不要在 buildType 名称里加序号,执行顺序只由依赖 graph 表达;`SyncWorkspace` 负责真实 `p4 client` + `p4 sync`,其余阶段可先 no-op 占位。

## Troubleshooting

- 固定 `{agent}_{streamName}` workspace 意味着同一 agent+stream 只能同时跑一个构建;给 build 加 Agent Requirement/Agent Pool 绑定和并发数限制。否则 `sync/revert/clean` 会互踩同一个 P4 client/root。
- ⚠️ **Agent 工作区互踩**:WinBuilder3 本机是 TeamCity agent;WP_Build 系列(每晚 03:00-06:00)等构建跑在本工作区,Revert Client 步骤执行 `p4 revert -w //...`,会清掉 pending CL 文件;Build UE 与本地编辑器/cook 互锁 DLL(LNK1104)。**pending CL 必须当天提交**;长时间本地 cook 验证前先暂停指向本机的触发器。
- ⚠️ **P4 陷阱:`p4 revert -a` 会 revert open-for-add 文件**(add 无 diff 被视为"未变更")。索引脚本收尾的 revert -a 只能针对单文件路径,绝不能 `-c <CL>` 整个含 add 的 changelist。
- **TeamCity Agent 自动清理 checkout 目录误删游戏工作区(2026-08-19,E:\WinBuilder3_MainDev 被整树 rd /s /q,PL_BuildUgsBinaries #5141-#5143 连续红)**:机制=任何曾被 buildType 登记为 checkout directory 的目录都进 agent 的 directory map;登记配置移除 checkoutDir/被删后条目成孤儿,默认 192h(`teamcity.agent.checkoutDir.expireHours`)未再被使用即被 DirectoryMapDirectoriesCleanerImpl 整树删除(agent 日志 "Build directory has expired, unused or free disk space is needed"——与磁盘余量无关,当时还剩 1.55TB)。罪魁=PLN `Task_Sync_CyanCookDepot`:kts rev#1-#6 设了 `checkoutDir`(8/11 CL1129 改为 `%P4SyncRoot%/%teamcity.agent.name%_%P4Stream%`),8/11 23:05 build #213 在 WinBuilder3 以 `E:\WinBuilder3_MainDev` 为 checkout dir 跑一次即登记;8/12 CL1135 移除 checkoutDir 改脚本 sync 后条目成孤儿,192h 后(8/19 23:09,分钟级吻合)被删;同日 06:30 还在 WinBuilder1 以 `E:\WinBuilder1_MainDev` 跑过一次(冲掉 client Root+sync -f 4h,Root 后已改回 F:\)。症状链:磁盘文件没了但 P4 have-table 还在 → 裸 `p4 sync` 只拉 CL delta 秒过 → RunUAT.bat / UnrealEditor-Cmd.exe not recognized → Upload to Minio 报 "Source directory does not exist: ...\LocalBuilds\ArchiveForUGS\Staging"。恢复:`p4 -c <client> clean <root>\...`(校验差异只补缺失,远比 sync -f 全量快;会删 depot 外本地多余文件)。同类残留:① WinBuilder1 的 E:\WinBuilder1_MainDev 孤儿条目 8/20 06:30 到期(孤儿副本,真工作区在 F:\);② PLN TaskBuildCodeGraph/TaskBuildUELinux/TaskPrintP4Ignore 仍有 checkoutDir=/mnt/disk2/... 且无 requirements 块。防御:① 游戏工作区路径永不登记为 checkout dir,用 checkoutDir 的配置必须 `requirements` 钉死 agent;② buildAgent.properties 设 `teamcity.agent.checkoutDir.expireHours=never` 并重启 agent(低磁盘清理由 freeSpaceMb 单独控制);③ 删除被进程占用(coreclr.dll Access denied)删不干净会留 `.teamcity.clean.checkout.required` 标记,需手工删标记+directory map 陈旧条目,否则下次强制重清;④ agent 自升级会重写 directory map 时间戳,升级后一周是高危窗口。**详细事故报告见 [checkout-dir-auto-clean.md](checkout-dir-auto-clean.md)。**
- **PL_BuildUgsBinaries Step10(Build UE)/Step11(AS Compile Check)的 PowerShell 吞错**:RunUAT.bat 不存在时 Write-Error 后仍 exit 0,构建只在 Step12 Upload to Minio 才变红;若 Staging 目录有残留会以陈旧产物绿灯发布。改这两个步骤脚本时务必加 Test-Path 前置守卫 + fail-fast(failure condition 的 "stop build immediately" 会跳过 `execute_only_if_failed` 通知步骤,**fail-fast 要写在步骤脚本内**)。
- **`A conflicting instance of Global\UnrealBuildTool_Mutex_<hash>`(2026-08-14 查明根因,PL_RunProcessorsOnDT #12-#14 连续三天 07:01-07:03 撞锁)**:mutex hash 按 engine root 路径生成。**根因 = 本机跑了两个 TeamCity agent JVM**:8/11 18:49 agent 自升级后旧 JVM(PID 31896,端口 9090,父进程已退)没被杀死,launcher 又起了新 JVM(端口 9091);两个进程都以 "WinBuilder3"(AgentId=31) 注册到同一服务器,**同一个 build 被两个 agent 同时完整执行两遍**(agent 日志里 `Starting Build {id=...}` 出现两次、每个 Step 的 CallRunnerStage 成对、两个 ant runtime 文件)。两边的 Build UE 步骤同时跑 GenerateProjectFiles/UBT → 后到的必撞 ConflictingInstance;赢的一方继续跑完(日志里会出现第二条 flow 的 live commandlet 输出,log 按 flowId 分组看起来像"幽灵步骤")。**双重 sync/revert 同一 P4 client 还有清掉 pending CL 的风险**。排查确认路径:`Get-CimInstance Win32_Process -Filter "Name='java.exe'"` 数 agent JVM 个数(正常=1 launcher+1 agent)+ agent 日志数 `Starting Build` 次数。修法:杀掉孤儿 JVM;防御性兜底=buildUE 的 UBT 调用加 `-WaitMutex`。验证锁是否还被持有:PS `[System.Threading.Mutex]::OpenExisting('Global\UnrealBuildTool_Mutex_<hash>')`,抛 WaitHandleCannotBeOpenedException=无人持有(named mutex 句柄全关即销毁,无需手工清理)。

## 配置结构

- `PL_BuildProjectWindows` 基于模板 `PL_WpBuild`(13 配置共用);`env.p4_stream` 区分流;定时触发器用 `buildParams.env.<name>` 做参数定制(夜间全量 cook 即此机制)。
- **改继承步骤须改模板**(buildType 层 PUT 返回 200 但响应体是旧值 = 层级错了)。
- REST 改步骤脚本:`PUT .../steps/<stepId>/parameters/jetbrains_powershell_script_code`(text/plain),GET 回读核对。

## UAT / Cook 关键事实(UE 5.7)

- UAT 命令行的 `-noglobalshaderddc -nomaterialtranslationddc` 不会传入 cook 进程(无效参数);给 cooker 传参用 `-AdditionalCookerOptions="..."`。
- `-fastexit`:修复 cook 收尾偶发 0xC0000005→exit 25(2026-07-08)。
- MPCook:`-CookProcessCount=N`,1 Director + N-1 Worker;**收尾(BuildChunkManifest 等)仍 Director 单线程**。64C/128G N=4:43k 包主循环 22.9→6-10 min,内存 ~80 GiB。
- 增量:`-CookIncremental`;强制全量 `-fullcook`(仍写增量元数据,夜间兜底);UAT 不加 `-clean` 不删 Saved/Cooked。
- **增量类允许名单(核心)**:包可跳过要求所有 ImportedClasses `bTargetIterativeEnabled=true`,由 `Editor.ini:[CookSettings]:IncrementalClassScriptPackageAllowList` 控制;引擎默认只 `Allow,<EngineRoot>` → import 项目 C++ 类的包全部 NonIterative,WP generator 失效则其生成包级联失效。项目已加 `Allow,<ProjectRoot>`(DefaultEditor.ini)→ skip 17.3k→39.8k,主循环 476s→378s。残留 ~3k:AS 类作为 export 的 Class 的包(动画资产 AS AnimNotify 等)——AS 类进 ClassDigests 但永远不被 Allow(插件无名为 "Angelscript" 的模块,模块解析失败,EditorDomainUtils.cpp:1290),天然安全。个别不确定类用 `+IncrementalClassDenyList` 拉黑;诊断 `-LogCmds="LogEditorDomain Verbose"`("NonIterative Package X due to Y");正确性校验 `-IncrementalValidate` cook 模式。
- **⚠️ AS 父类蓝图盲区(2026-07-13 事故,CL 116377 修复)**:蓝图的 AS 父类(/Script/Angelscript 动态类)不进 ImportedClasses(PackageReader.cpp SerializeImportedClasses 只收集"export 的 Class"+UScriptStruct import),资格检查与 CalculatePackageDigest 都看不到它;/Script/Angelscript 是运行时合成包无 .uasset,父类布局变更(.as 增删 UPROPERTY)不触发任何失效 → 陈旧包被无限复用 → 运行时 unversioned 序列化索引错位崩溃(GA_AffixFunction_SpawnFireAOE)。**配置层不可修复**(回退名单/Deny/DenyList 均实测或机制上无效);修复=引擎 @CYANCOOK 守卫:TargetDomainUtils.cpp IsIncrementalCookEnabled 查资产 NativeParentClassPath tag 含 "/Script/Angelscript." 即强制 NonIterative(AS 类注册为 native,覆盖 BP→BP→AS 间接链)。修复后 .as 布局变更仍安全,但已产出的陈旧包需一次 -fullcook 清理。详见 MainDev 仓库 ClaudeTasks/Cook/IncrementalCook_ASParentBlindspot.md。
- chunk 分配:`FinalizeChunkIDs` 逐包回调自研 `FPLChunkPackImpl`(GASExtendedPL/ChunkPack)。**已优化(CL 116039)**:旧实现逐包递归遍历传递引用者(477s);新实现 Init 时全图"祖先 chunk 集合"不动点传播 + O(1) 查询(5.6s,85×),开关 `use_fast_chunk_resolve`(chunk_rule_config.json,默认 true),Uninit 打印 `Perf:` 统计行。旧算法 multiref 检测有提前 break 的顺序依赖缺陷,新算法确定化(唯一差异:1 个包 multiref→低位 chunk,更正确)。

## 失败排查(exit 25 = Error_UnknownCookFailure)

1. 日志搜 `LogBlueprint: Error:`(最常见)、`Angelscript: Error:`(启动 12s 内退出 code 3)。
2. `[AssetLog]<路径>.uasset` → TeamCityLogParserInformer.py 解析 + Feishu;`--use-cl-author` 兜底 @ CL 提交者。
3. Build Windows Package 内置 fail-fast:命中模式即杀 cook。
4. CrashSight 符号上传失败不判红(重试 3 次后 WARNING)。

## 内容检查(CIS)

- `PL_BlueprintCheck`(MainDev,整点)/ `PL_BlueprintCheckRel02`(Rel-0.2,:30),9-21 每小时,CompileAllBlueprints ~10-15 min,避开 WinBuilder1。
- `buildBlueprintCheck` 的 `failonerror="false"`:永远绿灯,**按设计仅通知**(用户确认)。

## 基线与效果(buildStageDuration 统计)

- #9139 基线:总 79.5 min(cook 35.2 / stage 9.6 / archive 14.3 / deploy 6.5 / 符号 5.8),排队 43.5 min。
- #9168(MPCook×4+增量,名单修复前):总 67.9 min,cook 23.6 min。
- 名单修复后本地:cook 16.0 min(tick 6.3 + BuildChunkManifest 8.0 + 启动);ChunkPack 优化后本地 cook ~4-8 min。
- **Archive 已移除**(2026-07-12):Windows 平台 UAT Archive 无后处理(纯单线程拷贝,源码 ArchiveCommand.Automation.cs 可证),已从 UAT 参数删除 `-archive -archivedirectory`,下游(PakSnapshot/Metadata/符号上传/Deploy)全部改读 `Saved\StagedBuilds\<平台>`;StagedBuilds 由 UAT Stage 每次自动清空重建。注意:去 Archive 必须删 `-archive` 开关本身,只去 `-archivedirectory` 会归档到默认路径。
- CI 预期:cook ~10-12 min、打包步骤 ~36 min、总 ~45 min。剩余优化:符号/Deploy/Metadata 并行化(-5~6 min)、AS 动态类 digest(二期)、cook 启动耗时。

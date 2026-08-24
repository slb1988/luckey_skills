# TeamCity 构建失败排障

> 从 SKILL.md 移出。TeamCity 服务自身的行为陷阱见 [gotchas.md](gotchas.md)。

UE 构建报 `A conflicting instance of Global\UnrealBuildTool_Mutex_<hash> is already running`（UBT 退出码 ConflictingInstance）时：mutex hash 对应**引擎根目录**，含义是同机有另一个 UBT 实例在对同一引擎目录工作，冲突方不一定是 TeamCity 任务。排查顺序：(1) 每台构建机只有一个 agent，用 REST API 查该 agent 在撞锁时间窗内的所有 build（见 rest-api.md）排除 TC 内部冲突；(2) 若 TC 侧无并发 build，元凶在 TC 之外——最常见是有人在这台机器上开着 UnrealEditor+Live Coding 或 UGS 客户端自动编译，P4 sync 落地文件变更会触发它（特征：撞锁总发生在 sync 完成后几秒内）；(3) 上机看 `<EngineRoot>\Engine\Programs\UnrealBuildTool\Log.txt` 拿冲突方的完整命令行和启动时间，或用 Sysinternals `handle64.exe -a UnrealBuildTool_Mutex`（管理员）循环抓持锁进程。缓解：UBT 撞锁几乎秒失败（~0.3s）但持锁方常只占几秒，在 build 脚本里对 ConflictingInstance 加 sleep 30s 重试 3~5 次即可自愈。

## PLN_TaskBuildUELinux "莫名全量重编"（2026-08-24，构建 #179/#189；08-25 #200 复发）

现象：CL 变动很小（如 126065→126079 纯 uasset/文档），构建却突然全量重编引擎 4500+ actions。拆解方法：下载日志（`/downloadBuildLog.html?buildId=<id>`）grep `Invalidating makefile|Creating makefile|to run N action`，UBT 会直接给出失效原因。该配置的真实机制（脚本印在构建日志 Step 2 开头）：

- **两条链共用同一工作区** `DefaultAgent_MainDev`：日常链（CodeGraph, `env.unshelve=0`）和评审链（AiReview, `env.unshelve=<shelfCL>`），上游都是 `PLN_TaskUnshelve`（只做 `p4 revert //...` + unshelve，**不 sync 到指定 CL**）。
- **日常链有 marker 短路**：`<workspace>/Saved/Build.version` 存在就跳过 `Build.sh UnrealEditor`，只编 ProjectLungfishEditor target。
- **评审链强制引擎构建**（脚本注释自己写明：shelved CL 可能含 Engine/ 改动，marker 短路会漏检）→ 每次评审必然跑 UBT UnrealEditor target。

由此产生三类"重编"：
1. **评审链全量 = 设计行为 + 挂账引爆**。日常链 marker 把 Build.cs/uplugin 变更需要的引擎全量一直挂账；评审链是变更后第一个 UnrealEditor target 构建，UBT 报 `Invalidating makefile for UnrealEditor (SharedDefinitions.Engine.Cpp20.h modified)` → 全量 4571 actions。与被评审的 shelf 内容无关（shelf 125931 纯 docs 也照样全量）。**已验证会随每次规则级提交复发**：#189 引爆的是 126003（15:57 CommonGame 插件依赖重构）；#200（08-25 00:06）引爆的是 126162（22:35 Engine Core DirectStorage cpp）+126170（23:00 PLEngineExtended.Build.cs+新源文件），期间日常链 #199 只编了项目 target（`source file added` → 995 actions），引擎账照旧留给评审链。
2. **日常链项目增量**（1019/995/608 actions 级）：`Invalidating makefile for ProjectLungfishEditor (XXX.Build.cs modified)`、`(source file added)` 或纯源文件增量——查该构建 sync 窗口内的 CL 即可对上（`p4 -C none files "//depot/path/...@cl1,cl2" | grep -E '\.(cpp|h|cs|uplugin)'`）。
3. **`Creating makefile for UnrealEditor (Build.version is newer)`**：引擎 makefile 比 `Engine/Build/Build.version` 本地 mtime 旧 → 全新 makefile → 全量。depot 里该文件长期不变（rev#15 @121188），mtime 变新说明本地被重写（强制/全量重拉、清理事故恢复等）。

注意区分两个同名文件：脚本 marker 是 `<workspace>/Saved/Build.version`；UBT 追踪的是 `Engine/Build/Build.version`。

改进方向：(a) Task_Unshelve 检查 shelf 文件列表，无 `Engine/`、`Source/`、`*.Build.cs`、`*.uplugin`、`*.Target.cs` 时对下游传 unshelve=0，docs-only shelf 不白编引擎；(b) 日常链 sync 后检查本段 CL 含上述构建规则文件时主动删 marker，避免挂账。

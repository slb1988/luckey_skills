# TeamCity 构建失败排障

> 从 SKILL.md 移出。TeamCity 服务自身的行为陷阱见 [gotchas.md](gotchas.md)。

UE 构建报 `A conflicting instance of Global\UnrealBuildTool_Mutex_<hash> is already running`（UBT 退出码 ConflictingInstance）时：mutex hash 对应**引擎根目录**，含义是同机有另一个 UBT 实例在对同一引擎目录工作，冲突方不一定是 TeamCity 任务。排查顺序：(1) 每台构建机只有一个 agent，用 REST API 查该 agent 在撞锁时间窗内的所有 build（见 rest-api.md）排除 TC 内部冲突；(2) 若 TC 侧无并发 build，元凶在 TC 之外——最常见是有人在这台机器上开着 UnrealEditor+Live Coding 或 UGS 客户端自动编译，P4 sync 落地文件变更会触发它（特征：撞锁总发生在 sync 完成后几秒内）；(3) 上机看 `<EngineRoot>\Engine\Programs\UnrealBuildTool\Log.txt` 拿冲突方的完整命令行和启动时间，或用 Sysinternals `handle64.exe -a UnrealBuildTool_Mutex`（管理员）循环抓持锁进程。缓解：UBT 撞锁几乎秒失败（~0.3s）但持锁方常只占几秒，在 build 脚本里对 ConflictingInstance 加 sleep 30s 重试 3~5 次即可自愈。

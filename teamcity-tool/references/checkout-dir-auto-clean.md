# Checkout 目录自动清理误删工作区事故（2026-08-19,E:\WinBuilder3_MainDev 被整树删除）

> 关联:[gotchas.md](gotchas.md) 的「Checkout directory 过期自动清理」条目;PL 侧镜像知识在 `D:\MainDev\.claude\skills\teamcity-package-pipeline\SKILL.md`。

## 姊妹清理器：DirectoryMapUnknownCleaner（2026-09-04 auto-server 实例）

与 192h 孤儿过期清理（DirectoryMapDirectoriesCleanerImpl）**不同**的另一个 cleaner：

- **触发**：每次构建启动准备时（agent 重启后也会）扫描 `work/` 下**未登记进 `work/directory.map`** 的子目录，当即当作无主垃圾 `Move directory ... to work/.old/xxx` 并异步物理删除——**没有 192h 宽限，发现即清**。
- **日志特征**：`DirectoryMapUnknownCleaner - Checking not listed in directory.map folder <dir>` + `DirectoryCleanerImpl - Move directory <dir> to .../work/.old/<dir>_N for cleaning`。
- **登记时机**：任何带 custom `checkoutDir` 的配置（**MANUAL 模式也会登记**）在该 agent 上启动构建时，目录名进 `work/directory.map`（纯文本，条目形如 `bt133=PLNew::Task_AiReview -> DefaultAgent_Stable |?| <时间> |:| never`）；`system/checkoutdir-revisions/<dir>.xml` 只在真正执行 VCS checkout 时写。
- **竞态窗口**：评审/同步链若在 work/ 下新建 P4 client Root（如 P4SyncWorkspace.py 新建 `{agent}_{stream}`），而链上前置配置（Sync/Unshelve）不带该 checkoutDir——新目录在「创建」到「链中某个带 checkoutDir 的配置启动登记」之间的窗口内，会被链自己后续构建的启动扫描清掉（Stable 首评实测：53min 全量同步完稿后 2 分钟内被连清两次）。
- **结论性建议**：P4 长驻工作区**不要放在 agent work/ 下**（挪到如 `/mnt/disk2/TeamCity/p4ws/`）；必须放的话，链首加一个带该 checkoutDir 的空 registrar 配置把登记提前。

## 机制(DirectoryMapDirectoriesCleanerImpl)

- 任何曾被 buildType 登记为 **custom checkout directory** 的目录,都会进入 agent 的 directory map(agent system 目录下持久化)。
- 当属主配置**移除 checkoutDir / 被删除 / 停止在该 agent 上运行**后,条目成为孤儿;距最后一次使用超过 `teamcity.agent.checkoutDir.expireHours`(默认 **192h**)即被 agent 后台清理线程整树 `rd /s /q`。
- 触发与磁盘余量**无关**(事故时还剩 1.55TB);agent 日志特征行:
  `DirectoryMapDirectoriesCleanerImpl - Deleting <dir>. Build directory has expired, unused or free disk space is needed`
- 删除在 P4 之外发生 → **服务器 have-table 仍认为 client 拥有全部文件** → 裸 `p4 sync` 只拉 CL delta 秒过,磁盘依然是残的。
- 删除时被进程占用(coreclr.dll / UE DLL 报 Access denied)会删不干净,留下 `<dir>\.teamcity.clean.checkout.required` 标记 → 下次清理周期**强制重清**。
- agent 自升级会重写 directory map 时间戳 → **升级后约一周是高危窗口**(2026-08-11 18:49 升级 → 08-19 晚集中爆发)。

## 事故时间线(全部有日志实锤)

| 时间 | 事件 | 证据 |
|---|---|---|
| 7/30 | PLN `Task_Sync_CyanCookDepot` kts rev#1 创建,带 `checkoutDir`(rev#1-#6 都有) | `//depot/Teamcity_PLN/.teamcity/patches/buildTypes/TaskSyncCyanCookDepot.kts` filelog |
| 8/11 CL1129 | rev#6 把 checkoutDir 改为 `%P4SyncRoot%/%teamcity.agent.name%_%P4Stream%`(注释明写 "Windows flows override via reverse.dep.*.P4SyncRoot") | p4 diff2 #5 #6 |
| **8/11 23:05** | **build #213 (id 12193) 在 WinBuilder3 运行,TeamCity 以 `E:\WinBuilder3_MainDev` 为 checkout dir 做 agent-side checkout(`p4 sync -f` 拉了 2h40m)** → 登记进 directory map | build 12193 日志 "Checkout directory: E:\WinBuilder3_MainDev" |
| 8/12 06:30 | build #216 (id 12207) 在 **WinBuilder1** 以 `E:\WinBuilder1_MainDev` 为 checkout dir 跑了一次(冲掉 client Root、sync -f 4h;Root 后已改回 `F:\WinBuilder1_MainDev`) | build 12207 日志 |
| 8/12 16:15 CL1135 | rev#7 移除 checkoutDir、改脚本 sync(P4SyncWorkspace.py 复用 client 已记录的 Root)——修法正确,但 map 条目成孤儿 | p4 describe 1135 |
| 8/19 21:33 | sunlaibing 在 UI 编辑该配置(rev#9,只删注释/禁步骤,与事故无因果) | audit `build_type_edit_settings` |
| **8/19 23:09:14** | **192h 到期(与 #213 运行时间分钟级吻合),cleaner 整树删除 `E:\WinBuilder3_MainDev`**;因文件占用未删净,留 marker;23:16:51 删除 map 配置文件 `8d165dfb_WinBuilder3_MainDev.xml` | teamcity-agent.log |
| 8/19 23:09-23:27 | cyancook 自动触发链(每新 CL 一次)连续拉起 PL_BuildUgsBinaries #5141/#5142/#5143,**三连红**:Step10 Build UE 的 RunUAT.bat 不存在(PowerShell 吞错 exit 0),Step12 Upload to Minio 报 "Source directory does not exist: ...\LocalBuilds\ArchiveForUGS\Staging" | builds 13456/13465/13478 |

## 排查方法论(可复用)

1. 下载失败构建与上一个成功构建的完整日志:`/downloadBuildLog.html?buildId=<id>`,逐步骤对比(17 步里 Step10/11 的 "not recognized" 是关键)。
2. 看 sync 步骤输出:只有 CL delta(#added/#updated/#deleted 几十个文件)= have-table 完好、磁盘被绕过的铁证。
3. 查同 agent 时间窗内所有构建:`/app/rest/builds?locator=agent:id:<N>,finishDate:(...)`。
4. Kotlin 版本化设置**逐项目树** grep `checkoutDir`/`checkoutDirectory`(PL 树 `//depot/Teamcity/.teamcity` 干净,PLN 树 `//depot/Teamcity_PLN/.teamcity` 命中)——注意 `p4 grep` 只搜 head,追历史要 `p4 filelog` + `p4 print -q file#rev` 逐版本看。
5. REST audit(`/app/rest/audit`)保留窗口有限(~5000 条),8 天前的配置变更已查不到。

## 恢复

```bash
# 磁盘残缺 + have-table 完好时,裸 sync 无效,必须:
p4 -c <client> clean <root>\...   # 校验差异只补缺失,远比 sync -f 全量快
# 注意:clean 会删除 depot 之外的本地多余文件
```

`Saved/`、`Intermediate/`、`LocalBuilds/`、`.vs/` 等本地产物不可恢复(rd /s /q 不过回收站)。

## 防复发清单

1. **游戏工作区路径永不登记为 checkout directory**;必须用 checkoutDir 的配置,加 `requirements { matches("teamcity.agent.name", ...) }` 钉死 agent。
2. 每台构建机 `buildAgent.properties` 设 `teamcity.agent.checkoutDir.expireHours=never` 并重启 agent(低磁盘清理由 `freeSpaceMb` 单独控制,不受影响)。
3. 发现清理日志后:删 `<工作区根>\.teamcity.clean.checkout.required` 残留标记 + agent system 目录下 directory map 陈旧条目,否则强制重清。
4. agent 升级后一周内,主动检查 directory map 里所有指向真实工作区的条目。

## 遗留风险(事故当日盘点)

- **WinBuilder1** 的 `E:\WinBuilder1_MainDev` 孤儿条目 8/20 06:30 到期(8/12 06:30 build #216 登记);该目录是孤儿副本,真工作区在 `F:\WinBuilder1_MainDev`,清理不伤数据但会留脏标记。
- PLN 的 `TaskBuildCodeGraph` / `TaskBuildUELinux` / `TaskPrintP4Ignore` 仍有 `checkoutDir=/mnt/disk2/...` 且**无 requirements 块**——被单独触发到 Windows agent 会再登记垃圾目录;配置日后改名/删除,Linux DefaultAgent 的真工作区 `/mnt/disk2/.../DefaultAgent_MainDev` 会重演同样的 192h 孤儿清理。
- PL_BuildUgsBinaries Step10(Build UE)/Step11(AS Compile Check)的 PowerShell 吞错(RunUAT.bat 不存在也 exit 0),只有 Step12 兜底——若 Staging 有残留会以陈旧产物**绿灯**发布。需加 Test-Path 前置守卫 + fail-fast。

# PLN_FlowAiReview：当前拓扑与历史性能画像

## 当前 Windows Win64 链（2026-09-08 配置契约）

`PLN_TaskSyncCyanCookDepot → PLN_TaskUnshelve → PLN_TaskBuildUEWindows → PLN_TaskAiReview`，
由 composite `PLN_FlowAiReview` 发起。业务参数由 Flow 统一下发；路径在实际 Agent 上解析。
Windows/WinBuilder 要求放在专属节点，不需要 Linux 交叉工具链变量；共享 Sync/Unshelve 仍服务其他链。
参数配对、同机组、工作区公式、排障与验收统一见 [build-chain-parameters.md](build-chain-parameters.md)。

## 历史 Linux 链耗时基线（2026-08-31，14 次构建采样）

以下耗时和 Linux/p4ws 现场属于历史方案，不作为当前 Windows 链的配置指令。
REST 读取当前链仍需从具体 Flow 递归展开 snapshot dependencies，而不是只看直接依赖。

| 环节 | 典型耗时 | 性质 |
|---|---|---|
| 排队 | 0~4+ min | 单 Linux agent 串行，见下 |
| Sync Depot | 63~93s | 恒定开销：p4 sync 全量 have-list 扫描；`p4 sync --parallel=threads=4` 约省一半 |
| Unshelve | ~12s | 可忽略 |
| BuildUE_Linux | 增量 12~48s | 57min 全量重编只出现在 2026-08-24/25（跨链 UBT makefile 互爆，脚本内修复已生效）；再出现 57min 级别耗时可判定为该问题复发 |
| AiReview | 77s~20min | **99% 是 `Pi_Agent_Review` 单步**（LLM 评审），其余步骤全部 <1s |

## Pi_Agent_Review 步的非显性特征

- 评审时长**与 diff 大小不相关**（0.8KB diff 审 321s，157KB 的反而 126s）；耗时由 turn 数和 thinking 深度驱动。
- `thinking_level=high` 下每个 LLM 往返 20~30s，验证性 grep/read 也会产出上万字符思考；上下文随 turn 单调膨胀（实测 15K→245K tokens，末 turn cacheRead 237K），越跑越慢。单次评审成本约 $10。
- pi CLI 支持 `--thinking low`，大部分 turn 只是验证性工具调用，降档预计砍 40~60% 时长（评审质量需 A/B 对比几次再定）。
- 每次评审必读 `.claude/skills/pl-review/SKILL.md`，内联进 prompt.md 可省固定 1~2 个 turn 和首轮 context。
- pi session 文件在 agent workspace 的 `sessions/` 下无限累积，且**每次构建全量上传 artifact**——分析评审过程时直接去 workspace 拿 session JSONL 比翻 TC artifact 快。
- 评审步的 pi CLI 以 **`--no-extensions` 显式启动**——只往构建机复制 pi 扩展文件（如 memory-hub 首轮预热扩展）不会被加载，必须同步改该步启动参数做显式加载；且构建机上的 memory_hook 客户端版本偏旧，没有 search-v2 召回入口，接记忆召回时客户端也要一并升级。
- 历史 Linux 部署的 agent-home `p4ws/` 下有 `DefaultAgent_MainDev` 与 `DefaultAgent_Stable`。当时按目录定 memory-hub project，前者=maindev，后者错挂 auto-server；两条流同属 maindev。此路径不是当前 Windows AI Review 的 Root 公式。

## Pi_Agent_Review 耗时黑洞：裸 grep 全树扫 P4 工作区（2026-09 Windows 链，build 18454 实锤）

Windows 链评审时长呈**双峰分布**：快档 1~6 min（模型全程用带 path 的 find/grep，如 18474 全程 88s），慢档 9~30 min。快慢与 LLM/网关无关（LLM 首响应 5.7s，build-api-proxy 在评审窗口零留痕），瓶颈全在模型首个**无 path 限定的裸 grep/find**：

- **机理**：pi 的 grep 走自带 ripgrep；评审 workspace 是 P4 检出，没有 `.git`/`.ignore`，rg 不应用任何忽略规则 → 全量扫 UE 树（含 Intermediate/Binaries 几十万文件）。冷缓存 + Defender 下 7~30 min，热缓存秒级——所以快慢随机。build 18454 实测首个裸 grep 执行 441.5s，占该 build 评审步 10m05s 的大头。
- **整 30 min 的 build（18417/18404）= 裸 grep 卡满步骤 1800s taskkill**，verdict=error 白跑——看到 30:00 整 + error 先怀疑这个，别怀疑模型。
- **修复已落地（2026-09-08）**：评审步 kts `--tools read,grep,find,ls` 收窄为 `read,ls` 物理断搜（CL 1562）+ `AiReviewContextCollect.py` prompt 同步改写禁搜索（CL 130007）——**两处必须同时生效**，否则 prompt 声称有 grep 而工具没有，模型报错浪费轮次。下一步方向是 Collect 步预生成 `codegraph_context.txt`（diff 符号批量过 web codegraph `/callers`+`/impact`），但 web 版 codegraph 当前全挂（1004 = 服务端缺 codegraph CLI 二进制，根因见 codegraph skill），修好前按不可用降级。

## 排队瓶颈与多 agent 历史方案（2026-09-07 CL 1499，非当前部署状态）

在该历史方案中，`DefaultAgent` 是唯一 Linux agent，AiReview 链与 CodeGraph 链共享它，串行执行。
review 步是 LLM/IO 等待型（编译才吃 CPU），**同机加第二个 agent 即可消除串行**；
workspace 命名 `{agent}_{stream}` 原生支持多 agent 共存。

**CL 1499 历史多 agent 方案**：Flow 级 `DefaultAgent` 参数改为锚定正则
`^(?:DefaultAgent|WinBuilder3|WinBuilder4)$`（经 `override.dep.*` 下发），链可调度到
WinBuilder3/4（Windows 11 + 同款 v26 Linux 交叉工具链 `env.LINUX_MULTIARCH_ROOT`，用
Build.bat 编 Linux target，门禁语义不变）。要点：

- bash 步骤全部改为 python-runner 内联脚本（Verify Client Root / Build UE / Pi Agent Review /
  两个 Log Analysis Notification）；`|| true` 在 cmd 下无效，全部改为步骤内吞错。
- pi 评审步：prompt 以 `@Saved/ai_review/prompt.md` @file 传参（cmd 8191 上限 + 重解析风险），
  1800s 超时杀进程树（Windows taskkill /F /T，POSIX killpg）。
- WinBuilder3/4 上 `{agent}_{stream}` client 是 DryRun 链时代建的（Root 在 E:/D: 独立盘），
  与 agent-home p4ws 硬编码不符——TaskBuildUELinux/TaskAiReview 首步 Resolve_Workspace_Root
  从 client spec 实时解析真实 Root 写 env.WORKSPACE_ROOT，后续步骤跟随（DefaultAgent 上
  Root==checkoutDir 行为等价）。
- 能力门按调用范围落在专属节点，不能全局收窄共享 Sync/Unshelve，也不能把共享 Linux 编译节点认定为 AiReview 独占；当前 Win64 链见本文开头及 chain 主参考。
- WinTest1 也带 LINUX_MULTIARCH_ROOT，靠 name regex 排除；WinBuilder1 无双条件满足。
- 配置级兼容性不等同于某次 Flow 的实际候选；旧 `%reverse.dep.*.X|...%` 表达式不能视为通用 fallback。验证应查具体 queued build、单节点隐式要求、同机组交集及实际启动参数，而不是仅手算名称/工具链条件。
- 历史上线检查：当时 WinBuilder3 的 pi provider 与 WinBuilder4 的启用/安装状态未验证完整。当前机器状态必须现场查询，不能用这份历史清单判断现在的可用 Agent；匹配通过后仍需验证 runner 与 pi 模型配置。

## 后端 busy 门、降级放行与取消归属（2026-09-09 review 197 事故确认）

以下均为 auto-server 后端行为，排查「评审不动 / 评审乱放行」时先对这几条：

- **分支串行 busy 门（静默）**：同分支已有 review 的 DB 状态为 compile running 时，新 review 被压住不入 TC 队——零活动记录、零前端提示，用户视角就是「点了没反应」，刷新 shelve 重触发同样被拦回。注意 **DB running ≠ TC 在跑**：状态由发起时写入、靠回调翻转，链可能只是排在 TC 队列里没起跑。排查先比对该分支其他 review 的 compile_status 与其实际 TC 链状态。
- **后端永不 cancel 在途 TC 链**：看到链被 cancel，直接查 build 的 `canceledInfo.user`——一定是人（或 TC 侧），可排除后端。
- **链级 FAILURE → 降级放行缺陷（风险）**：链 FAILURE 后后端降级为「无可分析文件」分析 → risk=0 → 命中 risk≤15 自动放行分支；若代提交恰好成功，CL 将零评审直接进库（197 案例靠代提交也失败才挡住）。且该路径自动评论误写「编译验证通过」（compile skipped 被当通过）。修复方向：链级 FAILURE 禁止走自动放行分支。
- **review 打回 rejected 后无任何通知**（已知缺口）：作者不主动看 dashboard 就不知道要 reopen，是造成「等了几小时」体感的放大器。
- **卡死链的自愈预算**：`_poll_compile` 的 TC 等待预算 = `COMPILE_TC_TIMEOUT_POLLS`（默认 180，config/env 可调）× 60s tick ≈ 3h 才超时降级为静态分析；busy 门 fresh 窗口 4h——链卡死又不人工取消时，同分支最长被压 ~3h。
- **纯二进制资产单默认不跑 TC 链**（`_chain_skippable`）：文件全是不可分析二进制时直落静态分析；若看到二进制单仍触发了链，说明命中 force_ai 路径规则或计数一致性校验 fail-closed（权威口径见 pyAutomation `backend/server/applications/ai_review/SKILL.md`）。
- **时间戳口径**：后端 activities/DB 是 UTC，TC REST 是 +0800，跨系统对时间线先换算再对齐。

### busy 门的设计根因、取单公平性与前端可见性（2026-09-08 review 257 积压排查确认）

- **为什么必须有 busy 门：TC 队列不提供链级互斥**。AI 评审链是 4 个独立 build config（Sync→Unshelve→BuildUE→AiReview）共享同一 `{agent}_{stream}` workspace；TC 只保证单 agent 一次一个 build。若无后端门，同分支两条链节点可交错（SyncA→SyncB→UnshelveA→UnshelveB）：UnshelveB 把 CL-B 落进链 A 正在编译/评审的树 → 评错 diff、verdict 失真；且链尾 ALWAYS Cleanup 会把另一条链跑到一半的 unshelve 直接 revert 掉。busy 门就是用 DB 状态补 TC 缺失的链级互斥锁（代码内 R6 fence 注释实锤该风险）。**同分支「排队」是设计内行为**：突发积压（实测 ~20 单）时按每链 3~15min 逐单消化，不是卡死。
- **饿死修复已上线（#241）**：ticker 取单 limit 50 + busy 让位 120s 退避 + 公平排序；终态 review 不参与阻塞（#93 僵尸修复），配合上文 fresh 4h 自愈窗口。
- **排队态前端可见**（修正上文「零前端提示」口径）：详情页 `aiQueue.blocked_by.review_id` 驱动「等待 Review #N 的评审链完成（TC 构建）」文案；「零提示」仅指被压住时不产生 activities 记录。

## Unshelve 独占锁失败模式

`can't edit exclusive file already opened`（Unshelve 步秒级失败 → 整链 FAILURE）= 作者本机 client 把 +l 独占文件（典型 uasset）开着。归因：看失败文件 + `p4 opened -a <file>` 查谁持有打开锁。与编译失败归因分开看——这发生在链最前段，Compile 步根本没跑。

## 队列停摆：全 server 零构建但排队链不起（2026-09-09 观测，根因未实锤）

历史症状：跨所有 agent `running:true` 返回空、Agent 在线空闲，排队链长期不起，重建链后恢复；当时同时出现 `not read only` 设置选择日志，因果关系未确认。
该日志不能单独说明 UI 编辑或缓存导致无匹配；先核实具体构建的兼容性、参数与 revision，再按 chain 主参考决定是否安全重排，不把“重跑恢复”当成根因证明。

## 已确认的其他问题

- 同一 CL 会被完整重审（观测到 127675×2、127683×2、125931×4），无按 CL+编译结果哈希的评审缓存。
- 结果发布回调步带 `|| true`，回调失败被吞掉时提交方永远等不到结果——用户报"评审卡住/慢"时先查这一步。

## 编译失败归因与 sync/reset 机制（2026-09-03 确认）

- **Sync 的是 MainDev 最新 HEAD，不是被审 CL 的基线** → 主干坏窗口内所有评审都会被别人的坏 CL 误伤。案例：CL 128884（19:34 提交，unity 撞名）到 19:51 才被 128897 修复，窗口内 review 104 编译失败，报错文件与该 CL 无关。**归因方法：编译报错文件清单 ∩ 评审 CL 文件清单 = ∅ → 基线已坏/非本 CL 引入**，不硬卡作者，应告警基线破坏者（飞书通知链路已有 blame 能力，只缺接进评审定案）。
- **Workspace 重置机制存在且工作正常**，不存在跨评审残留"串台"：`P4UnshelveStage.py` 在 unshelve 前跑 `p4 revert -w //...`；`Task_AiReview` 链尾有 ALWAYS 执行的 Cleanup `p4 -c {agent}_{stream} revert -w //... || true`（与 Windows 链 revertClient 同纪律）。revert 管不了已提交进 depot 主干的坏文件——报错文件是 sync 正常拉下来的。

### UBT adaptive unity 盲区（评审链特有）

UBT 按 `ISourceFileWorkingSet`（本地修改/可写文件）把 unshelve 进来的文件踢出 unity 单独编译，日志标志 `[Adaptive Build] Excluded from <Module> unity file: xxx.cpp`。
后果：**新增 .cpp 引入的 unity 撞名在作者自己的评审里天然测不出**——新文件被单独编译，匿名 namespace 按 TU 隔离不撞；文件提交进 depot 变只读后进入 unity blob，在**下一个人**的评审编译时才爆（典型：兄弟规则文件从彼此复制匿名 namespace 助手块且裸名相同，unity 合并后 redefinition）。修复惯例是名字加模块前缀。编译失败且报错文件与评审 CL 无交集时先怀疑这个；要堵住可在 BuildUE 步对新增 .cpp 所在模块强制非 unity 编译（代价是变慢）。

### 已知小 bug

- Dashboard `编译错误数: 0`：`_analyze_compile_errors()`（auto-server 后端）靠正则 `提取到 **(\d+)** 条` 从日志分析报告抠数字，匹配不上就落 0——实际有错误时飞书通知里的数字是对的，只是 dashboard 归因展示少数字。

### 链失败归因全链路盲区（2026-09-09 review 281 实证根因）

- `_poll_compile` 只认「BuildUE 步骤 SUCCESS」：Sync/Unshelve 失败时一律记 `compile_status=failed`，不带失败阶段信息。
- `_analyze_compile_errors` 的分析对象是 **composite Flow 日志**（仅链 bookkeeping，~69 行），不是失败步骤（BuildUE/Unshelve）自己的日志 → 必然「提取到 0 条」。抽查全部历史 `failed` 单 `compile_error_count` 均为 0，含真·编译失败单（BuildUE 日志里一堆 clang error 的 #57）——**后端这条分析路一直全瞎**，只有 TC 侧 informer 飞书卡数字是对的。与上文「已知小 bug」是两层缺陷：那层是报告数字正则抠不出，这层是分析对象本身就是错的日志。
- 后果链：unshelve 独占锁失败 → 前端 tag 误显示「编译失败 ✗」→ AI compile_context 拿到 Flow bookkeeping 废话 → 分析提不到真实原因，必须人翻 TC 日志。
- 定位链根因失败步骤：沿 snapshot deps 递归展开，排除显示 `Snapshot dependency failed` 的级联步骤，第一个自己跑挂的步骤即根因。
- 修复方案（ws:autoserver-deveops，未实施）：`.claude/plans/AiReview链失败归因上屏.md`——`_classify_chain_failure` 按 stage 分派日志源、归因结构落 `compile_result['chain_failure']`、前端 tag+失败步骤直链；语义上 unshelve 失败仍记 `failed` 保持批准门禁阻断。

### 新流首次评审：UnknownCleaner 清工作区 + 工具脚本缺失（2026-09-04 review 157 实例，9/5 查清）

- **触发条件**：某条流**史上第一次**发起 AI 评审（review 157 / CL 129252 是 Stable 流首评）。Sync 阶段新建 P4 client `{agent}_{stream}` 并全量同步（Stable 0→126068 跑了 53min，同步本身成功）。
- **主因（结构性，会复发）**：工作区内容在评审步开始前被 **TC agent 的 DirectoryMapUnknownCleaner 整树清掉**。该 cleaner 在**每个构建启动准备时**扫描 agent `work/` 下未登记进 `work/directory.map` 的目录，当无主垃圾 move 到 `work/.old/` 随后物理删除（日志特征：`Checking not listed in directory.map folder ...` + `Move directory ... to .../work/.old/...`）。链上 Sync/Unshelve 配置**无 checkoutDir**（跑在 hashed 目录），登记只发生在带 `checkoutDir=work/%agent%_%P4Stream%` 的 TaskBuildUELinux/Task_AiReview（MANUAL 模式也会登记）**启动那一刻**——于是新工作区在 Sync 完稿后、登记前的窗口里被链自己的 Unshelve/BuildUE 构建启动扫描连清两次（20:08:41/20:08:51，日志实锤），AiReview 步面对的是空目录。MainDev 不出事是因为早已登记且天天被用。**每条新流的首评都会踩这个窗口**。
- **次因（已被 CL 129362 修复）**：`Task_AiReview` 是 `checkoutMode=MANUAL` + 不挂 VCS root，`Collect Review Context` 跑 `python Tools/AiReview/AiReviewContextCollect.py` 依赖脚本随 UE 流 sync 进工作区；当时 `Tools/AiReview/` 只在 MainDev 流，Stable HEAD（126068）没有 → 即使没被清也会报 `Errno 2` exit 2。9/5 CL 129362 已把工具合入 Stable。新流首评前确认该流含 `Tools/AiReview/`。
- **次生症状**：`Validate And Publish Result` 步被跳过 → 回调永远不发 → 后端 review 记录 `compile_status=running` 卡死（dashboard 一直转圈）。查评审卡住先对 `compile_build_url` 的链状态。
- **清理后现场**：磁盘空目录 + P4 have-table 满（up-to-date 假象）——裸重跑 sync 只拉 delta 秒过、工作区 99% 缺失。恢复必须 `p4 -c {agent}_{stream} clean //CyanCookOfficialDepot/<stream>/...` 或 sync -f 全量补回（.old 会被 cleaner 第二阶段 purge，无法从 .old 抢救）。
- **当时的 Linux 部署方案（见 `.claude/plans/评审工作区迁出TC-work目录.md`；当前 Windows Root 另按 NODE_WORKSPACE 契约）**：工作区基座从 agent `work/` 挪到 **`%teamcity.agent.home.dir%/p4ws/`**（CL 1481+1482）：UnknownCleaner 只扫 work/，agent home 级目录安全（先例：buildAgent/devops）；agent-home 相对路径使多 agent / Windows 扩展不用改配置。改动点：`Teamcity_PLN/.teamcity/patches/buildTypes/` 的 TaskSyncCyanCookDepot.kts `P4SyncRoot` + TaskAiReview/TaskBuildUELinux/TaskBuildCodeGraph/TaskPrintP4Ignore/TaskSyncStreamDepot 五个 checkoutDir。存量 client 迁移：`mv` 目录 + 改 client spec Root 即可（have-table 存的是 depot 路径映射，与本地绝对路径无关，`p4 sync -n` 可验证无损）。另加 `teamcity.agent.checkoutDir.expireHours=never` 防 192h 过期清理误伤低频流。
- **业务入口契约**：非默认分支/CL 从 `PLN_FlowAiReview` 发起。独立 Task 的默认入口、名称策略与自定义业务参数透传是不同契约，不能相互推断；完整验证要求见 chain 主参考。

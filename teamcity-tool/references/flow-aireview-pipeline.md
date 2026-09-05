# PLN_FlowAiReview 管线性能画像（2026-08-31 基线，14 次构建采样）

AI Review 复合链：`PLN_SyncDepot → PLN_Unshelve → PLN_BuildUE_Linux → PLN_AiReview`（pi agent 评审）。
REST API 查复合构建只返回直接 snapshot 依赖，**要递归追踪** `snapshot-dependencies` 才能拿到完整链路。

## 各环节耗时基线

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

## 排队瓶颈

`DefaultAgent` 是唯一 Linux agent，AiReview 链与 CodeGraph 链共享它，串行执行。
review 步是 LLM/IO 等待型（编译才吃 CPU），**同机加第二个 agent 即可消除串行**；
workspace 命名 `{agent}_{stream}` 原生支持多 agent 共存。

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

### 新流首次评审：UnknownCleaner 清工作区 + 工具脚本缺失（2026-09-04 review 157 实例，9/5 查清）

- **触发条件**：某条流**史上第一次**发起 AI 评审（review 157 / CL 129252 是 Stable 流首评）。Sync 阶段新建 P4 client `{agent}_{stream}` 并全量同步（Stable 0→126068 跑了 53min，同步本身成功）。
- **主因（结构性，会复发）**：工作区内容在评审步开始前被 **TC agent 的 DirectoryMapUnknownCleaner 整树清掉**。该 cleaner 在**每个构建启动准备时**扫描 agent `work/` 下未登记进 `work/directory.map` 的目录，当无主垃圾 move 到 `work/.old/` 随后物理删除（日志特征：`Checking not listed in directory.map folder ...` + `Move directory ... to .../work/.old/...`）。链上 Sync/Unshelve 配置**无 checkoutDir**（跑在 hashed 目录），登记只发生在带 `checkoutDir=work/%agent%_%P4Stream%` 的 TaskBuildUELinux/Task_AiReview（MANUAL 模式也会登记）**启动那一刻**——于是新工作区在 Sync 完稿后、登记前的窗口里被链自己的 Unshelve/BuildUE 构建启动扫描连清两次（20:08:41/20:08:51，日志实锤），AiReview 步面对的是空目录。MainDev 不出事是因为早已登记且天天被用。**每条新流的首评都会踩这个窗口**。
- **次因（已被 CL 129362 修复）**：`Task_AiReview` 是 `checkoutMode=MANUAL` + 不挂 VCS root，`Collect Review Context` 跑 `python Tools/AiReview/AiReviewContextCollect.py` 依赖脚本随 UE 流 sync 进工作区；当时 `Tools/AiReview/` 只在 MainDev 流，Stable HEAD（126068）没有 → 即使没被清也会报 `Errno 2` exit 2。9/5 CL 129362 已把工具合入 Stable。新流首评前确认该流含 `Tools/AiReview/`。
- **次生症状**：`Validate And Publish Result` 步被跳过 → 回调永远不发 → 后端 review 记录 `compile_status=running` 卡死（dashboard 一直转圈）。查评审卡住先对 `compile_build_url` 的链状态。
- **清理后现场**：磁盘空目录 + P4 have-table 满（up-to-date 假象）——裸重跑 sync 只拉 delta 秒过、工作区 99% 缺失。恢复必须 `p4 -c {agent}_{stream} clean //CyanCookOfficialDepot/<stream>/...` 或 sync -f 全量补回（.old 会被 cleaner 第二阶段 purge，无法从 .old 抢救）。
- **根治方向（已实施，见 `.claude/plans/评审工作区迁出TC-work目录.md`）**：工作区基座从 agent `work/` 挪到 **`%teamcity.agent.home.dir%/p4ws/`**（CL 1481+1482）：UnknownCleaner 只扫 work/，agent home 级目录安全（先例：buildAgent/devops）；agent-home 相对路径使多 agent / Windows 扩展不用改配置。改动点：`Teamcity_PLN/.teamcity/patches/buildTypes/` 的 TaskSyncCyanCookDepot.kts `P4SyncRoot` + TaskAiReview/TaskBuildUELinux/TaskBuildCodeGraph/TaskPrintP4Ignore/TaskSyncStreamDepot 五个 checkoutDir。存量 client 迁移：`mv` 目录 + 改 client spec Root 即可（have-table 存的是 depot 路径映射，与本地绝对路径无关，`p4 sync -n` 可验证无损）。另加 `teamcity.agent.checkoutDir.expireHours=never` 防 192h 过期清理误伤低频流。
- **运维备注**：Task 级配置（Sync/Unshelve/BuildUE/AiReview）**不能脱离复合配置单独触发**——`DefaultAgent` 参数靠复合配置经 `override.dep.*` 下发，standalone 触发会卡在 `%reverse.dep.*.DefaultAgent|DefaultAgent%` 未解析 → "no idle compatible agents"。要手动验证一律触发复合配置 PLN_FlowAiReview。

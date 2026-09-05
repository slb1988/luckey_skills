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

### 新流首次评审：工具脚本缺失 + 回调缺席卡死（2026-09-04 review 157 实例）

- **触发条件**：某条流**史上第一次**发起 AI 评审（review 157 / CL 129252 是 Stable 流首评）。Sync 阶段新建 P4 client `{agent}_{stream}` 并全量同步（Stable 0→126068 跑了 53min，**同步本身成功**）。
- **根因**：`PLN_TaskAiReview` 是 `checkoutMode=MANUAL` + **不挂任何 VCS root**，`Collect Review Context` 步直接跑 `python Tools/AiReview/AiReviewContextCollect.py`，**假设评审脚本随 UE 流的 sync 进入工作区**。但当时 `Tools/AiReview/` 只在 MainDev 流——Stable HEAD（126068，8/24 拷贝）里没有 → `Errno 2` exit 2，整链 FAILURE。
- **次生症状**：`Validate And Publish Result` 步被跳过 → 回调永远不发 → 后端 review 记录 `compile_status=running` 卡死（dashboard 一直转圈），尽管链已 FAILED。查评审卡住时先对 `compile_build_url` 的链状态。
- **修复**：次日 CL 129362（'add ai review tool'）把 `Tools/AiReview/` 合入 Stable 流，流层面根治；此后任意流首评前确认该流含 `Tools/AiReview/` 即可。
- **排查路径**：复合构建 REST 只返直接依赖需递归追踪；`Task_AiReview` 的 settings 里 `checkoutMode/checkoutDirectory` 是关键；sync 日志 grep 目标文件名可证「流里有没有」。

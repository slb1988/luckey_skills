# TeamCity AI Review 链

## 1. 当前拓扑

现行生产源码是 Windows/Win64 链：

```text
PLN_TaskSyncCyanCookDepot
  → PLN_TaskUnshelve
  → PLN_TaskBuildUEWindows
  → PLN_TaskAiReview
  → PLN_FlowAiReview（COMPOSITE 汇总）
```

依赖声明方向：Flow → AiReview → Build → Unshelve → Sync；执行方向相反。所有 snapshot 边设置 `runOnSameAgent=true`，Agent requirement 使用 WinBuilder 正则，workspace 按实际 Agent 与 stream 隔离。

历史 `TaskBuildUELinux`、`DefaultAgent_*`、`LINUX_MULTIARCH_ROOT` 和 Linux `p4ws/` 资料只用于读旧构建，不得恢复成当前配置。

TeamCity 通用链参数规则见 [teamcity-tool/build-chain-parameters](../../teamcity-tool/references/build-chain-parameters.md)，REST 查询见 [teamcity-tool/rest-api](../../teamcity-tool/references/rest-api.md)。

## 2. 参数所有权

业务输入由 Flow 确定并覆盖各消费者；中间 Task 不应再次自引用地 relay 同名参数。

| 参数 | 业务语义 |
|---|---|
| `env.p4_stream` / `P4Stream` | 目标 stream |
| `env.change_list` | Sync 基线/业务触发值 |
| `env.unshelve` | 被审 shelved CL；0 表示跳过 unshelve |
| `env.need_compile` | 是否实际执行 BuildUE/AS；不决定是否进入整条评审链 |
| `env.PI_MODEL` | Pi 模型，必须为 provider/model |
| `env.AI_REVIEW_CALLBACK_URL` | 本轮 Review 回调，含代际 nonce；输出时只保留 review_id |
| `DefaultAgent` | Agent 名称策略，不是实际已选 Agent |
| `env.NODE_WORKSPACE` | 目标 Agent 的盘根；不能被项目空值遮蔽 |

工作区不变量：

```text
Sync Root
 = Unshelve client Root
 = Build/Review 核验后的 Root
 = <NODE_WORKSPACE>/<actual-agent>_<stream>
```

路径公式必须在目标 Agent 上解析。配置成功、参数没有 `%...%` 残留、甚至链启动，都不能替代实际 Root/CL 的断言。

## 3. 各节点职责

### 3.1 Sync

- 同步本轮固定基线；
- 写 `Saved/latestCL`；
- 使用独立 DevOps checkout 运行 helper 不代表 engine workspace 也在那里；
- P4 client Root 不符合预期时应失败，不自动改 spec 或猜 fallback。

### 3.2 Unshelve / merge

`P4UnshelveStage.py` 在目标 client：

1. 清理本链授权范围；
2. unshelve；
3. 再同步到固定 baseline；
4. `resolve -am`；
5. `resolve -N` 复查未解冲突；
6. 写版本化 `merge_result.json`。

只看 `resolve -am` exit 0 不够：它可能空跑或跳过冲突。`merge_result.json` 同时作为 Task artifact 和 workspace `Saved/ai_review/` 证据；下游要交叉校验 schema、CL、stream、client、baseline、build ID 和完整文件集。

常见 exit 类别：CL missing、cross-stream、workspace missing、unshelve failure、baseline/preflight、deterministic conflict、merge execution/verification。不要把 Unshelve 失败称作编译失败。

### 3.3 TaskBuildUEWindows

典型步骤：

1. Resolve Workspace Root；
2. Build UE on Windows（`need_compile=0` 时跳过）；
3. AngelScript Compile Check（按需）；
4. Log Analysis Report（ALWAYS）；
5. Log Analysis Notification（失败时）。

AngelScript 检查与 C++ 编译是门禁证据。warning 不应全部塞进 50 KiB error tail；informer 的 AI Review 模式单独生成 `build_log_analysis.txt` 和 provenance/meta sidecar。

`PLN_TaskAiReview` 对 Build 节点使用允许下游继续的 failure policy：编译失败后仍要运行 Pi，目的是让 AI 读取错误并解释；这不代表编译通过。

### 3.4 TaskAiReview

当前步骤主线：

1. **Resolve Workspace Root**：核对实际 P4 client 与 Root。
2. **Collect Review Context**：运行 MainDev `Tools/AiReview/AiReviewContextCollect.py`；若 shelf 修改评审工具自身，trusted-source guard fail-closed。
3. **Pi Agent Review**：清本轮旧输出，按 `AI_REVIEW_MODE` 运行 `AiReviewRunner.py` 或显式 bypass。
4. **Validate And Publish Result**：运行 `AiReviewResultPublish.py`，写 result 并尝试 callback。
5. **Cleanup Workspace**：ALWAYS `p4 revert -w`。
6. **Log Analysis Notification**：Task 自身失败时的 opt-in informer 路径。

Runner 故障不会自动把链标红；Publish 会生成 `verdict=error`。callback 失败也可能只 warning。因此必须检查 artifact 和后端 activity，不能从 build status 推断业务成功。

## 4. 运行模式

`AI_REVIEW_MODE` 至少有：

- `review`：真实 Collect/Runner/Publish；源码默认目前为 review，但生产 build 的 effective value必须读 startProperties。
- `bypass`：紧急占位路径，写固定 approve 结果并沿同一 Publish 契约发布。

bypass 的绿色构建只证明链路可收口，不证明模型评审。回滚/切换时同时核对 versioned settings revision 和运行参数，不能只看 Kotlin 文件注释或 UI 当前值。

## 5. Artifact 契约

本轮关键文件位于 `Saved/ai_review/` 并由 Task 发布：

| Artifact | 用途 |
|---|---|
| `merge_result.json` | Unshelve/merge 证据与基线 |
| `shelved_diff.txt` | 实际 requested stream 的 baseline→merged workspace diff |
| `build_log_tail.txt` | 错误/fatal/failed 摘录或 fallback tail |
| `build_log_analysis.txt` | informer 生成的结构化 error/warning/AS 报告 |
| `build_log_analysis.meta.json` / provenance | 报告对应 build/CL/新鲜度证明 |
| `prompt.md` / `review_input.md` | Collect 与 Runner 的最终输入 |
| `pi_out.txt` / `pi_err.txt` | Pi stdout/stderr |
| `pi_session.jsonl` | 本轮 Pi 消息、token、tool call 和时间戳 |
| `runner_manifest.json` | Pi argv、模型、Memory、turn guard、时间与退出 |
| `result.json` | Publish 后的可信元数据结果 |
| `memory_state/**` | CI Memory 召回状态；可能含敏感业务上下文 |

Artifact 可能跨构建累积或被后续构建覆盖。分析本轮时按 build artifact、build ID sidecar 和 mtime/manifest 过滤，不读取“目录里最新文件”就认作本轮。

完整 session、prompt、diff、Memory 和 callback 信息都可能敏感；不要公开分享 artifact，不打印凭证或完整 URL。

## 6. 排队与耗时拆解

### 6.1 区分三类等待

1. **真正 queue wait**：Flow 入队到首个可运行节点获得 Agent。
2. **snapshot chain sequencing**：某个 Task 早已显示 queued，但在等待前置 Sync/Unshelve/Build；前置 finish 与本 Task start 紧邻，不是 Agent starvation。
3. **业务 worker defer/backoff**：Review 尚未触发 TC，或 callback 后 fallback/submit job在等待；不属于 TeamCity queue。

报告时分别计算，不能把 Task 的 `queuedDate→startDate` 全叫排队。

### 6.2 Pi 慢的典型签名

| 现象 | 优先判断 |
|---|---|
| 连续约 5 分钟静默，session 记录 `Request timed out`、0 tokens | provider/gateway HTTP timeout；不是模型在读代码 |
| 先固定约 120 秒，再多次 provider timeout | Memory bootstrap timeout叠加模型 retry |
| 接近 1800 秒整结束、turn guard未结束 | Runner hard timeout；继续看模型请求还是工具卡住 |
| tool call 指向无 path 的 grep/find、P4 UE 树无 ignore | 历史全树扫描黑洞；当前 allowlist 应为 read/ls/memory_search，不应恢复 grep/find |
| 1 秒左右 `Unknown option: --` | 构建机 Pi 版本偏旧，与 Runner argv 不兼容 |
| Pi 有合法 JSON但 callback无活动 | Publish/curl/nonce/CL 映射；构建绿色不能排除 |
| `pi_out.txt` 空，Publish result=error | 查 `pi_err.txt`、session最后消息、manifest；后端会走 fallback |

模型耗时与 diff 大小通常不线性。用消息级时间戳、input/output/cache token 与工具调用解释，而不是仅凭文件数。

## 7. 失败归因

从具体 Flow build 递归取 snapshot dependencies，按执行顺序找第一个：

- `status != SUCCESS`；且
- `statusText` 不是纯 `Snapshot dependency failed` 级联。

对应归因：

- Sync：P4/network/client/root；
- Unshelve：CL/stream/+l/merge/baseline；
- Build：真实 C++/AS；
- AiReview：Collect/Runner/Publish/工具链；
- Flow：只做汇总，不用 composite bookkeeping 日志代替根节点日志。

Build 成功而 AiReview 失败时，compile 仍可 passed；Sync/Unshelve 失败且 compile 必需时应阻断 approve。

## 8. 配置与 revision

每次调查记录：

- TeamCity server 版本；
- Flow 与所有 Task 的 global buildType ID；
- 实际 build 的 `versionedSettingsRevision`；
- `startProperties` 中脱敏后的关键参数；
- Agent name/ID、connected/enabled/authorized；
- 当前 UI 配置与 build snapshot 是否同一 revision。

versioned settings 开启时，UI-only 修改可能被 VCS 覆盖；已入队 build 也不会自动采用新配置。安全重排应从业务 Review 原生入口触发并更新其 build 关联，不手工复制一条孤儿 Flow。

## 9. 进一步参考

- 参数、Root、同机组和探针：[build-chain-parameters](../../teamcity-tool/references/build-chain-parameters.md)
- AI Review 历史性能与链故障：[flow-aireview-pipeline](../../teamcity-tool/references/flow-aireview-pipeline.md)
- 通知/informer：[task-aireview-notification](../../teamcity-tool/references/task-aireview-notification.md)
- 目录清理：[checkout-dir-auto-clean](../../teamcity-tool/references/checkout-dir-auto-clean.md)

这些文件含历史方案；遇到 Linux/旧 buildType 名时先看章节的适用范围。

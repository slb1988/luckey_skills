# 批量批准驱动（scripts/drive_approvals.py）

大批量批准（数十条）的执行驱动。复用方式：importlib 加载同目录 `review_queue.py`，不重复 HTTP 逻辑；
判断层仍是 agent 的活（逐条审核正文/实体/边/novelty 后形成决策），脚本只负责执行编排与安全恢复。

## 用法（2026-09-21 起为新接口）

```bash
python scripts/drive_approvals.py decisions.json --run-dir <run目录>
```

输入为 apply 决策 JSON 的顶层 `approvals` 结构，每项在 `review_id / content_mode / snapshot_token /
rationale` 之外**必须带 `memory_id` / `group_id`** 两个本地元数据字段，由生成决策的人/agent 从实际
审核的**同一 scan 包**原样带入；驱动不联网补齐、不 rescan 换 token。缺元数据、removals/rejections
混入或空 approvals 都在 POST 前拒绝（旧内嵌 DECISIONS 名单路径已移除）。

## 执行机制（与 core-rules 的对应）

| 机制 | 对应的既有规则 |
|------|---------------|
| 按物理 `group_id` 交错：每轮每组最多批一条，同组下一条等前一条 `memory_status=indexed` | 同组串行门禁只串行化本执行者；交错是门禁约束下的吞吐安全形式 |
| token 只用决策文件里已审核的原值；观测详情发现 token 变化 / memory 或组不一致 / `review_changed` → 转「待重审」 | 不自动换 token 重试；新预览须重新审核，不继承旧验收 |
| 组头缺席 open 列表 → 按完整 ID 直读详情核实（已 approved→等 indexed，rejected→并发终态跳过，仍 open→留 pending）；读取失败/404 保留为未知，不记 skip/完成 | 列表截断或并发变化都不能当终态；空批不是完成条件 |
| `preview_pending` 留在 pending，其他组继续；已审核且 token 匹配的 `preview_failed + original` 可执行，`curated` 不可跳过失败预览；全部暂不可执行时按 20s 节奏有限等待（单调时钟，15 分钟预算） | 暂态依赖等待，不忙转也不早退 |
| `hub_only` 不放行同组门禁；只有 `indexed` 才释放 | approved ≠ indexed |
| apply 子进程带 `--receipt-file`，决策与回执使用绝对路径，不受子进程 cwd 影响；POST 前持久化意图，响应后追加逐项回执；有意图无回执记 unknown，不重发，只读核对 | 503/timeout 回执 ≠ 服务端状态；一次 open 不是未提交证明 |
| apply 停止后仍有无提交记录的批内项：立即非零退出并给出 `.apply.log` 路径，未尝试项保留 pending；不把子进程失败更新为业务进展 | 修复本地执行错误后显式恢复，不能无限启动同一失败子进程 |
| 回执按完整 review ID 归因（8 字符前缀实测撞车）；`already_processed` 或详情已终态时核对 memory/group 后计入并发/先前终态，不算本次批准；终态自身引起的 token 变化不要求重新审核 | 本次动作回执与后续观察分开统计 |
| 全部对账完成后直接汇总，不做末尾全队列 rescan | 本批范围以输入决策为准 |

## run 目录与中断恢复

每次运行用独立 `--run-dir`（不覆盖 skills 内文件与历史材料）：

| 文件 | 用途 |
|------|------|
| `decisions.input.json` + state 内 sha256 | 固定本批输入；恢复时校验不一致即拒绝 |
| `state.json` | 最小状态，原子更新；损坏/不完整拒绝当空批重置，须人工核对 |
| `round-NNN.decisions.json` / `.receipts.jsonl` / `.apply.log` | 逐轮提交载荷、结构化回执、子进程输出；恢复后轮次追加不覆盖 |
| `drive.log` | 阶段日志（queue/detail/apply/verify/poll/finalize + 最后进展时间） |
| `stacks.txt` | 长时间未推进时的线程栈转储（faulthandler，仅诊断；Python 不能强制取消底层等待，保存证据后由操作员终止） |
| `run.lock` | 排他运行标记；陈旧标记**不自动抢占**——确认旧父/子进程已停止后人工删除再以同一命令恢复 |

中断恢复 = 同一命令重跑：先回放回执并只读核对——已尝试项不重复审批（有意图无回执=未知，只读核对），
未尝试项不丢失（组头轮转时重新核对 token/组对应关系，仍匹配才执行）。

## 退出码与汇总口径

| 退出码 | 含义 |
|--------|------|
| 0 | 本批已对账结束（全部 indexed 或已核实终态） |
| 1 | 输入/用法错误（POST 前阻塞） |
| 2 | 存在等待超时/待重审项 |
| 3 | 存在未知提交结果（暂停，未重发） |
| 4 | 读取、记录或本地执行失败（含 run.lock 冲突、state 损坏、apply 无提交记录） |

汇总把「本次批准回执」「未知回执核对后已批准」「并发/先前终态」分开统计；后几类不计入本次完成数量。

## 长批次运行时的队列活性

- **扫描时 `preview_pending` 的条目可能在处置期间由 worker 生成预览**（实证：2026-09-19
  `01a0b9f2`）。收尾前重扫一次，对新出现的预览按标准质量核对后补批，不要一律留队列升级。
- 处置期间新 session 持续归档，队列会边审边涨——本轮批次的范围以扫描判断过的 packet 为准，
  新到条目另起一轮，不混入本次完成统计。

## 停滞根因已实锤：Windows urllib getfqdn（附绕行）

长批次静默 wedge（进程活着、0 TCP、CPU 不涨、无日志）2026-09-23 经 `stacks.txt` 实锤根因：
`socket.getfqdn ← proxy_bypass_registry ← urllib urlopen`——Windows 注册表代理探测触发的
DNS 调用无限阻塞（纯标准库 urllib 客户端问题，与服务端无关；2026-09-21 的 LpcReply wedge
症状签名相同，按同一根因处置）。**绕行：跑 scan/drive 前置 `no_proxy='*' NO_PROXY='*'`**，
让 urllib 走环境变量分支、完全跳过注册表探测；绕行后当日两批 41 条全程无卡死。

客户端侧观测手段仍是 `drive.log` 阶段日志（含最后真实进展时间、逐 ID 详情完成进度）与
`stacks.txt` 定时栈转储；发现停滞时保存日志/栈后人工终止该 run，再按上节恢复流程续跑，
不能「杀掉后直接重跑」。`stacks.txt` 无法强制结束底层等待是已知限制。
清理「wedged」python 进程前先核 CreationDate + 0 TCP——tasklist 里命令行相同的进程可能是
几天前同命令行的残留（2026-09-23 实证两个 9/21 残留 scan 进程），误杀会毁掉仍在跑的 run。

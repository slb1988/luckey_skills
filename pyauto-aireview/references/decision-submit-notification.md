# 决策、代提交、客户端闭环与通知

## 1. Request Review 交接

当前 `DevOps/RequestReview.py` 作为 P4V Custom Tool：

1. 校验 pending CL 与 client；
2. `p4 shelve -f -Af -c <CL>` 刷新 shelf；
3. 记录文件清单/校验；
4. 对需要交接的 `+l` 文件立即 `revert -w` 释放独占锁；
5. 打开申请页；
6. 后台 watcher 跟踪 Review 并在终态收口作者 workspace。

不同版本曾采用“全部 revert”或 `--keep-local` 语义。调查具体用户现场时，以其已安装脚本 revision、watcher state/log 和 `p4 opened` 为准，不用旧说明猜行为。

Shelve 成功是本地清理前置。任何工具更新都必须证明：失败时不丢数据、不会把未上传内容当已备份、不会静默留下 `+l` 锁。

## 2. 预检与创建门

Request preflight 包含：

- CL、author、description、branch/stream、cl_type、shelf；
- 已有 Review 与可否 reopen；
- branch 默认 required reviewer，排除作者；
- submit validation dry-run；
- strict review 与 jury；
- force_ai、是否有 code files、branch review 是否关闭。

`POST /ai_review/request` 再做服务端强制校验，不能信前端 switch：

- shelf 必须存在；
- blocking submit rules 不允许由旧 skip/exemption 机制绕过；
- 创建或重开唯一 Review；
- branch closed direct pass 也保留 submit validation；
- 纯二进制可能跳 TeamCity，但空文件清单必须 fail-closed。

P4 change-submit trigger 的 review gate根据 branch 和受保护文件决定是否要求 Review：skill/UGS code/metadata 层有不同规则，strict branch 可覆盖全部文件。approved/submitted 的放行只应服务平台 bot，避免作者绕过代提交状态机。

## 3. 人工决策

### 3.1 基本规则

- Review 必须仍允许决策；
- 指定 reviewer 存在时，普通用户只有指定人可决定；
- 未指定时，首位合法决策者可自登记 reviewer；
- 任一有效 reject → rejected；
- 任一有效 approve → approved；
- 不做多数票计数；
- `__ai__` 是模型意见，不作为人工票；
- `__system__` 用于自动批准/direct pass。

`approved` 不是终态：P4 尚未提交，仍可通过受控 reject 收敛。`submitted/rejected/archived` 冻结普通变更。

### 3.2 Approve gate

`service._approve_gate` 只拦 approve：

- 编译确实 required 时，pending/running/failed 都不能批准；
- AI 确实 required 时，必须是当前轮 done；
- reject 不等待编译/AI完成。

判断 required 要看 shelf/option/live job，不是只看 enum。`need_compile=0` 不代表整条链没跑；同样，TC SUCCESS 不代表 AI done。

### 3.3 作者自批/自拒

当前源代码允许受控 self-approve：开关开启、AI done、风险严格低于 self-approve 门槛等条件同时满足。作者 self-reject 在进行中可作为否决票。

reopen 必须复位 author/reviewer/required/ai 的旧 decision；否则旧 author veto 会在新轮批准同秒把状态重新打回。排障时活动流中“approve 后立即 status→rejected”优先查残留票，而不是只查 risk。

### 3.4 Strict jury

strict branch 同时要求：

- reviewer 侧批准；
- jury 达到实时配置票数。

同一用户既是指定 reviewer 又是 juror 时，一票可满足两种角色。juror 决策不应被“仅指定 reviewer可投票”错误拦截。

### 3.5 自动路径

自动 approve 的典型条件：

- AI done；
- risk 不高于自动门槛；
- 编译 required 时 passed；
- 无指定 reviewer；
- 非 strict；
- verdict 不是 reject；
- 文件清单非空。

branch review关闭且非 strict 时可 direct system approve；strict 永不 bypass。所有阈值和开关以运行时配置为准，不把源码 default 当生产事实。

## 4. approved → submit queue

`service._trigger_auto_submit` 只入队并快速返回。真正 P4 操作由 `submit_worker.py` 执行，这消除了 approve HTTP 请求长时间持有 submit 的旧设计。

### 4.1 队列并发

- `ai_review_submit_jobs.review_id` UNIQUE，重复 approve不创建双任务；
- `workspace_key` 是串行域；
- 每域按最老 queued job claim；
- CAS 条件同时要求同域无 running；
- 同域严格串行，跨域可并行；
- claim 后再次解析 domain 并检查 drift/fence，防 client 映射在排队期间变化。

只有代提交需要按共享 bot workspace 串行；不要把旧 backend branch busy 门重新套到 TeamCity 投递。

### 4.2 直提

典型 `p4 submit -e` 路径：

1. 确认 shelf/owner/stream/client和当前 Review 仍为 approved；
2. 必要时把 shelved CL 临时转给服务账号；
3. 执行 `submit -e`；CL 可能 rename；
4. 从明确回执取得 actual submitted CL；
5. DB 幂等收敛 `review.cl/cl_type/status`；
6. 软性恢复原作者署名；
7. 发送成功通知。

不要猜提交号。只有明确 P4 回执或只读对账证明才能写 submitted。

### 4.3 Auto-merge

直提遇到 out-of-date/open-files 类错误时，可进入 `_auto_merge_submit`：

- 建/选受控 pending CL和正确 stream client；
- unshelve；
- sync 到固定 baseline；
- `resolve -am -c`；
- `resolve -N -c` 复查；
- clean 才 submit。

`resolve -am` 返回 0不代表无冲突。确定性 conflict可自动 reject；transient/未知错误不能硬选 theirs/yours 放行。虚拟/跨 stream 文件需要映射该 target stream 的受控 client，不能复用不映射文件的 MainDev bot client。

### 4.4 明确失败

现行策略是“一次失败停止”：

- Review 保持 approved；
- submit job failed；
- activity 和通知带真实 P4 error；
- 由获准用户/admin手工 retry或 reject；
- 不按旧 `AI_REVIEW_SUBMIT_RETRY_MAX` 自动循环提交/耗尽打回。

人工 retry 是重新入队，不应绕过串行域和幂等 fence。

### 4.5 结果未知

网络断开、进程终止或 P4 回执不完整可能产生 `SubmitOutcomeUnknown`：

- 写 manual_required；
- 不自动重试；
- 不改作者、描述或“最近提交”去猜新 CL；
- 先用 CL state/filelog/明确回执做只读对账；
- 对账仍不唯一时交人工。

“原 CL 不存在”可能表示成功 rename，也可能删除/其他状态；不能直接 rejected。

### 4.6 Crash recovery 与 sweep

running 超过 stale 宽限后：

1. 先检查当前轮 manual marker；
2. 读取 `vcs.cl_state`；
3. 已 submitted → 补 DB、job done；
4. 仍 shelved且没有未知标记 → CAS requeue；
5. missing/pending/unknown → manual。

周期 sweep：

- queue 已管理的跳过；
- manual marker跳过；
- 无失败记录的幽灵窗口做自愈/对账；
- 有失败且 CL missing 的只读核对，不重新执行 submit；
- 成功 activity按当前 approved round 的 activity ID 边界判断，不按 DATETIME 秒精度猜顺序。

## 5. P4 与 DB 的非事务边界

关键中间态：

```text
Review approved 已提交 DB
  → P4 submit 成功
  → Flask 进程在 DB finalize 前中断
```

此时 depot 已有内容，但 Review仍 approved/旧 CL。恢复必须优先证明 P4 事实，再补 DB和署名；重启/部署脚本不能把“HTTP请求结束”当作 submit 已原子完成。

反向也要防：DB不能在 P4 明确成功前写 submitted。`_finalize_submitted` 使用 current-round success activity 和 status CAS双重幂等。

## 6. RequestReview watcher 闭环

本地 watcher 的持久 state/log位于用户 LocalAppData，而不是 TeamCity workspace。它：

- 按作者查询 Review；
- 根据申请选项处理 non-lock 文件；
- submitted 后 revert/sync/resolve，使本地 workspace 跟随新 depot 状态；
- rejected 后恢复 shelf并处理独占 filetype；
- 通过短 TTL cancel intent与服务端协调。

排障“平台已提交但本地还脏”时，同时看后端 activity与 watcher log，不要让服务端 worker直接操作作者 client。

## 7. 通知矩阵

通知全部是辅助副作用：异常记录日志但不回滚业务事务。

| 事件 | 典型收件人/时机 |
|---|---|
| 创建、重开、shelf更新 | reviewer；AI开启时可延后到结果就绪 |
| 无 AI 且无 reviewer | 作者，提示没有审阅落点 |
| AI完成 | 作者/请求者；高风险可进群；reviewer有独立就绪卡 |
| AI失败 | 作者及配置群 |
| 编译/链失败 | 作者、required reviewer、群；应带真实阶段和链接 |
| 评论、回复、Task、Task addressed | 作者、被回复人、reviewer按语义路由；自通知跳过 |
| rejected | 作者 |
| approved | 作者，提示进入代提交而非宣称已提交 |
| submit成功 | 作者，带实际 CL与本地 sync指引 |
| submit失败/未知 | 作者、管理员、群；必须保留真实 error/manual状态 |

AI findings 不逐条发通知，避免刷屏；汇总由 AI done卡承担。

## 8. 活动流取证

`cl_submitted` payload需要区分：

- success：actual CL、original CL、method、是否 auto-merged/stream fallback；
- failure：success=false、原始错误；
- manual：manual_required、outcome/error code/stage/receipt摘要；
- soft probe：ghost/reconcile/attribution/queue recovery。

`decision_made` 应能区分 self_approve/self_reject/auto_approve/jury/branch closed；`status_changed` 独立记录 from/to。提交问题不要只数 `cl_submitted` 总行数，要从本轮最近一次 `status_changed(to=approved)` 之后统计。

## 9. 恢复边界

- 普通用户可走 refresh/reopen/trigger_ai/retry_submit 等原生入口；
- `force_status` 和生产 SQL 是最后逃生阀，先备份并保存活动审计；
- 任何 DB 手修前都需核对 P4事实、当前 round、并发 worker和终态；
- 不删除唯一约束来“修复”CL冲突；约束是误认他单的最后防线；
- 恢复已提交事实优先于迟到 reject，但必须有明确 P4证据；
- 未经用户明确授权不改生产状态、不触发提交或通知。

# AI Review 决策模型与 reopen 自拒残留（review #126 根因）

py_automation 后端 `service.py` 的评审决策/风险门槛模型，以及 2026-09-04 排查 review #126（jiangheng 批准后仍失败）实锤的 reopen 复位缺陷。

## 决策与风险门槛模型

- `make_decision` 的 risk 门槛只拦两处：**作者自批**（要求 risk <60）和 **AI 自动放行**（要求 risk ≤15）。**其他 reviewer 的批准没有任何 risk 门槛**——设计如此：AI 有误报可能，高风险单要留人兜底批准的通道。
- approve 的落库门禁（编译 passed + AI 分析 done）与 risk 门槛相互独立，互不影响。
- `_recalculate_status`：自 2026-12「作者自拒一票否决」起，**author 行的 decision 并入 votes**；此前 author 行不携带有效决策，这是后续 reopen 缺陷的引入点。
- activity 表记录每个决策与状态迁移（带时间戳），是排障第一手资料。特征识别：**「人工 approve 落库」与「系统 from pending → rejected」同秒相邻** = 被存量否决票当场打回，而非风险分拦截。
- 排障入口（无需 SSH）：`GET /ai_review/reviews/<id>`（状态/compile_build_url/风险分）+ `GET /ai_review/reviews/<id>/activities`（事件时间线，payload 含 build_id/错误文本）；时间戳为 UTC，与 TC REST 的 +0800 对齐时换算。

## reopen_review 复位漏 author（review #126 根因）

`reopen_review()` 只把 role ∈ `('reviewer', 'required_reviewer', 'ai')` 的 participant decision 复位为 pending，**漏了 `'author'`**。作者自拒后 reopen，author 行的 `rejected` 残留为常驻否决票，之后任何人批准都会在落库当场被它打回 rejected（不触发代提交）。

必现路径：高风险 → AI reject → 作者自拒修改 → reopen → 他人兜底批准——正好踩在人工兜底设计上。

测试盲区：`test_reopen.py::test_reopen_resets_participant_decisions` 打桩的 author decision 本来就是 pending，断言空转通过，覆盖不到此路径。

**修复状态（截至 2026-09-04 未实施）**：复位条件加 `'author'`；补回归「author 带 rejected reopen 后复位 pending，之后他人 approve 能推进到 approved」。

## 误打回 review 的 DB 恢复（不重跑编译/AI）

1. 作者 participant decision 改回 `pending`，review status `rejected` → `pending`（保留他人已落库的 approved 票）；
2. 批准人再点一次批准 → approved → 自动代提交触发。

## compile_status 误标 failed（review #138 根因，2026-09-05 实锤）

**链行为前提**：2026-09-05 起 AI review 链**始终触发**（Sync → Unshelve → [BuildUE] → Pi 评审，链尾 pi 评审是详细 AI 结果的主来源），BuildUE 编译步骤**仅当 `need_compile=true` 才进链**——没勾选编译的单，链构成里根本没有 BuildUE。

**根因**：`ai_worker.py` `_poll_compile` 的 FAILURE 分支用 `_chain_tail_only_failure` 甄别「是否只有链尾失败」（避免误伤编译结论），实现是在链里找 BuildUE；未勾选编译时找不到 → 保守返回 False → 链级故障（如 TaskUnshelve FAILURE）被当作编译失败，记 `compile_status='failed'` → 页面显示「编译失败 ✗」并误发编译失败告警、误跑编译日志 LLM 分析——实际链里从未跑过编译。

**修复（2026-09-05 已在工作区实现，当Session未 submit/部署）**：`compile_wanted=False` 时链级故障统一记 **`'skipped'`**（前端显示「未编译」），三处：`_trigger_compile` 降级分支、`_poll_compile` 超时分支、`_poll_compile` FAILURE 分支（在 tail 甄别前短路）；`compile_wanted=True` 行为不变。回归用例在 `tests/unit/ai_review/`。

**识别特征**：页面「编译失败」但该单未勾选编译 / 链构成里无 BuildUE。存量误标单 #138 / #106 / #23（均已 submitted 终态，仅影响展示，DB 把 `compile_status` 订正为 `skipped` 即可）。

## review #129：approved 状态门禁放行作者手动提交（2026-09-04 实锤）

**现象**：作者看到 Review 被 rejected，但 CL 内容实际已进 depot——「被拒绝后还能 P4V 直接提交」是**时序错觉**，真相是反的：

1. 作者 14:13 直接 `p4 submit` 被 rule_review_gate 正确拦截（命中 2 个 SKILL.md，无 Review）→ 走 Request Review 建 #129；
2. 14:42:11 作者**自批**（MainDev `review=True` 但 `review_required_reviewers=[]`、无 strict_review/陪审团，risk 35 <60 自批门槛通过）→ status=approved → 触发代提交；
3. 平台 `submit -e` 两次失败：作者自己在本机 client 重新 open 并 +l 独占锁了全部 5 个文件（p4 原始报错 `No files to submit`，`_format_locked_error` 探测补出锁持有者）。**失败回滚把 CL 属主转回作者**（`change -f -U author`，设计如此：保证作者仍能手动 submit -e）；
4. 14:45:18 作者 P4V 手动 submit 129050 → trigger 回调平台 → **gate 查 review status=approved → `existing.status in ('approved','submitted')` 直接放行**（此路径本为平台代提交防死循环设计，但**只认 CL 号+状态，不校验提交者身份**，作者手动提交与平台 `submit -e` 不可区分）→ 提交成功 rename 为 CL 129108（User=WeiXuanye）；
5. 14:46:23 平台第 3 次重试：`get_cl_info(129050)` 报 no such changelist → 14:46:25 `_reject_review_for_submit_failure` 把 approved 打成 rejected（"auto-submit failed 3 times"）——**rejected 发生在提交成功之后 67 秒**，是系统对「CL 消失」的兜底误伤，不是内容被驳回。

**两个设计缺口**：
- gate 的 approved 放行路径不校验提交者身份（payload user 应为 `AI_REVIEW_P4USER` 才放行，作者本人提交应拒绝并提示「平台代提交进行中」）；
- `submit_shelved_cl` 的「cannot resolve CL author（CL 不存在）」错误被 `_reject_review_for_submit_failure` 当作普通失败计数打回——CL 消失应先走幽灵对账（`cl_state`/rename 追溯）确认真已提交，直接收敛 submitted，而不是 reject。

**识别特征**：活动流里「锁拒绝 → cannot resolve CL author → auto-submit failed N times → rejected」序列；P4 侧文件已被作者本人 CL 提交（filelog 核实）。

## 代提交 bot client 不映射虚拟流目标（review #213 根因，2026-09-08 实锤）

**根因**：代提交 bot client `autoserver-MainDev-review` 绑主流 `MainDev`（`Paths: share ...`），**不映射 `//CyanCookOfficialDepot/WwiseProject_main/`**。作者 client 经虚拟流 `MainDev_Wwise` 的 `import+` 映射可把该 depot 的文件 shelve 进面向 MainDev 的 CL；这种 shelf 平台 `submit -e` 必然失败：p4 要求「files shelved to a stream target may only be submitted by a stream client that is mapped to the target stream」。shelf 内容与 bot client 都不变 → 失败完全确定性，每次重试逐字节相同地失败；attempts 耗尽后 review 停 `approved + submit_failed`，不再自动重试。

**p4 报错层级陷阱（排障关键）**：该场景的逐文件明细（`file not mapped in stream ... client`）只是 **warning 级**，p4python 抛出的异常只携带 error 汇总行——服务端日志和 activity 永远只有光秃秃的 `Submit failed -- fix problems above`。真实原因必须读 `p4.warnings`（`submit_shelved_cl` 未拼进错误日志）或沙盒 1:1 复现才能看到。

**鉴别特征**：失败时刻无 validate/trigger 回调 → 死在 trigger 前的映射检查，可据此与门禁拒绝区分；shelf 基线==head 排除 out-of-date、无 `+l` 锁排除 #129 类锁冲突。

**救单（沙盒已验证）**：另建绑 `//CyanCookOfficialDepot/MainDev_Wwise` 的 client，从它 `submit -e <shelved_cl>`，再把 review 行修平为 submitted；作者手动提交会被 gate 拒（approved 只放行 bot），必须平台侧做。

**防复发（截至 2026-09-08 未实施）**：`submit_shelved_cl` 把 `p4.warnings` 拼进错误日志；新增 `file not mapped in stream` 错误分类 → 自动切换到对应 stream 的 client 或走 `_auto_merge_submit` 兜底。

## 分支串行 busy 门：「更新review」点了不触发（trigger_ai 静默 defer）

「更新review」按钮 = `POST /ai_review/reviews/<id>/trigger_ai`（api.py；路由**无 /api 前缀**，2026-09-09 实测带前缀 404，全部路由见 :5000/swagger.json）：终态（submitted/rejected/archived）或有 running job 时拒收；否则重置 compile_status='not_started' + 清上轮 AI 产物、job 重新 queued 并 `_kick_ai_job` 秒级点炮。**端点本身不做分支 busy 检查**——拦截在 worker：`process_job` 进 `TRIGGER_COMPILE` stage 前先过 `_branch_compile_busy`（ai_worker.py），命中则本轮静默跳过——job 保持 queued、attempt_count=0、零报错零活动，前端表现就是「点了没反应」。

busy 判定口径：同分支 + 其他 review + status ∈ (pending,reviewing) + compile_status ∈ (pending,running) + update_time 在近 `_BRANCH_BUSY_FRESH_HOURS`（=4h）内。终态 review 卡 running 的行不参与阻塞（2026-12 review #93 僵尸阻塞事故的修复口径）；轮询已死的行（job 重试耗尽 failed / 进程重启残留）不再 bump update_time，最多堵 4h 自愈。

**强制停止 TC 构建后点「更新review」不触发 → 优先查此门**：同分支找 compile_status 卡 pending/running 且 4h 内有更新的活跃 review；后端日志 grep `blocked by review #`（busy 命中会点名 blocker）。修复：按 TC 真实结果直接改库 `UPDATE ai_reviews SET compile_status=..., update_time=update_time WHERE id=<blocker>`（update_time 保持不变，防列表「耗时」被 bump）。

> 该门的完整设计语义（为什么终态行必须豁免、轮询 bump update_time 机制）权威文档在 pyAutomation 仓库 `backend/server/applications/ai_review/SKILL.md`「trigger_compile」段——ai_review 排障先读它再读代码。

## worker 取单饿死：queued 查询 limit(5) 无 ORDER BY（review #241 根因，2026-09-08 实锤）

**取单机制**：`create_review`/`trigger_ai` 建 `AIReviewJob(status='queued')` 后 `_kick_ai_job` 秒级点炮；kick 撞 busy 门则让位回 queued，之后只剩 60s 一轮的 worker tick 能捞。tick 取单查询（`ai_worker.py:1417`）`filter(status=='queued').limit(5)` **无 ORDER BY**——MySQL 稳定按主键序返回前 5 个。queued 积压 >5 时，id 大的 job **永久进不了候选集**；排前面的 job 每轮 tick claim → 撞 busy 门 → 让位（`attempt_count` +1/-1 抵消，**无退避无 backoff**），永远占满 5 个名额。

**识别特征**：DB 里 job queued、`attempt_count=0`、无报错无活动，但 tick 日志 `queued=[...]` 列表恒为同一批低 id job、全部 "blocked by review #xxx"——被饿死的 job 在日志里零痕迹。review #241（job 233）即被 181/220/226/229/230 五个 MainDev 占位 job 饿死。

**修复方向（当 Session 未实施）**：① 取单加 `order_by(AIReviewJob.id)` 保证 FIFO；② busy 让位时写 `next_retry_time = now + 60~120s` 退避，被挡 job 让出候选名额。只加 ORDER BY 或只放宽 limit 都不治本（前者仍被占位，后者只是拖延 + 每轮空转 churn）。

**附带两个结构性事实**：
- tc_inflight 看门狗只覆盖 `tc_inflight` 阶段——`load_diff` 等阶段卡死（job 21 running/load_diff 自 8/31 僵尸）无人收尸。
- busy 让位路径**刻意不清 claim_token**（queued 却带 token 是良性设计，不是脏数据，不要修）。

## reopen 后失败计数跨轮累计 + 超限 continue 跳过，自动拒绝失效（review #246 根因，2026-09-08 实锤）

**失败计数与拒绝的耦合结构**（service.py）：
- 重试调度统计该 review 的**全部历史失败**（~2040-2045 行），不区分 reopen 后的新一轮——reopen 后的失败直接在旧计数上累加。
- 调度循环对 `n >= max_attempts`（=3）的单 `continue` **整体跳过**（~2119-2120 行）——重试、对账、拒绝全都走不到。
- `_reject_review_for_submit_failure` 只在「调度器亲自执行第 N 次重试且当次失败」的路径上被调用（#129 即此路径：第 3 次重试失败 → rejected）。计数因 reopen/人工重试**越过**上限而非调度器恰好踩中的单，永远到不了这个调用点。
- 人工重试入口同样没有超限拒绝逻辑，只累加计数。

**#246 时序**：17:14 第一轮 3 败自动拒绝（机制正常）→ 18:51 作者 reopen 同一 review → 20:22 批准后提交失败、累计 4 → 调度器每轮 `continue` 跳过 → 22:45 人工重试再败、累计 5。终态卡 `approved`、失败 5/3、无 next_retry_time，无人收尸。排查时 CL 129911 已不存在（删除或提交后 rename 未定）。

**识别特征**：review 停 `approved` 且失败计数 > max_attempts、无 next_retry_time，活动流含 reopen 记录；与 #213（attempts 耗尽停 approved + submit_failed）同属「计数到顶后无兜底」族。

**修复方向（当 Session 未实施）**：① 失败计数按 reopen 轮次重置/独立计数；② 超限卡单先走幽灵对账（cl_state/rename 追溯，同 #129 缺口），确认未提交再自动拒绝——把拒绝从「调度器执行路径的副作用」改为「计数越限的独立兜底」。

## 幽灵对账误认他单提交 + 失败事务未回滚（review #73 根因，批准 500 假象）

**触发场景**：approve 已落库后，代提交发现原 shelved CL 不存在，转幽灵对账（`_finalize_submitted`）。

**根因（两缺陷叠加）**：
1. 对账候选 CL 只按「作者 + 描述」匹配，**不校验目标 CL 是否已被其他 review 占用**。#73（原 CL 128548）与 #96（原 CL 128794）作者、描述相同；#96 提交后 rename 为 128834，对账把 128834 误认成 #73 的提交结果 → UPDATE #73 的 `cl` → 撞 `ai_reviews.cl` 唯一约束 `Duplicate entry '128834' for key 'ai_reviews.cl'`。
2. 异常路径（service.py ~1959）IntegrityError 后**未先 `rollback()`** 就读 ORM 属性 → 二次抛 `PendingRollbackError` 掩盖原始冲突，前端只见光秃 500。另有误导日志：service.py ~2242「收敛成功」打印在事务 commit **之前**。

**识别特征**：批准其实已生效（status=approved 早已落库），500 发生在批准后的对账阶段，反复点批准重复报同一错；排查先查撞约束的 CL 号实际归属哪条 review（找同作者同描述的另一单）。

**修复方向（当 Session 未实施）**：`_finalize_submitted` 写入前查目标 CL 是否已被别的 review 行占用（占用则跳过/告警而非 UPDATE）；异常路径先 `rollback()` 再读 ORM。**不要删 `ai_reviews.cl` 唯一约束**——它是此类误认的最后防线。同作者同描述的双单先与作者确认旧单是否已被新单替代再归档，不要直接把 cl 改成新号。

**排障入口提示**：ai_review 源码在 pyAutomation 仓库 `backend/server/applications/ai_review/`（本机工作区 `D:/work/admin_sun_depot_7184/pyAutomation/`），**不在 MainDev 游戏 depot**——别去 MainDev 采集器代码里找。

## 已知缺口

- 「批准后被系统打回」路径**无任何通知**，作者在页面只看到 rejected，不知道发生了什么。
- **非编译单的链级 FAILURE 对自动放行不可见**（2026-09-09 review #197 实锤）：`_auto_approve_check` 只在 `compile_check_required` 为真时要求 compile_status=passed；无代码文件且未勾选编译的单，链 FAILURE（如 Unshelve 独占锁失败）后后端降级「无可分析文件」→ risk 0 → 直接命中 ≤15 自动放行并触发代提交——「链从未跑到评审步」不进准入判定（空清单 fail-closed 已修，链失败变体未堵）。识别特征：活动流 `compile_finished {tc_status: FAILURE, chain_failed: true}` 紧跟 `ai_analysis_done {reason: "no analyzable files"}` + 自动放行评论写「编译验证通过」（comment 模板硬编码，compile skipped 也写「通过」，误导）。

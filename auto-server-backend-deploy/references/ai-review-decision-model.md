# AI Review 决策模型与 reopen 自拒残留（review #126 根因）

py_automation 后端 `service.py` 的评审决策/风险门槛模型，以及 2026-09-04 排查 review #126（jiangheng 批准后仍失败）实锤的 reopen 复位缺陷。

## 决策与风险门槛模型

- `make_decision` 的 risk 门槛只拦两处：**作者自批**（要求 risk <60）和 **AI 自动放行**（要求 risk ≤15）。**其他 reviewer 的批准没有任何 risk 门槛**——设计如此：AI 有误报可能，高风险单要留人兜底批准的通道。
- approve 的落库门禁（编译 passed + AI 分析 done）与 risk 门槛相互独立，互不影响。
- `_recalculate_status`：自 2026-12「作者自拒一票否决」起，**author 行的 decision 并入 votes**；此前 author 行不携带有效决策，这是后续 reopen 缺陷的引入点。
- activity 表记录每个决策与状态迁移（带时间戳），是排障第一手资料。特征识别：**「人工 approve 落库」与「系统 from pending → rejected」同秒相邻** = 被存量否决票当场打回，而非风险分拦截。

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

## 已知缺口

「批准后被系统打回」路径**无任何通知**，作者在页面只看到 rejected，不知道发生了什么。

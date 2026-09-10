# pyAutomation 后端模块

## 1. 代码位置与职责

根目录：`pyAutomation/backend/server/applications/ai_review/`（属于 `ws:autoserver-deveops`）。

| 文件 | 责任 |
|---|---|
| `model.py` | Review、文件、参与者、评论、finding、activity、AI job、submit job、jury config 模型 |
| `api.py` | `/ai_review` Flask-RESTX 资源、参数校验与响应投影 |
| `service.py` | 创建/重开/刷新、状态机、AI 结果、决策、审批门、提交生命周期协作 |
| `ai_worker.py` | AI job claim、TeamCity 触发/轮询、chain 归因、backend LLM fallback |
| `submit_worker.py` | 代提交串行队列、auto-merge、未知结果和 stale recovery |
| `prompts.py` | backend fallback 的 system/user prompt；它不自动继承 MainDev `pl-review` |
| `notification.py` | 飞书卡片与收件人路由；通知失败 log-only |
| `submit_validation.py` | Request 阶段 submit dry-run 与 blocking/warning rules |
| `vcs/base.py` | VCS 协议、CL/File 数据类、`SubmitOutcomeUnknown` |
| `vcs/p4_adapter.py` | P4 元数据/diff/shelve/submit/auto-merge/client/CL 状态 |

支持模块：

- `server/util/teamcity_util.py`：触发构建、状态、snapshot dependencies、artifact。
- `server/util/skill_file_rules.py`、`code_file_rules.py`：强制评审文件分类。
- `server/applications/p4_trigger_validate/rules/rule_review_gate.py`：P4 change-submit 门禁。
- 前端：`pyAutomation/frontend/src/views/ai_review/`、`src/api/aiReview.ts`。

先读模块自己的 `SKILL.md` 与最窄 reference，但遇到版本冲突时以当前源码和运行时为准。

## 2. 数据模型：9 张表

### `ai_reviews`

核心字段：

- `id`：稳定业务身份；
- `cl` UNIQUE、`cl_type=shelved|submitted`；
- `status=pending|reviewing|approved|rejected|submitted|archived`；
- `ai_status=pending|running|done|failed`；
- `compile_status`、`compile_build_id/url/error_count/result/analysis`；
- `ai_risk_score/ai_summary/ai_result_source/ai_verdict`；
- `request_options`：note、requested_by、need_compile、unshelve_non_lock、submit_validation 等；
- `open_tasks` 冗余计数；终态时 `update_time` 冻结，供列表耗时展示。

### `ai_review_files`

每文件记录 depot path、action、`file_type=code|config|text|content`、行数、risk、`diff_content`。diff 使用 MEDIUMTEXT并设单文件约 1 MiB 应用层上限，避免大 diff 毒化事务。

### `ai_review_participants`

`role=author|reviewer|required_reviewer|ai`，`decision=pending|approved|rejected`；`added_by` 区分指定 reviewer 与 open-flow 自登记。

### `ai_review_comments`

人类/AI 评论、Task 状态、递归 reply、file/line anchor、resolved。当前为 hard delete；不要把未来长期 Pi 对话依附于会在 refresh 时删除的 AI 评论。

### `ai_findings`

结构化 AI 问题：文件、category、severity、confidence、行号、摘要、建议和片段。

### `ai_review_activities`

业务审计流。常见 event：`review_created`、reviewer 增删、`decision_made`、评论/Task、`status_changed`、`ai_analysis_started/done`、`compile_started/finished`、`shelve_updated`、`cl_submitted`。排障优先读它，不只看 Review 当前快照。

### `ai_review_jobs`

一条 Review 一个 AI job。记录 stage、status、claim token、attempt/retry、next retry、requeue request、token usage；用于幂等推进 TeamCity/LLM 流程。

### `ai_review_submit_jobs`

一条 Review 一个 submit job。记录 `workspace_key`、status、claim token、attempt、开始/结束和最后错误；代提交并发域的权威队列。

### `ai_review_config`

单行 jury 配置：成员与要求票数；实时读取，不依赖进程缓存。

## 3. API 路由

当前 namespace 挂载在 Flask 根路径 `/ai_review`，不是旧 `/api/ai_review`。执行前可用 `:5000/swagger.json` 复核。

### Review 与配置

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/ai_review/reviews` | 列表；status/author/branch/pending reviewer 筛选 |
| POST | `/ai_review/reviews` | 直接创建，主要用于 submitted 历史单 |
| GET | `/ai_review/reviews/<id>` | 详情，含 decision/compile/AI/jury/submit_progress 投影 |
| DELETE | `/ai_review/reviews/<id>` | 管理删除 |
| GET/PUT | `/ai_review/config` | jury 配置 |

### Request 生命周期

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/ai_review/request/preflight` | CL、shelf、reviewer、规则、AI/compile 策略预检 |
| POST | `/ai_review/request` | 创建或重开唯一入口 |
| POST/GET/DELETE | `/ai_review/request/cancel` | 作者取消意图，供本地 watcher 协作 |
| POST | `/ai_review/reviews/<id>/refresh` | 进行中 shelf 更新，保留可保留的评论锚点 |
| POST | `/ai_review/reviews/<id>/reopen` | rejected/archived 重开 |
| POST | `/ai_review/reviews/<id>/trigger_ai` | 手工重排 AI；终态拒绝 |

### 参与者、评论与文件

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/ai_review/reviews/<id>/participants` | 列表/添加 reviewer |
| DELETE | `/ai_review/reviews/<id>/participants/<uid>` | 删除 reviewer |
| POST | `/ai_review/reviews/<id>/participants/<uid>/decide` | approve/reject |
| GET/POST | `/ai_review/reviews/<id>/comments` | 评论与回复 |
| PATCH/DELETE | `/ai_review/comments/<id>` | Task/resolved 更新或删除 |
| GET | `/ai_review/reviews/<id>/files` | 文件清单 |
| GET | `/ai_review/files/<file_id>/diff` | unified diff |
| GET | `/ai_review/files/<file_id>/content` | old/new content；shelf old 使用 shelf base，不用 `#head` |

### AI、活动与管理恢复

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/ai_review/reviews/<id>/ai_summary` | summary/risk/source/verdict/findings/compile |
| POST | `/ai_review/tc_callback` | TeamCity result；review_id、token、cb 代际、body.cl 交叉校验 |
| GET | `/ai_review/reviews/<id>/activities` | cursor 分页事件流 |
| POST | `/ai_review/reviews/<id>/reload_files` | 管理重建文件清单/diff |
| POST | `/ai_review/reviews/<id>/retry_submit` | 人工重入 submit queue；manual_required 时需先处置未知状态 |
| POST | `/ai_review/reviews/<id>/force_status` | 管理逃生阀，不是普通修复路径 |

相关 P4 trigger 入口：`POST /p4_trigger_validate/validate`。

注意：部分管理/评论接口沿用内网信任约定，不能据此假设公网授权安全；若改变暴露边界，先做完整 authz 审计。

## 4. AI worker

### 4.1 调度

- `kick_job(job_id)`：创建/重开/refresh/trigger 后的秒级 one-shot，主路径。
- `ai_review_worker`：60 秒 ticker，补偿丢 kick、取 queued、轮询 `await_compile`、回收 stale `tc_inflight`。
- 每 tick 的候选和 polling 都有限额；claim 用条件 UPDATE + `claim_token`，不是先查后写。

### 4.2 Stage

```text
load_diff → trigger_compile → tc_inflight → await_compile → analyze
```

`tc_inflight` 是“TC 已触发但 DB build ID 尚未安全落下”的代际 fence。超过 stale 窗口可 CAS 回 queued/trigger_compile，避免进程中断导致永远悬空。

### 4.3 TeamCity 触发参数

`_trigger_compile` 通过 `trigger_build_with_stream` 触发全局配置 ID `PLN_FlowAiReview`，下发：

- stream/change list；
- `env.unshelve`；
- `env.need_compile`；
- `env.PI_MODEL`，必须带 provider 前缀；
- callback URL，含 Review ID 与当前 nonce。

触发后 `compile_result.callback_nonce` 是当前 callback 代际。不要在日志或报告中回显完整 URL。

### 4.4 轮询、chain failure 与 merge gate

- 所有非终态 TC 状态都会消耗 polling budget；默认约 3 小时，404 直接终结降级。
- `_classify_chain_failure` 递归定位 sync/unshelve/build/ai_review 的首个真实失败，不把 snapshot dependency 级联报错当根因。
- Build 成功、仅 AiReview 尾部失败时保持正确 compile 结论。
- Sync/Unshelve 错误读取失败步骤日志；已知 transient 可按独立 chain retry 预算回到 trigger。
- `_evaluate_merge_gate` 读取本轮 TaskUnshelve 的 `merge_result.json`。冲突/错误 fail-closed；transient 才允许重试。
- 真编译错误由 `_analyze_compile_errors` 分析实际 BuildUE build，而非 composite bookkeeping 日志。

### 4.5 backend LLM fallback

`_run_analysis` 在没有定案 tc_callback 时调用 `_call_llm`，再计算 risk、落 findings/summary。它是降级路径，不等于 Pi session 续接，也不自动继承 MainDev `pl-review`。

异常由 `_handle_failure` 处理：在 `AI_REVIEW_MAX_ATTEMPTS` 内按指数分钟退避，超限 failed + 通知。报告耗时时，把每次 HTTP timeout 与 backoff 分开，不把全部静默期称为模型推理。

### 4.6 callback

`apply_tc_ai_result`：

- 校验 Review、CL、token 和 callback nonce；
- 定案 verdict 才清旧 AI 产物并写新结果；
- `error/skipped` 只留活动，继续 fallback；
- 幂等 replay；旧代际/终态迟到结果零写入；
- 写 findings 前后都检查是否被并发 callback supersede；
- 可从 snapshot BuildUE 成功侧提前 settle compile。

## 5. Submit worker

`submit_worker.py` 的 30 秒 ticker和 one-shot kick负责真正代提交：

- `enqueue_submit_job` 对 Review 幂等；
- 按 `workspace_key` 选择最老 queued，用 CAS + “同域无 running”条件 claim；
- 同一 P4 workspace/domain 严格串行，不同 domain 可并行；
- `_run_queued_submit` 执行直提或 auto-merge；
- 一次明确失败后停止，不套 AI worker 自动重试；
- `SubmitOutcomeUnknown` 写 manual_required，禁止猜测最近 CL；
- stale running 用只读 `cl_state` 对账成 done/requeue/manual；
- sweep 只做 ghost/CL-missing 对账，不是循环 submit。

详细业务见 [decision-submit-notification](decision-submit-notification.md)。

## 6. 配置名

只报告变量名和脱敏状态，不读取/输出值：

- LLM：`AI_REVIEW_LLM_API_KEY`、`AI_REVIEW_LLM_MODEL`、`AI_REVIEW_LLM_API_URL`、`AI_REVIEW_LLM_API_STYLE`、`AI_REVIEW_PI_MODEL`、`AI_REVIEW_MAX_ATTEMPTS`、risk threshold。
- TeamCity：`COMPILE_TC_BUILD_TYPE`、`COMPILE_TC_TIMEOUT_POLLS`、`AI_REVIEW_TC_CALLBACK_BASE/TOKEN`、chain retry max/delay。
- P4 submit：`AI_REVIEW_P4USER/P4PASSWD/P4PORT/P4CLIENT/P4CHARSET`、client roots、auto-resolve。
- 决策：self-approve、auto-approve 的 enabled/max-risk；jury config 在 DB。
- 通知：platform URL、group chat ID。

当前源码存在 credential fallback 风险时，只报告“文件/变量含硬编码凭证，需迁出并轮换”，绝不复制值到 skill、日志、plan、测试或消息。

## 7. 测试入口

主要测试位于 `pyAutomation/backend/tests/unit/ai_review/`，覆盖：

- create/request/reopen/refresh/terminal freeze；
- decision/approve gate/self/auto/strict jury；
- AI worker、kick、tc_inflight、callback、chain skip/failure、merge gate；
- submit queue、fail-closed、progress、auto-merge、真实隔离 p4d；
- notification/comment/no-review-channel；
- P4 adapter、diff cap、submit validation。

相关 gate 测试位于 `tests/unit/p4_trigger_validate/`；RequestReview 客户端测试位于 `tests/unit/test_request_review*.py`；TeamCity DSL 有独立结构/步骤测试。

先跑与改动直接相关的定向测试，再按风险决定完整 AI Review suite。测试进程不得连接生产 DB/P4/通知/callback；任何真实集成动作都需用户单独授权。

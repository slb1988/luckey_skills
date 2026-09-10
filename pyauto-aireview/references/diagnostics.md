# AI Review 证据化排障

## 1. 先回答“用户给的是同一单吗”

常见输入同时包含 Dashboard Review URL 和 TeamCity build URL。第一步不要分析耗时，先建立映射：

| 字段 | 获取位置 |
|---|---|
| Review ID | Dashboard path、详情 API |
| 原/当前 CL | Review详情、activities `cl_submitted` |
| Flow build ID | `compile_build_id/url`、`compile_started` activity |
| TaskAiReview build ID | Flow 的递归 snapshot dependency |
| callback Review ID | Task build startProperties 的 `env.AI_REVIEW_CALLBACK_URL` |
| Agent/stream/CL | Task startProperties、agent、log、manifest |
| config revision | build `versionedSettingsRevision` |

如果 callback 的 `review_id` 与用户 Dashboard ID 不一致：

1. 明确指出两个链接错配；
2. 分别找到各自真实对象；
3. 分两条时间线回答；
4. 不把一个 build 的 Pi timeout归到另一 Review。

完整 callback URL含 secret/nonce，只解析白名单字段，禁止原样粘贴。

## 2. 证据收集顺序

### 2.1 业务 API

先读：

```text
GET /ai_review/reviews/<id>
GET /ai_review/reviews/<id>/activities
GET /ai_review/reviews/<id>/ai_summary
```

关注：status、cl/cl_type、ai_status/source/verdict/risk、compile status/build URL、submit_progress、request_options、活动时间和 payload。

若 API 不足，再由 `@auto-server` 做只读 DB/log查询。不要从当前源码假设生产 schema已经迁移。

### 2.2 TeamCity

使用 `teamcity-tool` 认证约定和环境 token，不把 token写入命令历史、报告或 skill。

```text
GET /app/rest/builds/id:<BUILD>?fields=id,buildTypeId,state,status,queuedDate,startDate,finishDate,agent(name),versionedSettingsRevision(version),startProperties(property(name,value))
GET /app/rest/builds/id:<FLOW>/snapshot-dependencies?fields=build(id,buildTypeId,state,status,startDate,finishDate,agent(name))
GET /downloadBuildLog.html?buildId=<BUILD>
GET /app/rest/builds/id:<BUILD>/artifacts/children/Saved/ai_review
```

REST直接依赖不一定是完整链，递归展开到 Sync。配置页面的 Agent条件不能替代具体 build 的实际 Agent/startProperties。

### 2.3 构建 artifact

下载本轮：

- `runner_manifest.json`；
- `pi_session.jsonl`；
- `pi_out.txt` / `pi_err.txt`；
- `result.json`；
- `merge_result.json`；
- `build_log_tail.txt`；
- `build_log_analysis.txt` + meta/provenance；
- `review_input.md`，仅在需要核输入时读取，避免无谓暴露代码。

核对 build ID、CL、stream、生成时间和 sidecar。workspace目录里的同名文件可能已被后续 build覆盖。

### 2.4 Agent 机器

只有剩余问题属于本机环境时才派 `@winbuilder...`：

- TeamCity agent服务账号；
- 实际 Pi/Node/Python/P4 路径与版本；
- `NODE_WORKSPACE`、P4 client Root；
- agent/build日志；
- 本轮进程和本地 artifact；
- 到 TeamCity/backend/model gateway/Memory的连通；
- effective mode/model/thinking，凭证只报 present/source。

不要让远程 agent回显 settings中的 key、callback URL或整个 environment。

## 3. 时间线方法

统一到一种时区，建议同时保留原始时间与 `+0800`：

```text
T0 Review created
T1 AI job kicked/claimed
T2 Flow trigger accepted
T3 Flow真正入队/获得Agent
T4 Sync start/end
T5 Unshelve start/end
T6 Build/AS/report start/end
T7 Collect start/end
T8 Memory bootstrap start/end
T9 Pi 每条message/tool/API attempt
T10 Publish/callback
T11 backend fallback attempts/backoff
T12 decision
T13 submit job queued/claimed/P4 receipt
T14 DB submitted/notification/client closure
```

对每段给：duration、上一动作、下一动作、组件、证据。没有 activity不等于没执行；可能是 HTTP请求内、退避、已 failed等待人工，或记录被新轮 reset覆盖。

## 4. “慢”问题分类

### A. Review创建后长期没有 Flow ID

查：

1. `ai_review_jobs.status/stage/next_retry_time/attempt_count`；
2. kick与60秒 ticker日志；
3. branch busy门的旧文档是否误导——现行源码已移除；
4. `_chain_skippable` 是否纯二进制；
5. Review是否终态或 job被 terminal guard关闭；
6. TeamCity trigger 404/配置 ID错误；
7. `tc_inflight` stale recovery。

不要看到页面旧“排队”文案就认定 TeamCity queue。

### B. Task build 显示 queued 很久

比较本 Task start与前置 Task finish：

- 同秒/紧邻：snapshot sequencing；
- 前置已结束但无 compatible agent：参数/requirement/pool/root；
- 有 compatible agent但 busy：真实资源排队；
- Flow是 COMPOSITE：其 Agent空白正常。

### C. Pi step 20 分钟左右、0 tokens

`pi_session.jsonl` 若每隔固定约 5 分钟出现 `Request timed out`，且每次 0 output/input token或无 assistant内容：

- 耗时是 provider/gateway请求 timeout和 retry；
- 不是模型 thinking；
- 不是代码检索；
- 再看 Memory bootstrap是否先固定超时；
- 对照同 Agent前后成功 build，排除机器；
- 由 `@auto-server` 查 gateway/upstream request history确定最后一跳。

若 proxy进程 uptime正常，只能先定位“proxy到upstream故障域”，不能直接断言具体上游。

### D. Pi step 接近 1800 秒整

查 manifest：

- hard timeout是否触发；
- 最后一个 session event；
- provider request是否仍在飞；
- turn guard是否 armed/terminated；
- 子进程树是否被 taskkill；
- stdout/session字节是否持续增长。

### E. 工具调用耗时

历史允许 grep/find时，无 path 的全树扫描会遍历大型 P4 UE workspace并卡数分钟到30分钟。现行工具应限制为 read/ls/memory_search；若日志仍出现 grep/find，优先查运行的 DSL/Runner revision或扩展工具面，而不是优化模型 prompt。

### F. Memory 慢

manifest区分：injected、timeout、401、quality rejected、empty。Memory超时与模型超时同时发生时，查它们是否共享同一 gateway/upstream；但不能仅因同一主机就自动认定同根因。

## 5. “失败/卡住”症状矩阵

| 症状 | 首查 | 常见归因 |
|---|---|---|
| `Unknown option: --` | agent服务账号下 `pi --version`、manifest argv | 构建机 Pi版本偏旧 |
| build SUCCESS，Review仍无结果 | result/callback activity、nonce、Publish log | error降级、callback warning-only、旧代际 |
| `verdict=error` + `pi_out`空 | `pi_err`、session、manifest | provider timeout、argv、setup、process kill |
| Review显示编译失败但 Build没跑 | snapshot根失败、need_compile | Sync/Unshelve失败被误读；看当前 chain归因 |
| 错误数0但日志很多 | analyzer读取的build ID | 误读 composite而非BuildUE/失败Task |
| warning完全不见 | `build_log_analysis*` provenance | informer没跑、报告missing/stale、same-file copy |
| Collect `STREAM_MISMATCH` | shelf完整文件集、target stream | 整单不含目标stream；mixed stream会skip外部文件 |
| merge clean但代码像旧版 | merge_result、baseline、`resolve -N` | have回退、resolve空跑、证据不匹配 |
| Unshelve秒挂 `exclusive file` | 失败文件、`p4 opened -a` | 作者client仍持有+l锁 |
| Collect拒绝工具自身改动 | shelf是否打开`Tools/AiReview/` | self-modification guard，需人工受信流程 |
| Review反复 fallback | callback非定案或没到、backend LLM | Pi error/skipped，fallback同故障域 |
| approve后长时间approved | submit_progress/job/activity/P4 CL state | 队列、明确失败、manual_required、进程中断 |
| 原CL missing | P4明确回执、filelog、actual submitted CL | rename成功、删除或未知；禁止猜最近CL |
| retry_submit没动作 | submit job/manual marker/current status | 未知结果需先人工对账 |
| approve后立即rejected | participants与同秒activities | reopen残留author veto/strict jury |
| 用户能直接P4 submit | trigger payload user、review gate | bot-only放行边界错误或分支规则未命中 |
| 页面一直显示旧排队文案 | `ai_queue`投影与源码 | 已退役busy UI/缓存，不代表现行worker阻塞 |

## 6. 提交问题排障

按顺序：

1. Review当前 status必须重新读；
2. 找当前 approved round边界；
3. 读 `submit_progress` 和 `ai_review_submit_jobs`；
4. 读本轮 `cl_submitted` activities；
5. 只读查原CL/可能actual CL的明确 P4状态；
6. 查 submit worker claim/domain/stale recovery；
7. 区分：queued、running、明确failed、manual_required、P4成功但DB未收敛；
8. 未唯一确认前不 retry、不 reject、不改 DB。

常见 P4分类：

- +l/open-files；
- out-of-date需auto-merge；
- deterministic conflict；
- stream client不映射target；
- submit回执不完整；
- CL rename；
- DB unique/CAS竞争；
- 作者署名恢复软失败。

P4 warning可能包含真正逐文件错误，而异常对象只有汇总行；诊断代码需同时收集 warnings，但输出仍要脱敏。

## 7. Diff/输入可信度

任何“AI漏看/误判”先回答：

- 本轮分析了哪些文件？哪些SKIPPED？
- baseline是什么？
- merge_result与TaskUnshelve build匹配吗？
- warning/error报告 fresh吗？
- prompt注入了哪个 `pl-review`/模块规则版本？
- Pi允许读哪些路径？
- artifact是否被后续构建覆盖？

输入缺证时不要先调模型 prompt；先修采集/认证。风险0也可能只是空输入或降级路径。

## 8. 安全的只读 SQL 取证形态

仅在已授权生产只读会话中，由 `@auto-server` 执行白名单 SELECT；不要在聊天中传连接密码：

```sql
SELECT id, cl, status, ai_status, compile_status, compile_build_id,
       ai_result_source, ai_verdict, create_time, update_time
FROM ai_reviews WHERE id = <review_id>;

SELECT id, event_type, payload, create_time
FROM ai_review_activities
WHERE review_id = <review_id>
ORDER BY id;

SELECT id, stage, status, attempt_count, retry_count, next_retry_time
FROM ai_review_jobs WHERE review_id = <review_id>;

SELECT id, workspace_key, status, attempt_count, started_time, finished_time
FROM ai_review_submit_jobs WHERE review_id = <review_id>;
```

若 schema与查询不符，停止并核部署 migration，不临时改表适配查询。

## 9. 最终报告模板

```text
结论一句话
- 用户给出的对象是否同一 Review
- 最长耗时在哪个组件，不在哪些组件

身份映射
- Review / original CL / current CL
- Flow / Sync / Unshelve / Build / TaskAiReview
- Agent / stream / revision / callback review_id

时间线
- 每阶段 start/end/duration
- 最长静默窗口的上一动作和下一动作

根因
- 已确认机制（证据）
- 最可能基础设施归因（置信度）
- 独立并发问题（不要混在主因）

恢复与修复
- 当前单如何安全收口
- 代码/配置修复归属哪个 ws
- 需要哪个 @agent 做什么补证
- 未经授权没有执行哪些动作
```

# Memory Hub 检索 Eval 流程

## 目标与边界

评价的是“历史记忆是否帮助 agent 正确回答”，不只看 search 是否返回非空。默认只读：
不写 production memory，不 reingest/reindex/delete，不改生产 `.env`，不部署或重启服务。
评估 session 设置 `MEMORY_HUB_SKIP_CAPTURE=1`，避免测试问答回灌为新记忆；同时设置
`MEMORY_HUB_RECALL=0`（Claude/Codex）/ `MEMORY_HOOK_PI_BOOTSTRAP_RECALL=0`（Pi），
避免首轮自动预热的注入干扰评估变量。

评估仓库：`D:\Github\memory-hub`；黄金集在 `tests/eval/`，报告输出到 gitignored 的
`data/retrieval-eval/`。首次进入先确认 `.env` 的 `MEMORY_HUB_ENV`：dev 才运行开发/评估；
release 只做明确授权的运维。

## 标准流程

1. 选一个中等规模 project 做 pilot，再跨一个基础设施项目和一个业务项目复核。
   当前推荐顺序：`admin_sun_depot_7184` → `memory-hub` → `maindev`。
2. 冻结 case：query、project、expected memory/group、黄金答案、难度和 scope 类型。
3. 跑 v1 baseline 与 v2 candidate；保存 JSON + Markdown，不修改 judgment ID 空间。
4. 对关键失败逐条做“存错/取错”诊断（见下一节）。
5. 用真实 Pi 做成对测试：首次 bootstrap-only 与仅开放一次 `memory_search`；记录 session id、
   cwd/project、query、工具耗时、注入字符数、模型 token/成本、答案与人工评级。
   **每一回合开始前先轮转 trace**：`python scripts/rotate_pi_trace.py`（需要脚本侧视角时加
   `--include-hook-trace`），把旧的 pi-trace.jsonl 移到 state dir 的 `trace-backups/`，
   保证当轮 trace 只含本轮事件，逐 case 分析不被历史记录污染。
6. 先过小项目 answer-level 验收，再扩大 golden/project；指标退化时停止全量发布。

## 存错还是取错

对每个失败 case 固定按以下顺序查：

1. expected memory 是否存在、status 是否 indexed、group/project 是否正确。
2. `GET /v1/memories/{memory_id}` 的 `distilled_content` 是否包含黄金答案（数字、路径、配置、
   决策条件）；只记录布尔命中和必要短片段，不复制凭据或无关 session 正文。
3. 原文没有答案：归类为 capture/蒸馏/低价值过滤/错误 project 的写侧问题。
4. 原文有答案而 v1 没有：归类为 Graphiti 实体边抽取或排序损失。
5. 原文有答案而 v2 FTS 也没有：检查 query token、FTS 索引、status、scope/group、top-K 截断（服务端同款 MATCH + FTS SQL 直查复现法见 [troubleshooting.md](troubleshooting.md)）。
6. v2 已把答案片段返回但 agent 答错：才进入本地模型结构理解、排序或 rerank 问题。

代表性证据（2026-08-29）：`maindev` memory
`01a043eb-b994-7ecb-bd36-49aec0e282aa` 的正文完整包含
`SyncStaticMeshAssetMetaDT`、删除 10 行、最终 214 行；v1 只返回工具机制，属于取错，
不是存错。超时配置与 thinking 配置两个成功 case 的原文也完整。

## 运行命令

先验证黄金集格式：

```powershell
python scripts/eval_retrieval.py --golden tests/eval/golden.admin_sun_depot_7184.canary.jsonl --validate-only
python scripts/eval_retrieval.py --golden tests/eval/golden.memory-hub.canary.jsonl --validate-only
python scripts/eval_retrieval.py --golden tests/eval/golden.maindev.sample.jsonl --validate-only
```

生产只读 v1 baseline：

```powershell
python scripts/eval_retrieval.py --golden tests/eval/golden.admin_sun_depot_7184.canary.jsonl
```

runner 默认单请求故障上限为 120 秒，与 Agent 召回一致；这不是性能目标，p95/p99 门禁仍按下文执行。
报告 run id 含微秒，批量运行多个 golden 即使同秒结束也不会互相覆盖。Pi 真实评分导入 judgment 时
必须匹配同一 normalized query，禁止把某条 memory 在问题 A 下的评分套到问题 B。

本地 candidate v2：

```powershell
python scripts/eval_retrieval.py --api-version 2 --base-url http://127.0.0.1:9287 --golden tests/eval/golden.admin_sun_depot_7184.canary.jsonl
```

runner 在 `--api-version 2` 时必须显式发送 `quality_mode=retrieval`，只衡量检索器并保持历史
MRR/Noise 可比；在线 hook 则使用服务端默认的 `quality_mode=llm`。两类报告不要混算。

详尽 schema/runner 说明以 `D:\Github\memory-hub\tests\eval\README.md` 为准。

## 指标与 answer-level 评级

- 排名指标：StrongHit@5、AnswerHit@10、expected-memory Recall@K、MRR/nDCG、Noise@10。
- 覆盖度：judgment pool coverage < 0.9 时只报告 pilot，不冻结回归结论。
- 延迟：p50/p95/p99/max；120 秒是故障上限，不是期望延迟。
- 真实答案：完整回答 / 部分回答 / 关键结论漏召回 / 错答或幻觉。
- 安全拒答单列：不算完整命中，但优于编造。
- token/时间：记录检索输出字符数与模型 input/output/cache；2026-08-31 起生产候选最多 3 条、
  每条约 1200 字，不因“更多记忆”无限扩大上下文；旧报告仍可能有 4–5 条。

门禁至少要求：answer-level 不退化、关键 golden answer 命中；Recall@5 下降超过 2pp 或
Noise@10 明显上升即暂停推广。v1 `fact:*` 与 v2 `memory:*` 是不同 ID 空间，coverage=0 时先查
标注契约，不能把它解释为所有 query 都搜不到。

## LLM 使用原则

在线 Agent/hook 固定使用后端 LLM 质量门禁：一次请求把至多 10 条结构化候选批量判 0-3 分，
只返回 2/3 分；审核失败时 503 fail-closed。每条详细判断进入 `retrieval_judgments`，定期分析
rating/rationale/evidence/conflict 与人工 judgment 的差异，同时报告 token、延迟和失败率。

直接查 SQLite（`/share/Container/memory-hub/data/memory-hub.sqlite3`）时注意：评分列实际名为
`llm_rating`（不是 `rating`），其余关键列为 `candidate_rank` / `result_id` / `memory_id` /
`rationale` / `evidence` / `conflict` / `status`（正常值为 `completed`）；按 `retrieval_id` 过滤。
对在线生产库做只读分析时，先把 sqlite3 文件复制到临时副本再查询，查完清理，不直接打开在线库。
离线检索 eval 必须用 `quality_mode=retrieval` 排除 LLM，另做“检索器”和“端到端放行结果”两层指标，
避免 LLM 把召回缺陷掩盖成漂亮的 Noise 数字。

## 部署验收 known-good smoke 向量

<memory category="debug-commands">
**search-v2 部署验收 known-good smoke 向量**（commit 45c96f9「Keep three structured memory candidates」验收实测通过）：`project=maindev, query=SyncStaticMeshAssetMetaDT, limit=10` → 预期 HTTP 200、memory `01a043eb-b994-7ecb-bd36-49aec0e282aa`（source_type=`memory_document`）排第一。fusion 结构化 memory 候选保留口径：2026-08-31 起候选充足时固定保留 top-3、`policy_version=v2-fts-top3`；**unpruned 候选不足 3 条时 pruned == unpruned，不会补齐**（该向量实测 unpruned=2 → pruned=2，stats 全 0，属正常行为不是 bug）——验收时不要用「pruned = 3」做无条件断言。

该向量曾因 feedback bug 数据损害暂时失败，2026-08-30 hotfix e081453 部署+数据修复后已恢复（`01a043eb` 重回第一，unpruned=2）。search-v2 响应中无独立 `pruned` 字段——fusion 只暴露 `memory_candidates_unpruned` 与 `memory_candidates`，实保留数看后者（unpruned=2 → candidates=2 即零裁剪）。第二 known-good 向量（5a9366f 验收实测通过）：`project=admin_sun_depot_7184, query="Stable 和 MainDev 的真实自动合并方向是什么，前端虚线为什么显示反了？", limit=10` → HTTP 200、4 条结果、首条 `01a0463e`。
</memory>

## 纠错召回验收：rescue 进 pool 与 judge 裁决是两个独立分层（ee4df3e 实证）

<memory category="common-patterns">
**纠错记忆验收不达标时先分层定位：rescue 是否把纠正候选送进 judge pool、judge 是否执行替代规则——两层根因不同、修法完全不同，不要把 judge 失败误判成检索失败去回滚 rescue 机制**。commit ee4df3e「rescue explicit memory corrections during rerank」定版机制：词面 top-8 之外，`correction_hint=True` 的候选最多再补 2 个槽位进 judge pool（policy_version=`v2-fts-judge10-llm`，质量门禁 candidates=10 → kept=2，min_rating=2）。2026-08-31 生产验收实证（project=admin_sun_depot_7184）：纠正 memory 词面 RRF rank=9（top-8 之外）仍两次稳定以 rank 9 进入 judge pool——rescue 按设计生效。已知 judge 失败模式：judge LLM（kimi-k3）在 `conflict` 字段已正确识别语义冲突（"rank1 针对数值更新，本条针对 schema 变更"），但不执行 prompt 的替代（supersede）规则，反把纠正判 rating=1 被 min_rating=2 过滤，旧错误 memory 仍以 rating=3 排第 1。判读方法：只读查 `retrieval_judgments`——纠正候选在 pool 内但低 rating = judge 层失败，**不是 rescue/检索失败**；后续杠杆是强化 judge prompt 替代规则、换 judge 模型、或对同批 conflict 对强制成对比较。另：`quality_mode=llm` 的 search-v2 批量判 10 候选实测单次 34–64s（4453dde 验收观测，含 63.8s 上限样本），验收脚本/回执的超时预算要按 ≥70s 留余量，不要套 retrieval 模式的预期。
</memory>

<memory category="troubleshooting">
**search-v2 judge 间歇 503 `RETRIEVAL_JUDGE_*`（4453dde 验收实测约 50%，8 次调用 4×503/4×200）的根因是 judge `max_tokens=1600` 被 kimi-k3 的 thinking 吃光（实测单次 thinking 达 2578 tokens），JSON 输出中途截断——不是检索层也不是 prompt 规则逻辑问题**（2026-09-01 部署 4453dde 后实证）。伴随症状是判分漂移：judge 时而拿 query 字眼（如「数值」）当借口给被纠正的旧答案 rating=3 放行，违反新 prompt 的替代规则；token 预算修复前不要把漂移误判成 prompt 规则失效或回滚 rescue，修复方向是 judge max_tokens 提到 ~6000 或网关侧禁 thinking，修后必须重跑纠错验收向量确认稳定性。4453dde 验收正面事实：correction_evidence 已确认实际注入 judge 输入（502 字符窗口，含标准流程与本机验证记录），且存在完全达标样本（纠正候选唯一保留 rating=3、旧错 rating=0 被过滤）——功能达标、稳定性未达标，两者要分开报。
</memory>

<memory category="troubleshooting">
**0e54ce8（SCHEMA 6→7）发布在 pytest 门禁被一条断言脆弱性卡住，不是功能回归**：`tests/unit/test_retrieval_fts.py::test_search_v2_llm_quality_gate_scores_every_candidate_and_persists_details` 用 `== 110.0` 严格断言 judge `timeout_seconds`，而实际值是浮点 deadline 计算结果 109.99999276082963（~7µs 误差）；compileall 通过、同批其余 45 用例（migrations/judge/llm_client）全过。修法：`pytest.approx(110.0)` 修断言后推新 commit 重走发布，不要为过门禁删改其他测试。该发布的质量验收向量（门禁通过后执行，用户定版）：`project=admin_sun_depot_7184, query='admin_sun_depot_7184 pyautomation 后端一般如何更新 model 数值', limit=6, quality_mode=llm` 连续 5 次相同查询——须 5/5 HTTP 200、纠正 memory `01a0576b-2a32-7275-bb07-62fcdf8ad53e` 5/5 返回、旧错 `01a0576b-2674-7e2d-8bec-2d6538b081fa` 5/5 被过滤；judge 正确性只读汇总 `retrieval_judgments` 的 rating/intent/conflict/evidence，不回显候选正文。
</memory>

<memory category="troubleshooting">
**068a2c7 部署本身全过但上条 5× 纠错验收 0/2 失败，根因仍在 judge 层且新增「评分抖动跨阈值」证据**（2026-08-31 NAS 生产实证）：schema_migrations=7、`retrieval_judgments` 有 intent 列、46 单测全过、policy=`v2-fts-judge11-llm`；连测结果——旧错 `2674` 5/5 以 rating=3 排 #1（judge 把「更新 model 数值」按「ORM 改行值」语义解读，与旧错表面吻合，未触发降级闸），纠正 `2a32` 仅 2/5 返回。新现象：**同一 query 连跑，纠正候选 rating 在 1↔2 间抖动（3×1 被 min_rating=2 过滤、2×2 保留）——judge 注意到 correction hint 但解读不稳定，5/5 稳定性验收在 judge 修复前天然不可达，不要因单次达标样本误判已修复**。intent/evidence 输出正常无臆造；known-good 向量（SyncStaticMeshAssetMetaDT）仍排第 1。结论不变：在线判分问题而非检索/部署问题，不要回滚部署或改 rescue，杠杆在 judge prompt 强制识别 correction 替代关系、换 judge 模型或成对比较。
</memory>

<memory category="troubleshooting">
**只读 LLM 纠错裁决探针实证：kimi-k3 `thinking={type:disabled}` + max_tokens=500 可 5/5 稳定输出严格 JSON（单次 3.9–7.8s），且 2a32 的 correction_evidence 数据本身可裁决——此前 5× 纠错验收失败的根因进一步锁定在 judge 集成层（token 预算/thinking），不是证据数据不足**（2026-09-01 NAS 生产实证，全程只读）。判读「更新 model 数值」query：5/5 applies=true、corrected_term=「更新 model 数值」、resolved_intent=Flask-Migrate/Alembic schema 发布流程、old_answer_superseded=true（旧 ORM「改行值」答案答非所问）。对照前两条 judge 失败模式：「禁 thinking」修复方向获直接证据——thinking enabled 时单次 34–64s 且 max_tokens=1600 被 thinking（实测 2578 tokens）吃光截断；disabled 时 500 tokens 即充裕。探针构建方法：复用服务端 helper `explicit_correction_evidence()` 取纠正 memory 的 502 字符证据窗、`memory_excerpt()` 截 1200 字符取旧 memory 摘要，不写 judgment、不调 search-v2、不回显正文，严格 JSON schema {applies, corrected_term, resolved_intent, old_answer_superseded, rationale} 连跑 5 次独立解析。可重跑脚本留存 NAS `/tmp/memory_hub_llm_probe.py`（不含凭据/正文）。
</memory>

## 纠错验收结案：judge12 修复生效，`attempts` 字段是 resolver 触发的判读信号（22f9fb7 实证）

<memory category="common-patterns">
**commit 22f9fb7（policy_version=`v2-fts-judge12-llm`）生产验收 5/5 通过，前述 judge 失败链（token 预算/thinking/评分抖动）结案**：纠错向量（`admin_sun_depot_7184` / 「更新 model 数值」/ limit=6 / quality_mode=llm 连跑 5 次）5/5 HTTP 200，纠正 `01a0576b-2a32-7275-bb07-62fcdf8ad53e` 5/5 返回且唯一保留（candidates=10 → kept=1），旧错 `01a0576b-2674-7e2d-8bec-2d6538b081fa` 5/5 被过滤；judge 已正确执行替代规则——纠正 rating=3、intent=Flask-Migrate/schema 发布语义、rationale/evidence 有显式纠错留痕，旧错 rating=0、conflict 标记被较新纠正 superseded。**新判读信号：judgment `attempts` 暴露管线级数——纠错 query attempts=2（resolver+judge 两阶段），known-good（maindev/SyncStaticMeshAssetMetaDT）attempts=1；known-good 回归断言 attempts=1 即证明普通请求未触发 resolver、无额外 LLM 调用**。实测 llm 单次 32–73s，出现超出此前 ≥70s 预算的样本（73s），验收超时按 ≥80s 留余量。验收留痕存 NAS `data/acceptance-<short-sha>/`。

定版机制：仅候选池含 `correction_hint` 时，用 thinking-disabled、max 500 output tokens 的 resolver 比较原 query、纠正原句与词面 top-3 alternatives，输出 resolved intent / correction rank / superseded ranks；corrected term 必须实际存在于 query，非法或不可用即 503 fail-closed。主 judge 改用 resolved intent，服务端确定性把纠正 rank 置 3、被替代 rank 置 0，并把原文 evidence、替代 conflict 与最终 intent 落库。该 case 两条 memory 都已 indexed 且纠正正文完整，FTS 原始 rank≈12、rescue 后 judge rank=9，所以完整故障链是“先取不到、后判不对”，不是后来会话未学习。本机 Pi 同链路 27.1 秒生成 `20260831T164115Z-smoke-flask-migrate-judge12-01a058b1-f8f5-76f6-bc30-750c5256e495.md`，摘要“Flask模型更新与数据库迁移”，含纠正 ID、不含旧错 ID。验收不得只抽一次成功样本，至少同 query 连跑 5 次并核对两条 judgment。
</memory>

## f9ca0bc（schema v8 写入侧事实演进关系）验收：当前问法通过，历史问法召回未证实（2026-09-01 实证）

<memory category="troubleshooting">
**commit f9ca0bc（SCHEMA 7→8：memory_relation_analyses + memory_relations 两表，graphiti overlay 新增 POST /memory-relations 写端点）生产部署验收通过，但「历史问法仍可查回旧 memory」未证实，且 resolver 有偶发 503**（2026-09-01 NAS 实证）：全量 pytest 247 passed、schema_migrations=8、pilot 关系分析 51s completed（SUPERSEDES 边真实落入 Neo4j 两端 Episodic 之间，`graphiti.add_memory_relation` outbox completed；高思考单次分析可到 180s，轮询不要提前判超时）。overlay 源码唯一出处是 memory-hub 仓库 `deploy/graphiti-0.22.0/routers/retrieve.py` + `dto/retrieve.py`，同步到 memory-center 生产 patch 路径后 bind mount 进 prod graphiti(:8005)；candidate 实例(:8015)已确认**无**该写端点，不要给它加。新验收向量（当前问法）：`project=admin_sun_depot_7184, query='admin_sun_depot_7184 pyautomation 后端现在应该如何更新 model 数值？', quality_mode=llm, limit=10` → HTTP 200、kept=1 仅新 memory `01a0576b-2a32-…`、旧 `…2674…` rank2 rating=0 且 conflict 标注被显式替代、policy 含 `judge13-evolution`。**两条已知未裁决缺陷**：① 历史问法（'以前错误的 model 数值更新做法是什么？'）下旧 memory 未进 FTS top-30 候选池、resolver 把历史意图改写为当前意图——SUPERSEDES 后旧 memory 物理保留完好（status=indexed、Neo4j 节点与入边均在），按历史意图的检索召回**当时未被证实**——**已于 ce3efee 部署验收（2026-09）闭环证实**：同一历史问法 HTTP 200，旧 memory `…2674…` rank 1（rating 3）保留、纠正 `…2a32…` rank 2，历史意图召回正常；② resolver 偶发 503 `RETRIEVAL_CORRECTION_RESOLVER_INVALID_RESPONSE`（fail-closed），重试即恢复，属已知抖动不是部署回归。
</memory>

## ce3efee 验收：known-good 向量 rank-1 断言在 quality_mode=llm 下天然抖动（2026-09 实证）

<memory category="troubleshooting">
**known-good 检索验收不要断言「期望 memory 排第 1」，只断言 presence + HTTP 200 + attempts=1 + 零 resolver 错误**（ce3efee 部署验收实证）：maindev / `SyncStaticMeshAssetMetaDT` / limit=10 单次，期望 memory `01a043eb-b994-7ecb-bd36-49aec0e282aa` 在场但 rank 2——judge 给竞争候选 rating=3、期望 rating=2，纯 LLM 排序波动，HTTP 200 且无任何错误码。同批 62 条 retrieval_judgments 全 completed、零 `RETRIEVAL_CORRECTION_RESOLVER_INVALID_RESPONSE`/unparseable resolver 失败（此前 f9ca0bc 记的偶发 resolver 503 本次零复现，「已知抖动非回归」结论不变）。rank-1 未达不是部署回归、不构成回滚依据；对照纠错向量（5/5 通过）与 known-good 的 attempts=1（未触发 resolver）即可区分 judge 排序抖动与真实检索故障。

**事后根因诊断（2026-09-01 只读专项）把「纯排序波动」细化为「裸标识符 query 歧义」**：该 retrieval 的 FTS BM25 期望 8.573 > 竞争 7.033、fusion RRF 也第一——检索器始终排对，是 judge13 对裸工具名 query 认为「工具概览」memory 更贴合意图（rating 3 vs 期望 2），属可辩护的意图歧义、不是 judge 错误；同一 project 换 answer-level 问法「SyncStaticMeshAssetMetaDT 删除了多少行，最终还剩多少行？」连跑 3 次 quality_mode=llm，3/3 期望 rating=3 排第 1、竞争者 rating=1 被过滤（单次 6.2–7.3s）。**rating 顺序/rank-1 类断言只对 answer-level 自然语言问法有效；裸标识符 query 只断言 presence**。两候选关系为 complementary（各有独有内容），非 duplicate。
</memory>

## 候选 K 离线门禁

修改服务端候选上限前，必须用现网完整返回做离线前缀模拟，不要反复部署试阈值：

```powershell
python scripts/eval_retrieval.py --api-version 2 --result-limit 3 --golden tests/eval/golden.admin_sun_depot_7184.canary.jsonl
python scripts/eval_retrieval.py --api-version 2 --result-limit 3 --golden tests/eval/golden.memory-hub.canary.jsonl
python scripts/eval_retrieval.py --api-version 2 --result-limit 3 --golden tests/eval/golden.maindev.sample.jsonl
```

`--result-limit` 不改变服务端请求，只对融合结果前 N 条计分，报告会记录该值。2026-08-31 的
K=3 定版证据：三组 StrongHit、AnswerHit、expected Recall@3 均为 1.0；Noise 分别从
0.25/0.267/0.20 降至 0.208/0.167/0.167，平均候选约减少 31%。K=1/2 会让 admin 或 maindev
丢完整答案，因此不准在现有证据上进一步收紧；允许 1–2 条或空结果必须先积累单独的 no-answer
标注集。

## 写侧关系分析候选 K（memory_relation_analyses）前缀统计

<memory category="common-patterns">
**写侧关系分析的 candidate K=10 不要凭直觉下调——现网前缀统计（2026-09-01，ce3efee 后生产库临时副本只读聚合 result_json）显示约 1/5 关系边来自 target_rank>3**：69 条 completed analyses / 73 条 relations，50/69（72%）跑在 candidate_count=10；target_rank >3 有 14/73（19.2%）、>6 有 5/73（6.8%）、>8 有 3/73（4.1%）；SUPERSEDES（n=11，stale-fact 替代这个最关键类别）>3 有 2 条、>6 有 1 条，最远落在 rank 10。K 从 10 砍到 6 会损失 ~7% 关系边且恰好牺牲 SUPERSEDES 长尾，当前证据不支持收紧；要调 K 必须先重跑同一聚合确认长尾占比已下降，不要部署试阈值。
</memory>

## 写侧关系分析 excerpt 预算定论：维持 new=6000 / candidate=2400，自适应分档已被离线模拟否决（2026-09 实证）

<memory category="common-patterns">
**memory evolution 写侧 excerpt 预算（新 memory 6000 字符、每个 candidate 2400 字符）已实证 100% 保留全部 accepted 关系证据，不要收紧**（2026-09 ce3efee 生产库临时副本只读审计：67 completed analyses / 73 relations，基线 73/73 new+old evidence 全保留）。三档自适应/收紧方案全部不达标：P1 保守分档（6000；rank1-3=2400、4-6=1800、7-10=1400）保留 100% 但总 excerpt 字符仅省 8.1%（p50 6.4% / p95 13.8%）——**多数 distilled_content 本就短于 cap，按 rank 收紧几乎咬不到字符**；P2 中度（5000；2000/1600/1200）省 12.3% 但丢 3 条关系证据、含 1 条 SUPERSEDES；P3 统一（5000；全 1800）丢 2 条。丢失全部是 old_evidence 落在更紧的 candidate 摘要之外（rank-1 与 rank-10 候选）。无方案同时满足 100% 保留 + ≥15% 节省，结论：保持 6000/2400；将来要重提收紧，必须先重跑同一离线模拟证明 distilled_content 长度分布已变。审计方法两条铁律：① 证据校验必须直接复用服务端 `memory_hub.application.retrieval.memory_excerpt` 原函数与 `parse_memory_evolution` 的 normalization/ellipsis 语义，自写近似会误判保留率；② 节省估算必须逐 candidate 重算实际摘要长度，禁止用 cap 直接相乘。写侧成本规模参考（45 条 organic post-deploy analyses）：candidate 来源 fts-only 236 / fts+graph 101 / graph-only 77 / recency-only 0，candidate_count p50/p95=10，prompt_chars p50≈18.8k / p95≈23.1k，input_tokens p50≈6.2k / p95≈8.6k，单次分析延迟 p50 26s / p95 76s（轮询超时按此留余量）。
</memory>

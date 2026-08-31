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

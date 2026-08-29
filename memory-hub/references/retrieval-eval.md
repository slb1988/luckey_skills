# Memory Hub 检索 Eval 流程

## 目标与边界

评价的是“历史记忆是否帮助 agent 正确回答”，不只看 search 是否返回非空。默认只读：
不写 production memory，不 reingest/reindex/delete，不改生产 `.env`，不部署或重启服务。
评估 session 设置 `MEMORY_HUB_SKIP_CAPTURE=1`，避免测试问答回灌为新记忆。

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
5. 原文有答案而 v2 FTS 也没有：检查 query token、FTS 索引、status、scope/group、top-K 截断。
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

本地 candidate v2：

```powershell
python scripts/eval_retrieval.py --api-version 2 --base-url http://127.0.0.1:9287 --golden tests/eval/golden.admin_sun_depot_7184.canary.jsonl
```

详尽 schema/runner 说明以 `D:\Github\memory-hub\tests\eval\README.md` 为准。

## 指标与 answer-level 评级

- 排名指标：StrongHit@5、AnswerHit@10、expected-memory Recall@K、MRR/nDCG、Noise@10。
- 覆盖度：judgment pool coverage < 0.9 时只报告 pilot，不冻结回归结论。
- 延迟：p50/p95/p99/max；120 秒是故障上限，不是期望延迟。
- 真实答案：完整回答 / 部分回答 / 关键结论漏召回 / 错答或幻觉。
- 安全拒答单列：不算完整命中，但优于编造。
- token/时间：记录检索输出字符数与模型 input/output/cache；默认候选最多 5 条、每条约 1200
  字，不因“更多记忆”无限扩大上下文。

门禁至少要求：answer-level 不退化、关键 golden answer 命中；Recall@5 下降超过 2pp 或
Noise@10 明显上升即暂停推广。v1 `fact:*` 与 v2 `memory:*` 是不同 ID 空间，coverage=0 时先查
标注契约，不能把它解释为所有 query 都搜不到。

## LLM 使用原则

优先让现有本地 LLM 获得结构化的 `summary + excerpt + project/session/memory provenance` 后按需
判断。FTS-only 不调用 embedding/LLM，成本可预测。只有在“正确 memory 已进入候选但排序或
筛选仍持续失败”的证据成立后，才评估后端 LLM reranker；必须同时报告额外 token、延迟、
失败降级和可复现性。

---
name: memory-review
description: Memory Hub 关卡 2（抽取审核）队列的自动/半自动审核——拉取待审队列、质量检查、外科式清理预览（移除畸形边/错误归属实体）、带 rationale 留痕地批量批准/拒绝。当用户提到"审核记忆队列"、"review-extraction"、"消化审核队列"、"批准记忆入库"、"抽取审核"、"auto review 记忆"、"记忆入库审核"时触发。即使用户只说"帮我审一下记忆"、"把待审的记忆处理掉"也应触发。与 memory-hub skill 的关系：memory-hub 覆盖写入/检索/hook 运维；本 skill 专注 review pipeline 的关卡 2 处置（含关卡 1 intake 复核的入口指引）。
---

# Memory Review（抽取审核队列处置）

Memory Hub 的审核管线（详见 memory-hub skill 与服务端 `docs/REVIEW_PIPELINE.md`）在记忆写入
Graphiti 前设两道关卡。本 skill 覆盖**关卡 2（抽取审核）的批量化处置**：预览已生成、
novelty 演进分析已完成，需要人/agent 决定 approve（original/curated）还是 reject。

```text
memory → pending_intake → [关卡 1 intake 过滤] → pending_extraction → 预览 + novelty 分析
        → [关卡 2 抽取审核 ← 本 skill] → approve → outbox → Graphiti indexed
```

## 快速信息

| 项目 | 值 |
|------|-----|
| 队列页面 | `https://luckeyhome.site/memory-hub/#review-extraction` |
| 脚本 | `scripts/review_queue.py`（仅标准库，Python 3.11+） |
| 认证 | `MEMORY_HUB_API_KEY` + `MEMORY_HUB_CLIENT_USER_ID`（本机注册表已持久化） |
| 服务端代码 | 本机副本 `D:/Github/memory-hub`（改动 push 后经 @nas 部署） |
| 自动决策开关与决策留样 | v20 起三态 `off\|shadow\|auto`（默认 off，off 不产生影子 LLM 请求）；人工决策留样独立于影子 → [references/auto-review-modes-and-decision-samples.md](references/auto-review-modes-and-decision-samples.md) |

## 标准工作流

```bash
# 1) 扫描：拉队列 + 有限并发详情（上限 8）+ 确定性检查 → review_packet.json + 摘要表
#    逐完整 ID 即时进度；部分失败不发布正式审核包，只写 <输出>.incomplete.json 诊断包并非零退出；
#    返回达到 limit=200 上限时明确提示「覆盖未确定」，不能当作全队列扫描完成
python scripts/review_queue.py scan -o review_packet.json

# 2) 判断：逐条读 packet 的 distilled_content 与 proposed（实体/边），
#    结合 flags/suggestion 做决策，写决策文件 decisions.json

# 3) 执行（先 dry-run 核对，再实跑）；--receipt-file（新接口）把提交意图/逐项回执写 JSONL
python scripts/review_queue.py apply decisions.json --dry-run
python scripts/review_queue.py apply decisions.json
```
大批量批准用 `scripts/drive_approvals.py decisions.json --run-dir <目录>` 驱动（显式已审核决策含
memory_id/group_id、snapshot_token 绑定不重取、同组等 indexed、未知回执不重发、
回执/状态/日志落独立 run 目录可中断恢复）→ [批量批准驱动](references/batch-approval-driver.md)。

**判断层（agent 的活，脚本不替代）**：脚本的确定性检查只做机械筛查（自环边、预览厚度、
敏感模式、novelty 状态），以下必须逐条用判断力核对：

1. **边 fact 必须有正文支撑**：`proposed.edges[].fact` 陈述的事实要能在 `distilled_content`
   里找到出处；LLM 预览偶尔会幻觉出不存在的因果关系。
2. **错误归属实体**：worker 会话开头的 Orca 派发模板可能让 LLM 把 `orca` 抽成项目实体并
   让别的项目规则 `PART_OF orca`——这类实体用 remove 删掉（级联清边），不要带病批准。
   同理注意把"评审对象项目"和"执行工具"张冠李戴的归属边。
3. **短暂状态 vs 长期知识**：session_summary 默认是蒸馏后的长期知识（关卡 1 已过滤），
   但如果某条正文几乎全是"CL xxxx 待提交"这类短期状态，考虑 reject。
4. **同 session 多版本**：同一 session 多次更新会产生多条待审记忆，内容常有重叠。
   novelty 演进分析（SUPERSEDES/CONFIRMS/REFINES）已让它们彼此可见，判了
   novel/evolution 的通常都可批；不必因为"看着像"就拒其中一条——去重是演进链的事。
5. **content_mode 选择**：预览实体/边丰富且准确 → `curated`（Graphiti 高保真复现审核结果）；
   预览薄（0 边）但正文有价值 → `original`（保留原蒸馏文）。
6. **实体存在性标注只是参考，不是拒绝理由**（2026-09-06 起 detail 自带）：`entity_existence`
   （打开详情时实时查图谱）与 `entity_resolution`（preview 落库时的快照）标出
   已有 / 已有·近似 / 已有·多候选 / 新 / 未知。已有实体仍可能带来新边新事实——判重看
   novelty 与正文增量，不看实体是否已存在。「已有·近似」带 `suggested_canonical` 时无需
   手动改名：批准 curated 的重验会把 approved 别名/唯一候选自动改写为 canonical 并留痕。
   `ambiguous` 实体的 `llm_verdict`（map/new/uncertain + 置信度）只是建议，拿不准不要强行归并。
   空预览（0 实体 0 边）有 badge；正文有实质价值时仍可 approve `original`。

<memory category="common-patterns">
`ai-review` 在 pyautomation/TeamCity 语境指代码评审服务，不是 Memory Hub 的抽取/实体归并审核系统。
正文涉及“审核其他系统实体”时，preview 可能把被审核对象错抽成审核系统本身，继而将
`_normalize_extraction`、preview/novelty 改进等 Memory Hub 事实挂到 `ai-review`。
这是实体语义/归属错误，不是名称变体；已有/同名 canonical 不能证明归属正确，
须结合正文主题、实体摘要及边的实际属主核对，不能直接按别名合并。
</memory>

**安全红线（不可自动逾越）**：
- novelty `admission=duplicate` 或分析 `failed` → **升级人工**，不要自动 approve（服务端也
  会拦：需 `acknowledge_novelty_warning=true` 的人工二次确认）。
- 命中敏感信息模式（密钥/口令/私钥）→ **升级人工**；确认后可选 reject 或请人走关卡 1 的
  脱敏路径。不要自动 reject——误报代价小于误放进图谱，但 reject 丢记忆不可逆。
- `reject` 是终态（没有 rescue）。拿不准的一律留在队列或升级，不要乱拒。
- 每条 approve/reject 都带 `rationale`（落 `decision_rationale` 列，服务端 ≥v13），
  写明判断依据，方便事后审计"为什么批/拒"。

<memory category="core-rules">
`review_queue.py apply` 在任何写操作前校验每条 approve 的 `snapshot_token`；同一 review 的有效 remove 与 approve 不能在同一文件。
任一 remove 失败会停止后续 actions，但多条 remove 之间不是事务。先单独清理、重拉并重新审核，再用新快照构造批准文件。
`original`/`curated` 都绑定已审核 token；缺 token（含旧决策文件）或 `review_changed` 必须停下，不自动补取、替换 token 或重试。
</memory>

<memory category="core-rules">
同组“新实体入图”受串行门禁约束：approve 成功不等于索引完成，批处理须等前一条 `indexed` 再批下一条
（等待手段：轮询 review detail 的 `memory_status` 至 `indexed`）。
这只串行化本执行者；Dashboard/其他 agent 仍可并发改变组门禁与预览，单条 `indexed` 不是全组就绪屏障。
“同组存在尚未完成的新实体入图任务”是暂态依赖等待，不是永久拒绝：应自动退回等待，依赖完成后自动重建预览、按既有模式重审，无需人工重新入队。
自动退回/恢复不等于自动 approve，也不改变审核模式；门禁以 `entity_admission_blocked` 暂态等待生效，预览重建后旧 snapshot_token 失效须重取（实体名也可能变）。
重建后的预览不继承旧清理验收；重新核对事实与 novelty，不绕过门禁。
内容分层、状态口径、语义快照和执行归因见 [审核内容、状态与快照](references/review-state-and-snapshots.md)。
</memory>

<memory category="core-rules">
批准动作的 HTTP 回执与服务端提交是不同边界：`503 / memory-hub: timed out` 不证明
批准未执行或已回滚；实测回读可已为 review `approved`、memory `indexed`。
超时结果应视为未知，不自动重发；只读核对 review 与对应 memory 的状态，再决定是否可续批。
</memory>

<memory category="troubleshooting">
apply 返回 `already_processed`，或复读时条目已为 approved/rejected，均可能是并发处理的正常结果。
跳过即可，不重试、不改判；apply 前先 rescan 可减少撞上。本次动作回执与最终队列快照分开统计，
不能把并发批准/拒绝计入自己的完成数量，也不能仅凭空 rationale 推断操作者身份。
</memory>

<memory category="troubleshooting">
关卡 1 入库审核与预览生成共用 review worker；旧预览优先策略可能使入库审核饥饿，现已改为公平轮转。须分别观察两阶段进度，不能以预览消化证明入库审核正常；待人工审核数量本身不是 worker backlog（先核对[自动决策模式](references/auto-review-modes-and-decision-samples.md)）。worker 存活及 SQLite 异常退出边界见 [memory-hub](../memory-hub/SKILL.md)。
单条 preview 失败应与全局停滞分开判断：LLM JSON 截断或未剥 code fence 的解析失败均可能耗尽 `preview_attempts`；上限 3，到限后不再自动重试，worker 恢复也不会自动解锁这些条目。需人工处置（重置 attempts 重试 / 正文有价值时 approve `original` 跳过预览 / reject），不代表其它待人工审核条目也失败。
</memory>

<memory category="troubleshooting">
敏感模式仍未命中 ≠ 安全，审核仍须人工检查正文凭证（2026-09-08 实证：`口令 789512`
未被任何模式捕获）。sk- 模式 2026-09-08 已修双缺陷：加前置字符守卫
（`(?<![A-Za-z0-9])`）——否则 `task-management-xxx.md` 这类文件名内的 "sk-" 子串
会误报（实证：`sk-management-database-design`）；主体允许点号——带点号的
sk- 凭证此前漏报。
</memory>

## 决策文件格式

```json
{
  "removals": [
    {"review_id": "review-to-clean-a", "entities": ["错误归属实体名"], "edges": []},
    {"review_id": "review-to-clean-b", "entities": [],
     "edges": [{"source": "user", "name": "HAS_PREFERENCE", "target": "user"}]}
  ],
  "approvals": [
    {"review_id": "review-ready", "content_mode": "curated",
     "snapshot_token": "<从已审核的 detail/scan 原样复制>",
     "rationale": "auto-review: 预览准确无畸形；novelty=novel"}
  ],
  "rejections": [
    {"review_id": "review-reject", "rationale": "auto-review: 正文为一次性临时状态，无长期价值"}
  ]
}
```

apply 按 (action, content_mode, rationale) 分组，逐项 token 组装为 `expected_snapshot_tokens: {review_id: token}`；
reject 不要求 token。同一 review 的清理与批准须拆阶段，不能给新预览套用旧验收。
`drive_approvals.py` 的批量输入沿用该顶层 `approvals` 结构，每项另需 `memory_id`/`group_id`
两个本地元数据字段（从实际审核的同一 scan 包原样带入，缺失或不一致在 POST 前阻塞）。
scan 保留服务端 token、状态、attempts、memory/session/group 等元数据；未返回的字段留空，不推断版本或物理组。
新客户端的批准需要支持快照契约的服务端；旧服务无 token 时仅可扫描，不能降级批准。
接口与错误语义见 [审核状态与快照](references/review-state-and-snapshots.md)。

## 常见预览质量模式

自环、模板污染、错误归属、同批演进与名称变体的处置表见 [预览质量模式](references/preview-quality-patterns.md)。

**novelty 候选的可见范围**：比对候选 = 已入图谱记忆 + 严格更早的同队列在途条目（最多
2 个槽位，service.py `_memory_evolution_candidates`）——同批**晚到**的重复仍互不可见，同一事项
的 worker 侧 + 编排侧两个会话可能都被判 novel。判了 novel 不代表
队列内无重复；扫完 packet 后需在同批条目间横向比对 project/正文关键词，重复的二选一
（通常拒预览更差的那份，拿不准就留队列升级）。

<memory category="core-rules">
错 scope 搬迁必须区分**物理写入组**与**逻辑检索 family**：exact content 去重只看同一物理
`group_id`，但 novelty 候选与检索会展开 project merge family。因此
`memory_search(project=target)` 命中、甚至 novelty=duplicate，都不能证明目标物理组已有副本；
以 `GET /memories/{id}` 的 `group_id` 和 Graphiti `/episodes/{group}` 为准。若 duplicate 来自
family 内的错误源组，只有在人工明确确认“这是 scope 修复”后才可带
`acknowledge_novelty_warning=true` 批准目标组副本，再处理原条。

已 indexed 的错误记忆用 admin memory invalidate：Hub 会置 `invalidated`、撤销未完成 outbox、
调用 Graphiti `DELETE /episode/{uuid}` 并写 `graph_edits`。响应中的 `episode_deleted=true` 只表示
删除调用成功，不证明关系级联完整；curated episode 实测可能出现 Episodic 节点已消失，但
`RELATES_TO` 仍保留失效 UUID（包括只由该 episode 支撑的边）。失效后必须分别验证：① episode
不在 `/episodes/{group}`；②图快照中没有仅引用失效 UUID 的边；③共享边仍有存活 episode 支撑。
独占残留边与共享边的 provenance 污染是两类问题，不能把共享事实随独占边一起删除。
</memory>

<memory category="core-rules">
「preview 高频出现图谱已有实体、看似无增量」是机制性噪音而非数据 bug（2026-09-06 线上取证：
Top10 高频实体 100% 已在图谱）。根因四叠加：① preview 盲抽——LLM 只看 distilled_content，无图谱
上下文（service.py:2021-2054）；② detail/UI 无 per-entity 存在性标注（store.py:1145-1204）；
③ novelty 是事实级判定，不查实体增量；④ curated 批准无存在性检查，实体清单渲染成自然语言 episode，
合并交给 Graphiti 写入侧。审核含义：实体已存在 ≠ 图谱会产生重复，**不要仅因实体眼熟就判 duplicate
或 reject**；老实体可能是新边/新事实的合法端点。另：`_normalize_extraction` 仅 str.strip()（无
NFKC/casefold），线上已出现 `Memory Hub`/`memory-hub` 双节点——外科清理改名时优先对齐图谱 canonical
写法。已否决的方向（勿再提）：全实体名单注入 prompt（token 膨胀+注入风险）、「0 新实体+0 新边」硬判
duplicate（误杀）。完整排查：`.claude/plans/MemoryHub抽取审核重复实体排查.md`。
</memory>

## 服务端接口速查（dashboard BFF 代理，前缀 `/api/v1`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/review/extraction?status=open` | 待审队列（open=preview_pending+review） |
| GET | `/review/extraction/{id}` | 详情（proposed 预览 + novelty + turns） |
| POST | `/review/extraction/{id}/remove` | 按 name/三元组移除预览条目（不经 LLM） |
| POST | `/review/extraction/{id}/turns` | 与预览 LLM 多轮对话调整（复杂修正时用） |
| POST | `/review/extraction/actions` | 批量 approve/reject；approve 必填 `expected_snapshot_tokens`；另带 `content_mode`、`acknowledge_novelty_warning`、`rationale` |

直连 Hub 用 `http://10.77.77.6:9287/v1/...`（脚本 `--base-url` 自动适配前缀）。
**注意（2026-09-06 实测修正）**：review 系列接口只在 dashboard BFF 上，直连 Hub :9287 会 404；
本机直连应 `--base-url http://10.77.77.6:9288`。
服务端字段/状态机权威定义：`D:/Github/memory-hub/docs/REVIEW_PIPELINE.md`。

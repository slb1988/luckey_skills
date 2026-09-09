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
# 1) 扫描：拉队列 + 详情 + 确定性检查 → review_packet.json + 摘要表
python scripts/review_queue.py scan -o review_packet.json

# 2) 判断：逐条读 packet 的 distilled_content 与 proposed（实体/边），
#    结合 flags/suggestion 做决策，写决策文件 decisions.json

# 3) 执行（先 dry-run 核对，再实跑）
python scripts/review_queue.py apply decisions.json --dry-run
python scripts/review_queue.py apply decisions.json
```

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
`review_queue.py apply` 只保证 removals 排在 actions 前，不提供跨阶段事务或 fail-closed：
remove 失败时不能假定后续 approve 会停止。批准依赖预览清理时必须拆成两份决策文件；
先只执行 removals，重拉详情确认清理生效，再单独 dry-run/执行 approve/reject。
</memory>

<memory category="troubleshooting">
apply 返回 `already_processed` = 该条已被并发处理（通常是用户在 dashboard 上手动批/拒）。
属良性竞态而非错误：跳过即可，不要重试或改判；apply 前先 rescan 可减少撞上。
</memory>

<memory category="troubleshooting">
多条停留 `preview_pending` 且 `preview_attempts=0`（从未被处理）+ outbox 积压 = hub-worker 进程已死（无自愈），不是审核/LLM 问题——重启 worker 后队列自动消化，详见 memory-hub skill。单条反复 preview 失败的已知成因：LLM 返回带 ```json 围栏的输出，解析不剥 code fence 直接失败并烧次数；`preview_attempts` 上限 3，到限后不再自动重试，需人工处置（重置 attempts 重试 / 正文有价值时 approve `original` 跳过预览 / reject）。
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
    {"review_id": "...", "entities": ["错误归属实体名"], "edges": []},
    {"review_id": "...", "entities": [],
     "edges": [{"source": "user", "name": "HAS_PREFERENCE", "target": "user"}]}
  ],
  "approvals": [
    {"review_id": "...", "content_mode": "curated",
     "rationale": "auto-review: 预览准确无畸形；novelty=novel"}
  ],
  "rejections": [
    {"review_id": "...", "rationale": "auto-review: 正文为一次性临时状态，无长期价值"}
  ]
}
```

removals 先于 approvals 执行（服务端保证 remove 后 curated 用清理后的预览渲染）。
apply 按 (action, content_mode, rationale) 分组批量调用；需要逐条不同 rationale 时
给每条单独一句即可，脚本会自动分组。

## 已知典型问题模式（2026-09-04 首批 36 条 + 后续批次实证）

| 模式 | 处置 |
|------|------|
| 自环边（`user -HAS_PREFERENCE-> user`、`x.vue -FIXES-> x.vue`） | remove 该边后 approve |
| Orca 派发模板污染：`orca(Project)` 被当作评审对象项目的属主 | remove 实体（级联清边） |
| 预览 1 实体 0 边、正文有实质内容 | approve `original` |
| novelty=evolution（演进链 SUPERSEDES/REFINES 旧记忆） | 正常 approve，链路本身即价值 |
| 个人偏好类记忆（硬件选型、购物兴趣） | 可批；这类画像是设计内的记忆类型 |
| `DECIDED` 边错挂 Person（`项目 -DECIDED-> 女儿/家长`，target 应是决策实体而非人） | 按三元组 remove（一个三元组可覆盖多条同三元组重复边），保留其余预览 approve curated |
| 整个预览只有 Orca 派发模板实体（`orca` + 派发约定），正文实际内容零抽取 | curated/original 都会灌噪音（original 正文大半是模板原文，Graphiti 重抽同样撞上）；建议 reject 或升级人工 |
| `orca` 实体不一定是污染：正文真实主题就是 orca 本身（如 Orca Arguments 配置机制）时合法 | 看正文主题而非实体名，勿误删 |
| 同一编码规则在多个 Linear 工单上被重复验证（换工单重述同一事实）、或正文只含单张工单的完成状态 | novelty 看不到同队列条目，须跨条目横向比对：通用规则只留最佳一份主记录，其余 reject；单工单完成状态按短期状态 reject |
| 正文/预览含事实性错误（校验条件写反、结论已被线上最终版本证伪或取代） | reject；需要留存时以修正版重投，勿批带病版本——错误事实入图谱比丢记忆危害大 |
| project/user 归属错误（worker 误标对话主体、记忆落错 project） | 不能原地带病批准：先向目标**物理 group** 重投干净摘要并验证 memory/episode 的 `group_id`；原条仍待审则 reject，已 indexed 则走 admin invalidate |
| 演进链兄弟条目对同一对象的归属事实矛盾（同批 c85 记备份任务建在 HBS 3，c94 实体写成 AList 托管且 `alist -RUNS-> 任务`） | novelty 演进分析（SUPERSEDES/REFINES）不标矛盾，须横向核对链条内事实一致性；删带病条目的错误归属实体（级联清边）后 approve，保留该条核心增量事实——两条都带病批会同时制造矛盾事实 + 同对象双节点 |
| preview 从正文提及的前身/参考链接脑补派生关系（正文是“替换/不更新了”，却抽成 `songloft -BASED_ON-> xiaomusic`） | 删幻觉源实体级联清边（或按三元组 remove）；顺带避免与同批同名异型实体（如 xiaomusic Project vs Service）被合并 |
| 同一对象的实体名变体横跨同批多条目（`project-lungfish`/`projectlungfish`/`ProjectLungfish`），且变体是预览的主实体 | 不要用 removals 删主实体（会掏空预览）；正常 approve，把变体列为 `/graph/edits` merge 候选交人工确认归并 |
| 非 canonical 实体写法成对出现（`Memory Hub`/`memory-hub`、`xiaoyingtao`/`小樱桃`、`Chat Hub`） | 机制已接管大部分：preview 落库前机械规范化（NFKC+空白折叠+重名合并），casefold/normalized 唯一候选自动进别名管理页待审（approved 后批准重验自动改写）；漏网的仍按外科清理统一改到图谱 canonical 写法后再 approve |

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
| POST | `/review/extraction/actions` | 批量 approve/reject；`content_mode`、`acknowledge_novelty_warning`、`rationale`（v13+） |

直连 Hub 用 `http://10.77.77.6:9287/v1/...`（脚本 `--base-url` 自动适配前缀）。
**注意（2026-09-06 实测修正）**：review 系列接口只在 dashboard BFF 上，直连 Hub :9287 会 404；
本机直连应 `--base-url http://10.77.77.6:9288`。
服务端字段/状态机权威定义：`D:/Github/memory-hub/docs/REVIEW_PIPELINE.md`。

---
name: memory-hub
description: Memory Hub（agent 中心记忆网关）使用与运维指南。覆盖 HTTP API 写入/检索、检索 eval、session 不可变版本、scope/group_id、幂等与错误码，以及为 Claude Code、Codex、Pi 自动安装、检查、召回、持久化和补传 hooks。当用户提到 memory-hub、memory hub、记忆网关、agent 记忆、memory eval/记忆评估/检索评估、session 归档/版本、记忆检索/写入、服务排障，或在 Memory Hub 语境输入 install、安装、配置、检查、补传 Agent hooks 时触发。注意与 memory-center 区分：memory-center 覆盖后端 Graphiti/Neo4j，memory-hub 覆盖面向 Agent 的 HTTP 网关。
---

# Memory Hub（Agent 中心记忆网关）

Memory Hub 是 Agent 访问中心记忆服务的唯一入口。它通过 HTTP 对接部署在 `10.77.77.6` 的 Graphiti（Graphiti 用 Neo4j 持久化），自身只维护控制面元数据（SQLite）和 session 文件存储（本地文件系统），**不直接读写 Neo4j**。

```text
User ── Agent ── MCP / HTTP ──> Memory Hub ── HTTP ──> Graphiti ──> Neo4j
                           │
                           ├── SQLite metadata（files/sessions/versions/memories/outbox）
                           └── 本地 session 文件存储（不可变、按 SHA-256 去重）
```

核心边界（务必记住）：
- 完整 session JSON 只能通过独立文件上传通道保存；普通 memory 请求和 Graphiti episode 中**不得内嵌**大块 session/content。
- 每条记忆必须绑定唯一 `session_id` 和一个确定的 `session_version`；同一 session 多次更新逻辑覆盖 `latest`、物理保留全部不可变版本。
- Memory 写入先落 SQLite outbox（可靠），再异步投递 Graphiti；Graphiti 暂不可用时写入仍可保存。
- 本项目**没有 Neo4j 凭证也不需要**；任何"连不上 memory"先确认走的是 Hub HTTP 而非直连 Neo4j。
- Memory Hub 同时服务多个用户；`user_id` 是逐请求业务身份，不是 Hub 服务端固定配置。

## 快速信息

| 项目 | 值 |
|------|-----|
| 项目目录（NAS） | `/share/Container/memory-hub` |
| Hub API（客户端默认） | `https://luckeyhome.site/memory-hub/agent-api` |
| Dashboard（公网面板） | `https://luckeyhome.site/memory-hub/` |
| Hub / Dashboard 内网调试 | `http://10.77.77.6:9287` / `http://10.77.77.6:9288/` |
| Hub LAN 转发（经 auto-server） | `http://192.168.2.13:9287` 或 `http://10.77.77.4:9287`，见 [references/auto-server-forward.md](references/auto-server-forward.md) |
| 上游 Graphiti | `http://10.77.77.6:8005` |

其余路径（venv/data/日志/脚本）见 [deploy.md](references/deploy.md) 与各场景文档。

<memory category="troubleshooting">
公网反代 `https://luckeyhome.site/memory-hub/`（经 sub2api 那台 VPS 的 nginx 中转）的 Hub API 已打通（2026-09-08 起）：**Agent API base = `https://luckeyhome.site/memory-hub/agent-api`**（nginx 剥前缀转发到 `10.77.77.6:9287/`；健康检查与带凭证 `/v1/projects` 均 200、匿名 401，原前端不受影响）。不能用 `/memory-hub/api`——那是 dashboard 前端既有 BFF 路由，抢占会冲突。访问者**无需 WireGuard**（仅 VPS→NAS 段走隧道）；客户端默认使用该 base，`MEMORY_HUB_URL` 仍可显式覆盖；API Key 与三个身份头不变（`memory_hook.py` 用 `hub_url + path` 拼接，兼容带前缀 base）。历史教训仍成立：「公网面板能打开」不能当作 API 可用的判据（该反代曾长期只通面板静态页、API 全 404）。
</memory>

## 环境职能与更新发布

- 先判断机器角色：`.env` 的 `MEMORY_HUB_ENV` = `release`（服务端：部署/重启/迁移）或 `dev`（开发/测试/hook 安装与检索）。**标识不存在时先提醒用户创建添加，不要瞎猜环境**。
- 「更新发布前后端」= 完整流程（不是单纯重启）：① `git pull` → ② 修冲突 → ③ 本地改动及时 commit → ④ `cd frontend && npm run build` → ⑤ `stop_all.sh && start_all.sh && status.sh` 验证；纯「重启」只做 ⑤。细节与验证见 [deploy.md](references/deploy.md)。
- Hub(:9287)=后端、dashboard(:9288)=前端。不要误跳 auto-server-deploy——那是 py_automation 平台（192.168.2.13）的部署，与 memory-hub 无关。

<memory category="common-patterns">
Dashboard 抽取审核在手机竖屏上以信息完整性优先：实体、边、摘要、存在性和审核操作必须全部保留并改用纵向卡片，不能隐藏字段或继续压缩桌面多列表格。桌面表格留在 390px 抽屉内会把摘要列压到约 30px，造成中文逐字竖排；这是布局模型不适合窄容器，不是文案换行问题。
</memory>

## 按场景导航（references/）

| 场景 | 文件 |
|------|------|
| 服务端部署/启动/重启/备份/自启/身份迁移/内容清洗与图谱重建 | [references/deploy.md](references/deploy.md) |
| Dashboard 开发/部署/排障入口 | [references/dashboard.md](references/dashboard.md) |
| API 端点、写入流程、Idempotency-Key、错误码、常用 curl | [references/api-notes.md](references/api-notes.md) |
| Hook 安装/check/身份配置/环境变量/首轮召回/Pi 扩展机制与留痕/低价值过滤 | [references/agent-integration.md](references/agent-integration.md) |
| 手动批量归档历史 session（upload_sessions.py、漏传回填、project 归属） | [references/upload-sessions.md](references/upload-sessions.md) |
| 排障：检索 0 命中/hook 验证/spool 积压/feedback 判死/triage 解析/catch-all 误归/chat-hub 信封淹没归档与人物归档身份/测试平台坑 | [references/troubleshooting.md](references/troubleshooting.md) |
| 误归档 session 定点清理 runbook | [references/cleanup-misscoped-sessions.md](references/cleanup-misscoped-sessions.md) |
| 检索 eval（黄金集/存错取错诊断/指标门禁/部署验收 smoke 向量） | [references/retrieval-eval.md](references/retrieval-eval.md) |
| 检索 scope 选择、已知 project 一览、别名映射 | [references/projects.md](references/projects.md) |
| 全链路总览（拓扑/写入/检索/观测/隐患） | [references/system-overview.md](references/system-overview.md) |
| auto-server 上的 Hub LAN 转发（:9287→10.77.77.6:9287）、无 sudo 时用 docker 特权容器代办 root 操作 | [references/auto-server-forward.md](references/auto-server-forward.md) |
| outbox 确认机制/大批量 retry 判读 | [memory-center/references/ingest-performance.md](../../memory-center/references/ingest-performance.md) |

服务端仓库文档（NAS 项目 `docs/`）：`USAGE.md`、`API_CONTRACT.md`、`IMPLEMENTATION.md`、`DASHBOARD.md`、`REVIEW_PIPELINE.md`、`MULTI_USER_AUTH.md`、`GRAPH_CURATION.md`（图谱修订/实体合并）。

关卡 2（抽取审核）队列的批量/自动处置走独立 skill：**memory-review**（`.claude/skills/memory-review/`，含 scan/apply 脚本与审核准则）。
每日人物洞察走独立 skill：**insight-daily**（`.claude/skills/insight-daily/`）；它在 `daily-report` 生成日记后只上传相关分节，触发/轮询 insight run，并用本地 manifest 做逐字复核，不修改 `daily-report`。

用户在 Memory Hub 语境提到 `eval`、记忆评估或检索效果验证时，立即按 [retrieval-eval.md](references/retrieval-eval.md) 执行；先做只读 baseline 和"存错还是取错"分层，不把非空结果等同于有效召回。

## 身份、Scope 与检索

除健康检查外，请求需三个身份头 `X-Agent-Id` / `X-Project-Id` / `X-User-Id`（生产另需 `Authorization: Bearer <MEMORY_HUB_API_KEY>`）；group_id 由服务端按身份计算（`global` / `user:{uid}` / `project:{pid}` / `agent:{aid}`），搜索自动覆盖可读的四个 group，客户端不传 `group_ids`。写 global 需 `X-Role: trusted_service/admin`，普通 agent 不要设。

**检索先选对 project**（`GET /v1/projects` 或 [projects.md](references/projects.md)）；空结果先换其他 project 重试，都不命中再认为"没有这条记忆"（scope 隔离是设计行为，不是 bug）；不要绕过 Hub 直查 Graphiti；`GRAPHITI_UNAVAILABLE` 才是后端故障。hook 实际走 `/v1/memories/search-v2`（LLM 质量门禁、fail-closed），v1 纯 FTS 结果与 hook 召回不可直接对比。写入流程、索引状态、错误码、curl → [api-notes.md](references/api-notes.md)。

<memory category="troubleshooting">
Dashboard 创建/修改用户报 422（非 400）= Pydantic 请求模型在域逻辑之前拒绝，先查 role 的 `Literal[...]`。role 定义重复散落在四处，新增 role 必须全部同步改：`src/memory_hub/api/schemas.py`（Hub 数据面）、`backend/dashboard_backend/routers.py` 的 `AdminCreateUserBody/AdminUpdateUserBody`（管理面 `:9288/api/v1/admin/users`）、`application/accounts.py` 域校验（`role not in {...}`）、frontend `api/types.ts`——漏 dashboard_backend 那处就是 422。guest=只读角色：禁写数据面、不能签发 agent token。
</memory>

<memory category="troubleshooting">
outbox `graphiti.add_memory_relation` 事件 HTTP 503 ≠ Graphiti 故障：`POST /memory-relations`（graphiti-0.22.0 overlay）的 Cypher 要求 source/target 两个 episode 都在 payload 的**同一个 group_id** 里，MATCH 不到即返回 503——设计本意是"瞬时可见性漂移，让 outbox 重试"，但永久不匹配配上 `OUTBOX_MAX_ATTEMPTS=100000` 就是无限重试。永久不匹配三类成因：① 演化分析**跨 project 建关系**（出生即跨组，payload 只带单个 group_id）；② 归属回填导致**组漂移**（payload group_id 入队时冻结为旧组，target 后被搬走）；③ target 被**强制忘记**（invalidated，episode 已删）。Dashboard「最近错误为空 + attempts 持续增长」的形态 = 命中 `workers/outbox.py` `_defer_memory_relation_until_indexed` 缺陷：defer 终态集漏了 `invalidated`（terminal 只有 deleted/rejected/failed/hub_only/dry_run），每 5s 无限 defer 且 defer 会把 `last_error` 清成 NULL。另一缺陷：`service.py` 强制忘记 `DELETE FROM outbox WHERE aggregate_id=?` 用的是 memory_id，而 relation 事件的 aggregate_id 是 relation_id → relation 事件漏取消。**关系的权威账本在 Hub SQLite（检索走账本，镜像失败不影响功能），Graphiti 镜像仅图谱可视化/审计用途**——跨组/失效的镜像本就无法落图，处置是置 completed，不要指望跨组落图（端点单组 MATCH 是组隔离语义）。诊断脚本（只读，可复用）：memory-hub 仓库 `scripts/diagnose_relation_outbox.py`。
</memory>

<memory category="troubleshooting">
「#review-extraction 卡住 / 队列不动」先查 hub-worker 进程是否存活，别误判成网关/LLM 问题。hub-worker 单进程跑 review/evolution/insight/outbox 四线程；SQLite `database is locked` 持续写锁风暴可让四线程全部退出、进程死亡，且**无 supervisor 自愈**，必须人工重启（`stop_all.sh && start_all.sh`，`status.sh` 验证）。特征形态：Hub API :9287 / Dashboard :9288 / Graphiti / LLM 网关全部健康，但 `preview_pending` 永不前进（review worker 是 `generate_pending_previews` 唯一执行者）、outbox 积压 next_attempt_at 过期无人投递；前端只是轮询一个静止的后端。重启后 preview 与 outbox 自动消化（2026-09-08 实证）。已知未根治：worker 无守护、`database is locked` 无重试退避、preview 解析不剥 code fence（烧 preview_attempts，处置见 memory-review）。
</memory>

<memory category="common-patterns">
同义实体碎片（`memory-hub`/`memory_hub`/`Memory Hub` 多变体并存、事实边分散在各节点）的定点合并走服务端图谱修订管线。推荐 `POST /api/v1/graph/edits` 显式指定 `merge_into_uuid`：先 `dry_run` 获取 `snapshot_hash`，确认执行时以 `expected_snapshot_hash` 锁定完整图状态。
合并会把源节点事实边迁移到 canonical（同名同端点边合并、episodes 去重）、迁移 episode MENTIONS，并丢弃源↔目标合并形成的自环；全程不调 LLM。**节点摘要不会自动拼接或重总结**：默认保留目标 summary、源 summary 随源节点删除，选 canonical 时须同时核对摘要，必要时在 merge 请求中显式提供目标 summary。
合并不可自动撤销，但全部落 `graph_edits` 审计（before 快照支持人工回滚）；合法子实体（文件/环境变量/专题节点）不要合并，跨物理 group 也不能合并。权威文档 `docs/GRAPH_CURATION.md`。合并只是时点修复——归一化缺陷不除变体会再生（根因见 memory-review 记录的 `_normalize_extraction`）。
</memory>

<memory category="troubleshooting">
关卡 2 抽取审核存在性标注是 **group 内口径**：`_entity_existence()` → `Neo4jClient.resolve_entities(group_id, names)` 只按 review 所属 group（继承 memory 的 `project:<pid>`）做三级匹配（exact→casefold→normalized=NFKC+空白折叠，`backend/dashboard_backend/clients.py:907`）；LLM 二次修正后前端重拉 detail 重算，但仍限本组——「新」只表示本组首次出现，不代表全图没有。判读「新」先看该 memory 归属 project 是否碎片组（判据：全组实体同一毫秒诞生 = 一次 approved 写入的产物），再决定是真新实体还是归因碎片。project 派生规则见 references/projects.md。
</memory>

## 人物画像、Insight 与 review-prompts

Dashboard `#review-prompts` 管 6 个 prompt，改「什么样的人信息进画像」只动其中两个，其余无关：

| prompt | 职责 | 与人物画像的关系 |
|---|---|---|
| `intake-filter` | 关卡 1 入库拦截 | 无关 |
| `extraction-preview` | 关卡 2 抽图谱实体 | 只产图谱 Person 实体（检索可见），不进画像 |
| `decision-mining` / `profile-synth` | 画像提案 | **画像内容的唯一来源** |
| `quote-synth` / `memory-evolution` | 语录归纳 / 记忆演化 | 无关 |

画像链路：insight run 把「daily input + 本账号全部 user_id 的记忆」喂给这两个 prompt → 产出**提案** → 人审通过才写入画像 facet。

<memory category="core-rules">
- **facet 强制 EvidenceRef 校验**：画像事实不能手工空写，必须走「记忆 → 该人物的 insight run → 提案 → 审批」证据链。
- **创建 person 是 admin-only**（dashboard 人物中心，agent token 无权）：`kind=child` 自动启用 minor_strict；需锚定账号、设 `hub_user_id`，并先把该 id 绑进账号 user_ids——否则它的记忆不会进入自己 insight run 的输入。
</memory>

## Hook 集成与批量归档

三端（Claude Code / Codex / Pi）共用 `scripts/memory_hook.py`（仅标准库）：capture 先落本地 spool（fail-open 不丢）再上传；首轮自动召回 + 按需检索（Pi 用 `memory_search`，Claude/Codex 用 `search` CLI）。人物卡可手工运行 `memory_hook.py persona-card [--person-id ID]`（默认输出 Hub canonical Markdown，`--json` 输出原始结构）；Pi 另提供 `/memory-card` 与 `memory_persona_card`。安装、check、身份、环境变量、Pi 扩展机制 → [agent-integration.md](references/agent-integration.md)。**改 `assets/` 下的安装副本（pi 扩展模板、project-aliases.json）必须递增版本号并重跑 install**。

<memory category="core-rules">
Hook 链路有三个独立验收层级：① installer/check 只证明配置就绪；② trace/SQLite spool 持久记录证明本机已捕获并入队；③ Hub session version + full-session 文件证明远端上传完成。不得把 `check ok` 当作端到端收集成功；memory 尚在审核态不等于上传失败，只要 file/session 已入 Hub 即表示收集链路完成。
</memory>

<memory category="core-rules">
MainDev `Tools/AiReview` 内的 Memory Hub 客户端是 CI 专用分支，只做受控召回并关闭普通 capture；地址、超时、重定向和凭证策略也为 CI 特化。它与本 skill 的通用 Claude/Codex/Pi 会话采集客户端是两个兼容面，不可互相覆盖或拿 AIReview 副本作为开发者安装源，尤其不得把 CI 凭证策略带到用户机器。
</memory>

<memory category="troubleshooting">
Pi v30 与 Claude/Codex recall 对纯寒暄/单独测试词做客户端快速跳过：不请求 Hub、不写完成 marker，同 session 后续首个有效任务仍会召回。有效短任务保留原意，不再因字符数过短而替换为宽泛项目背景；排查旧副本仍把 `hi` 改写成「项目概况/架构/决策」时，先看 trace 的 `ext_version` 并重跑 install。
TUI 的计数分三层：服务端候选、LLM 放行、客户端实际注入。policy 含 `judge14-evolution-injection` 时客户端优先使用同次 Judge 的 `injection_results[].text`，以 `result_id+rank` 绑定来源；没有该字段才回退原记忆拼装。`search --json` 的 `context_stats.injected`、Pi trace 的 `injected_count` 才是模型可见条数。`recall-results` 是排查溯源包，必须同时原样保留 Hub 完整响应、服务端 LLM 精简结果、客户端最终注入上下文与全部放行 facts/provenance，任何一层都不能因旧字段白名单而静默丢失。
</memory>

Pi 扩展 v22+：用户用 `/skill:name` 显式指定 skill 的首轮 prompt **跳过自动预热检索**——pi 会把 skill 展开为 `<skill name="…" location="…">` 块注入 prompt 开头（裸 `/skill:` 未展开命令作兜底匹配），扩展检测到即跳过，trace outcome 记 `skipped_skill_invocation` 并照常写 bootstrap-done 标记（同 session 后续不补检索）。排查「首轮预热没跑」先认这个 outcome，是设计行为不是故障；`memory_search` 工具不受影响，skill 内仍可主动检索。

Pi 扩展 v25+：首轮预热（“正在检索并审核历史记忆…” widget）与 `memory_search` 检索**可按 Esc/Ctrl+C 中断**——取消即杀检索子进程、本轮不注入、agent 立即开始；trace outcome 记 `cancelled`，本会话不重试。Ctrl+C 只取消检索并照常透传给 pi（连按两次仍退出 pi）。

Pi 扩展 v27+ 注册 `/memory-card` 与 `memory_persona_card`，两者始终可手工读取 Hub canonical card；首轮自动 card 注入只有 `MEMORY_HOOK_PI_PERSONA_CARD=1` 才启用，默认关闭。启用后 card（客户端防御上限 2500 字符）排在 project recall 前；任一请求失败都独立 fail-open 并写 `memory_persona_card` trace，不替代 `memory_search`，也不改变未 opt-in 的默认首轮行为。

批量归档历史 session 用 `scripts/upload_sessions.py`（漏传检测用 `backfill_missed_pi_sessions.py`），**执行前必须先读 [upload-sessions.md](references/upload-sessions.md)**。两条铁律（用户定版，违反被纠正过）：① 默认 `--hook-namespace` 双资产一起传；② project 归属先 `--dry-run` 出清单给用户 review，确认后才执行。

更多坑位：深度排障（spool FIFO 阻塞、401 积压、过期 upload 重放、feedback 判死等）→ [troubleshooting.md](references/troubleshooting.md)；运维坑（venv 重建、.env 相对路径、备份）→ [deploy.md](references/deploy.md)。

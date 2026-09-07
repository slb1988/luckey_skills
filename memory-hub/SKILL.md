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
| Hub API | `http://10.77.77.6:9287` |
| Dashboard（观测面板） | `http://10.77.77.6:9288/` |
| 上游 Graphiti | `http://10.77.77.6:8005` |

其余路径（venv/data/日志/脚本）见 [deploy.md](references/deploy.md) 与各场景文档。

## 环境职能与更新发布

- 先判断机器角色：`.env` 的 `MEMORY_HUB_ENV` = `release`（服务端：部署/重启/迁移）或 `dev`（开发/测试/hook 安装与检索）。**标识不存在时先提醒用户创建添加，不要瞎猜环境**。
- 「更新发布前后端」= 完整流程（不是单纯重启）：① `git pull` → ② 修冲突 → ③ 本地改动及时 commit → ④ `cd frontend && npm run build` → ⑤ `stop_all.sh && start_all.sh && status.sh` 验证；纯「重启」只做 ⑤。细节与验证见 [deploy.md](references/deploy.md)。
- Hub(:9287)=后端、dashboard(:9288)=前端。不要误跳 auto-server-deploy——那是 py_automation 平台（192.168.2.13）的部署，与 memory-hub 无关。

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

<memory category="common-patterns">
同义实体碎片（`memory-hub`/`memory_hub`/`Memory Hub` 多变体并存、事实边分散在各节点）的定点合并走服务端图谱修订管线：`POST /api/v1/graph/edits`（action=merge，需 admin token）或 `PATCH /curate/entity-node`（merge_if_exists）。合并语义：旧节点全部事实边迁移到 canonical（同名同端点边合并、episodes 去重）、episode MENTIONS 迁移、旧↔新之间的边成自环自动丢弃、不调 LLM 完全可预测；**不可自动撤销**，但全部落 `graph_edits` 审计（面板「图谱修订」页可查、before 快照支持人工回滚）。权威文档 `docs/GRAPH_CURATION.md`。合法子实体（文件/环境变量/专题节点）不要合并；跨 group 普遍存在同类双枢纽，可按组如法炮制。合并只是时点修复——归一化缺陷不除变体会再生（根因见 memory-review 记录的 `_normalize_extraction`）。
</memory>

<memory category="troubleshooting">
关卡 2 抽取审核存在性标注「新」= 仅在 review 所属 group 首次出现，不代表全图没有：`_entity_existence()` → `Neo4jClient.resolve_entities(group_id, names)` 只按本 group 过滤做三级匹配（exact→casefold→normalized=NFKC+空白折叠，`backend/dashboard_backend/clients.py:907`）；review 的 group_id 直接继承 memory 的 `project:<pid>`，LLM 二次修正后前端会重拉 detail 重算，但重算仍限本组，结论不变。碎片 group 确认根因：hook `project_id_for_cwd` 只取 cwd 末级目录名（+精确别名表，无父目录/通配规则）——session 跑在 Orca worktree（`~/orca/workspaces/<repo>/<worktree>`）即生成一次性 project（如实锤的 `memory-hub-attribution-project`）→ 全新 graph group，已知实体在新组重建并全部标「新」；碎片组判据是全组实体同一毫秒诞生（随一次 approved 写入）。判读「新」标注先看该 memory 归属哪个 project，再决定是否归因碎片而非真新实体。**根因已修（2026-09-07）**：`project_id_for_cwd` 查别名表前先做两级 worktree 归一（`orca/workspaces/<repo>/` 路径段规则 + git linked worktree 取主检出目录名，`memory_hook.py`/`upload_sessions.py` 各一份相同实现），规则细节见 references/projects.md；存量错归 project 的 memory 仍需人工搬家清理。
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

Pi 扩展 v22+：用户用 `/skill:name` 显式指定 skill 的首轮 prompt **跳过自动预热检索**——pi 会把 skill 展开为 `<skill name="…" location="…">` 块注入 prompt 开头（裸 `/skill:` 未展开命令作兜底匹配），扩展检测到即跳过，trace outcome 记 `skipped_skill_invocation` 并照常写 bootstrap-done 标记（同 session 后续不补检索）。排查「首轮预热没跑」先认这个 outcome，是设计行为不是故障；`memory_search` 工具不受影响，skill 内仍可主动检索。

Pi 扩展 v25+：首轮预热（“正在检索并审核历史记忆…” widget）与 `memory_search` 检索**可按 Esc/Ctrl+C 中断**——取消即杀检索子进程、本轮不注入、agent 立即开始；trace outcome 记 `cancelled`，本会话不重试。Ctrl+C 只取消检索并照常透传给 pi（连按两次仍退出 pi）。

Pi 扩展 v27+ 注册 `/memory-card` 与 `memory_persona_card`，两者始终可手工读取 Hub canonical card；首轮自动 card 注入只有 `MEMORY_HOOK_PI_PERSONA_CARD=1` 才启用，默认关闭。启用后 card（客户端防御上限 2500 字符）排在 project recall 前；任一请求失败都独立 fail-open 并写 `memory_persona_card` trace，不替代 `memory_search`，也不改变未 opt-in 的默认首轮行为。

批量归档历史 session 用 `scripts/upload_sessions.py`（漏传检测用 `backfill_missed_pi_sessions.py`），**执行前必须先读 [upload-sessions.md](references/upload-sessions.md)**。两条铁律（用户定版，违反被纠正过）：① 默认 `--hook-namespace` 双资产一起传；② project 归属先 `--dry-run` 出清单给用户 review，确认后才执行。

更多坑位：深度排障（spool FIFO 阻塞、401 积压、过期 upload 重放、feedback 判死等）→ [troubleshooting.md](references/troubleshooting.md)；运维坑（venv 重建、.env 相对路径、备份）→ [deploy.md](references/deploy.md)。

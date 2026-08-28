# 记忆系统全链路总览

> 数据快照：2026-08-26 经 NAS 实测核实；静态机制以本 skill 其余 references 与仓库 docs 为准。

## 1. 这是什么

以 Graphiti 时序知识图谱为核心的 **agent 长期记忆系统**。三端 agent（Claude Code / Codex / Pi）的会话被 hook 自动归档为不可变 session 版本，蒸馏成记忆写入图谱；检索由 agent 按需发起（不自动召回注入）。

```text
┌─ Agent 端（各机器）─────────────────────────────────────────────┐
│ Claude Code / Codex / Pi                                      │
│   └ hook（memory_hook.py，纯标准库）                            │
│       capture → 确定性 gzip 快照 → 本地 SQLite spool（durable） │
│       Pi 扩展 v5：write-ahead marker → enqueue → 防抖 flush     │
└──────────────┬────────────────────────────────────────────────┘
               │ HTTP（身份头 + Bearer mhu_ token + Idempotency-Key）
               ▼
┌─ NAS 10.77.77.6（QNAP NAS453Dmini，release 环境）──────────────┐
│ Memory Hub :9287（Flask，宿主机进程，非容器）                    │
│   控制面：SQLite 66M（users/files/sessions/versions/memories/    │
│           idempotency/outbox/review_*）                         │
│   文件面：session-files 655M（SHA-256 去重不可变对象）            │
│   outbox worker：add_episode → confirm_episode 两段式            │
│   ├─ Review Pipeline（当前 mode=auto）：入库过滤 → 抽取审核       │
│   ▼                                                             │
│ Graphiti :8005 ──Docker 容器（memory-center，zepai/graphiti +   │
│   本地补丁 ingest.py / zep_graphiti.py bind mount）             │
│   单 asyncio worker 串行抽取，~24.6 次 LLM 调用/episode          │
│   ├─ LLM：Kimi 网关 http://10.77.77.4:8600（Anthropic 协议，     │
│   │        kimi-k3 主 / deepseek-v4-flash small）── auto-server │
│   ├─ Embedding：百炼 DashScope 公网 qwen3.7-text-embedding 1024维│
│   ▼                                                             │
│ Neo4j 5.26 Community（7474/7687，容器）── 10,215 节点/42,207 边  │
│                                                                 │
│ Dashboard :9288（FastAPI BFF + Vue3 SPA 静态托管，release 强制   │
│   登录）── 观测/审核/账号管理                                     │
│ cypher-ro :8006（只读 Cypher 网关，Bearer token，Community 无    │
│   RBAC 的替代方案）                                               │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 部署拓扑（2026-08-26 实测）

| 组件 | 位置 | 形态 | 端口 | 状态 |
|---|---|---|---|---|
| Memory Hub API | NAS 10.77.77.6 `/share/Container/memory-hub` | 宿主机进程（.venv Python 3.12） | 9287 | pid 22266，ready，graphiti/metadata 依赖 true |
| Hub outbox worker | 同上 | 独立进程 hub-worker | — | pid 22290 |
| Dashboard | 同上 `backend/` + `frontend/dist` | 宿主机进程 | 9288 | pid 22382，healthy，纯局域网直连无反代/域名 |
| Graphiti | 同上 `/share/Container/memory_center/memory-center` | Docker `memory-center-graphiti` | 8005→8000 | Up 8d healthy，队列已清空（remaining queue 0） |
| cypher-ro | 同上 | Docker `memory-center-cypher-ro` | 8006→8000 | Up 10d healthy（无 /healthcheck 路由，属正常） |
| Neo4j | 同上 | Docker `memory-center-neo4j` | 7474/7687 | Up 11d healthy |
| Ollama | 同上 | Docker（备选 embedding bge-m3） | 11434 | 已停用未卸载 |
| LLM 网关 | auto-server 10.77.77.4:8600 | Anthropic 协议网关（kimi-k3 / deepseek-v4-flash） | 8600 | Hub 的 REVIEW_LLM 也走它 |
| Embedding | 百炼 DashScope 公网 | qwen3.7-text-embedding | — | 唯一公网依赖 |

- 三个环境标识实测均为 `release`：`ENVIRONMENT`（Hub 强制认证）、`DASHBOARD_ENVIRONMENT`（面板强制登录）、`MEMORY_HUB_ENV`（skill 层机器角色标记）。
- 开机自启链路：QTS → Container Station 拉起 memory-center 容器（`restart: unless-stopped`）→ Entware `/opt/etc/init.d/S99memory-hub`（2026-08-17 安装）→ `boot_start.sh` 轮询等 Graphiti healthy（≤10min）→ `start_all.sh` 拉起 Hub+worker+Dashboard。最近拉起 2026-08-20 10:53 全 ok。
- 仓库版本：NAS 部署点 HEAD = `a78d558`（fix(dashboard) 表格列宽），本地开发副本 `D:\Github\memory-hub` behind 1（`5b65c67` 移除 shares 已在 NAS）。

## 3. 写入链路全流程

```text
capture → spool → upload(files 三段式) → SessionVersion → Memory(pending_intake)
  → 关卡1 入库过滤(auto triage, 可脱敏 approve) → 关卡2 抽取审核
  → outbox graphiti.add_episode → Graphiti 队列 → 单 worker 串行抽取
  → Kimi 网关 LLM（3 medium + ~21 small）+ DashScope embedding → Neo4j MERGE
  → outbox confirm_episode（组级批量结算，FIFO 前缀）→ indexed
```

1. **capture（agent 端）**：hook 在 Stop/SessionEnd（Claude/Codex）或 agent_end/session_shutdown（Pi）触发，生成确定性 gzip 快照（`agent-session/2`，只留最近 10 条 user/assistant），先落本地 spool 再上传——fail-open，断网不丢。Esc 中断轮次跳过；纯噪声/例行运维会话被启发式/LLM 过滤（`skipped_meaningless`）。
2. **上传三段式**：`POST /v1/files/uploads` → `PUT content` → `complete`；session 文件必须是单 JSON 文档（批传用 `agent-session-archive/1` 包装）。写操作必带确定性 `Idempotency-Key`。
3. **版本链**：`PUT /v1/sessions/{id}/versions`，首版 replace、后续 append（文件仍是完整快照），同内容 SHA 相同天然幂等。
4. **Memory + 审核**：`POST /v1/memories` 绑定 session/version/file。当前 `review_settings.mode=auto`（2026-08-26 02:04 切换）：关卡 1 LLM triage 决定入/拒/脱敏（209 条 rejected 留档可救回），关卡 2 抽取审核（15 条 pending_extraction 在途）。mode=off 时走旧直连链路。
5. **outbox 两段式**：`add_episode`（POST Graphiti /messages，202）→ 原地改写为 `confirm_episode`；episode uuid == memory_id（graphiti 侧补丁 MERGE 预建保证）。confirm 为**组级批量结算**：同 group 对齐冷却点、一轮一次 `/episodes` 查询、FIFO 前缀整段转 completed——dashboard 上 indexed 计数阶梯式跳动属正常。
6. **Graphiti 抽取**：单 asyncio worker 严格串行；每 episode ~24.6 次 LLM 调用（3 medium kimi-k3 抽取实体/边 + ~21 small deepseek-v4-flash 属性/边去重），p50 89s/条，实测吞吐 ~85 episodes/小时。瓶颈 = LLM 网关延迟 × 串行，NAS CPU 不是瓶颈。
7. **落库**：Entity/Edge/Episodic 全部 MERGE 幂等写 Neo4j；embedding 只作用于实体名与边事实（短文本）。

实测现状（2026-08-26）：outbox completed=3936、零积压零失败；memories 共 3796（indexed 3537 / rejected 209 / deleted 35 / pending_extraction 15）。

## 4. 检索链路

```text
Pi memory_search 工具 / Claude·Codex memory_hook.py search CLI
  → POST Hub :9287 /v1/memories/search（身份头自动圈定可读 group：
    global + user:{uid} + project:{pid} + agent:{aid}）
  → Graphiti /search（查询词向量化 → Neo4j 向量相似度 + 图遍历）
  → Hub 组装返回（不含用户身份/概要；无结果时不输出任何内容）
```

- 记忆按 `project:{project_id}` 隔离，**0 命中先怀疑 scope 错了**（换 project 重试，见 projects.md）；`GRAPHITI_UNAVAILABLE` 才是后端故障。
- 语义检索噪音底线高：返回非空 ≠ 命中；调大 limit、换关键词重试后再下结论。
- 图只读直查走 cypher-ro :8006（Bearer token，READ 事务强制）；写永远走 Graphiti REST/Hub，禁止 neo4j 管理员直连 7687 写。

## 5. 身份、scope 与 project 归属

- 请求身份三头：`X-User-Id` / `X-Agent-Id` / `X-Project-Id` + `Authorization: Bearer mhu_...`（release 强制；agent token 由面板手工签发，数据面可写；session token 只读+账号管理）。
- 服务端按身份计算 group_id，客户端不可注入；global 写需 trusted_service/admin。
- 用户：当前 users 表仅 `sunlaibing`（bootstrap admin，adopt 全部历史）。
- 写入端分布（memories.agent_id）：pi=2544、claude-code-mac=511、claude=444、codex=293，零星 pi-qnap/pi-mac/claude-code。
- project 归属优先级：CLI 显式 > 本机 `project-aliases.local.json`（机器级 catch-all）> 安装部署的 `assets/project-aliases.json` 副本 > 环境变量 > cwd 派生。批量归档必须先 dry-run 给用户 review 归属。
- 规模 top5 group：`project:maindev` 1531、`project:unity2018` 756、`agent:claude-code-mac` 450、`project:obsidianvault` 333、`project:admin_sun_depot_7184` 131；共约 20 个 project。

## 6. 观测入口

| 入口 | 用途 |
|---|---|
| Dashboard `http://10.77.77.6:9288/` | 健康灯、memory 状态分布、outbox retry/last_error、episode 探测、日志尾部、检索测试、入库审核、用量统计、账号/token 管理 |
| `scripts/status.sh` / `data/boot.log` | 进程/端口/自启拉起记录 |
| `data/memory-hub.log` / `data/dashboard.log` | Hub / Dashboard 运行日志 |
| `logs/graphiti/llm_calls.jsonl`（memory-center） | 每次 LLM 调用全量留痕（caller/模型/延迟/token/原文，200MB 轮转）；`scripts/llm_stats.py` 汇总 |
| agent 端 `pi-trace.jsonl` / `hook-trace.jsonl`（state dir） | 三端 capture/search 留痕，分析检索质量先查它们 |
| cypher-ro :8006 | 图直查（Episodic.uuid == memory_id 溯源） |

## 7. 关键可靠性机制（速查）

- **幂等**：快照 SHA-256 去重 + 确定性 Idempotency-Key + episode uuid==memory_id MERGE——中断重跑天然安全。
- **不丢**：spool durable（服务器不可用 job 永久 queued，FIFO 队头阻塞）、Pi v5 write-ahead marker + session_start catch-up、outbox 两段式 + Graphiti 丢 episode 后可重置重投（deploy.md「outbox 重投递」）。
- **降级**：Graphiti 暂不可用写入仍进 outbox；检索才会 503。
- **补丁即生命线**：graphiti 容器 12 项本地补丁（端点分离/关思考/group_id 冒号/worker 韧性/uuid 预建/历史降本/实体负例护栏等），重部署必须保留 bind mount，改补丁后 `docker compose restart graphiti`。

## 8. 已知隐患与技术债（2026-08-26）

1. **无定时备份**：crontab 无 memory-hub/memory-center 条目；备份靠手动 tar（sqlite3 + session-files + .env）与 Neo4j 停库 dump。data/ 下 5 个 .bak 均为排障期手动快照。
2. **SQLite 单机**：66M 控制面单文件，多副本生产前需切 PostgreSQL（adapter 未实现）；不要让多机共享同一 SQLite。
3. **Neo4j Community 无 RBAC**：只读强制完全依赖 cypher-ro 网关；别外发任何自建账号。
4. **审核预览是近似**：Graphiti 真实抽取在其内部，hub 侧关卡 2 只能逼近；Phase 6「入库后校对」未做。
5. **Graphiti ingest 串行瓶颈**：大批量补传需数小时排空（650 条 ≈ 7.5-8h），worker 并发化未做。

## 9. 文档地图

| 层 | 文档 |
|---|---|
| 入口/边界/坑位 | memory-hub `SKILL.md` |
| 部署/启动/备份/自启/身份迁移 | [deploy.md](deploy.md) |
| API 契约与实测 curl | [api-notes.md](api-notes.md)（权威：仓库 `docs/API_CONTRACT.md`） |
| 排障（检索 0 命中/hook 验证/spool/误报案例） | [troubleshooting.md](troubleshooting.md) |
| Dashboard 开发部署 | [dashboard.md](dashboard.md) |
| Project 归属与别名 | [projects.md](projects.md) |
| Hook 安装/环境变量/Pi 扩展机制 | [agent-integration.md](agent-integration.md) |
| Graphiti 容器架构/补丁原理 | memory-center `references/architecture.md` |
| ingest 吞吐/outbox 确认判读 | memory-center `references/ingest-performance.md` |
| 审核管线设计 | 仓库 `docs/REVIEW_PIPELINE.md` |
| 多用户认证设计 | 仓库 `docs/MULTI_USER_AUTH.md` |

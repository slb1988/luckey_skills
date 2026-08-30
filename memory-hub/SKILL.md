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
- 每条记忆必须绑定唯一 `session_id` 和一个确定的 `session_version`。
- 同一 `session_id` 可多次更新：逻辑上覆盖 `latest`，物理上保留全部不可变版本（审计/回溯用）。
- Memory 写入先落 SQLite outbox（可靠），再异步投递 Graphiti；Graphiti 暂不可用时写入仍可保存。
- Memory Hub 同时服务多个用户；`user_id` 是逐请求业务身份，不是 Hub 服务端固定配置。

## 观测面板（Dashboard）

浏览器打开 `http://10.77.77.6:9288/`：Hub/Metadata/Graphiti 健康、memory 索引状态分布（pending/submitted/indexed/failed）、outbox 重试与错误、最近更新的 session、Graphiti episode 探测、Hub 日志尾部、检索测试工具。面板是独立服务（FastAPI BFF + Vue 3 SPA），只读 SQLite 元数据，**不影响** :9287 的写入链路。

排障入口优先级：面板 Overview 状态灯 → Outbox 页签（retry/failed 的 last_error）→ Graphiti 页签（episode 探测）→ 日志页签。开发/部署细节见 [references/dashboard.md](references/dashboard.md)。

## 快速信息

| 项目 | 值 |
|------|-----|
| 项目目录 | `/share/Container/memory-hub`（同 `/share/CACHEDEV1_DATA/Container/memory-hub`） |
| 虚拟环境 | `项目/.venv`（Linux Python 3.12，用 uv 重建过） |
| 环境配置 | `项目/.env`（无 secret；只有 Graphiti URL） |
| Agent 访问地址 | `http://10.77.77.6:9287` |
| 上游 Graphiti | `http://10.77.77.6:8005` |
| metadata DB | `data/memory-hub.sqlite3` |
| session 文件 | `data/session-files/objects/{sha256 前缀}/{sha256}.json[.gz]` |
| 运行日志 | `data/memory-hub.log` |
| 独立 Hook App | `scripts/memory_hook.py`（仅 Python 标准库） |
| 手动 session 上传 | `scripts/upload_sessions.py`（仅 Python 标准库，幂等批量归档历史 session） |
| 漏传检测回填 | `scripts/backfill_missed_pi_sessions.py`（diff 本地 pi session 与 Hub 已归档，排除 LLM 分析子 session 后调 upload_sessions 幂等补传） |
| project 别名定版 | `assets/project-aliases.json`（install 部署到 state dir，hook 与批传共用） |

## 环境职能判断与更新发布

每次运行 memory-hub 相关操作、不确定当前机器角色时，先从 `.env` 提取 `MEMORY_HUB_ENV`（区别于服务端读的 `ENVIRONMENT`）。取值只有两种：`release`（生产服务端：部署/重启/迁移）与 `dev`（开发/测试/hook 安装与检索）。**标识不存在时先提醒用户创建添加，不要瞎猜环境**；拿到标识后按角色做各自处理。

「更新发布前后端」是**完整部署流程，不是单纯重启**——「更新」二字 = 先 `git pull` 拉代码，漏掉只跑重启会被视为没完成。固定顺序：① `git pull` → ② 有冲突优先修复 → ③ 本地有未提交改动，更新后及时 commit（不要等用户提醒）→ ④ `cd frontend && npm run build` → ⑤ `sh scripts/stop_all.sh && sh scripts/start_all.sh && sh scripts/status.sh`（重启验证）。只有纯「重启」请求才只做 ⑤。命令细节与验证步骤见 [deploy.md](references/deploy.md)。

memory-hub 自身结构：Hub API(:9287)=后端，dashboard(:9288)=前端（backend BFF + 静态托管 frontend/dist，由 start_all.sh 一并拉起）。不要误跳 auto-server-deploy——那是 py_automation 平台（192.168.2.13，`/data/py_automation`）的部署，与 memory-hub 完全无关；auto-server 未授权 NAS 公钥，SSH `dev@10.77.77.4` 会 publickey 拒绝。

## 按场景导航（references/）

| 场景 | 文件 |
|------|------|
| 服务端部署/启动/重启/备份/自启/身份迁移/内容清洗与图谱重建 | [references/deploy.md](references/deploy.md) |
| Dashboard 开发/部署备忘 | [references/dashboard.md](references/dashboard.md) |
| API 端点总览、写入流程、Idempotency-Key、错误码、常用 curl | [references/api-notes.md](references/api-notes.md) |
| Hook 安装/check/身份配置/环境变量/首轮召回/Pi 扩展机制与留痕/低价值过滤判定 | [references/agent-integration.md](references/agent-integration.md) |
| 手动批量归档历史 session（upload_sessions.py、漏传回填、project 归属） | [references/upload-sessions.md](references/upload-sessions.md) |
| 排障：检索 0 命中/hook 生效验证/spool 积压/feedback 判死/triage 解析/catch-all 误归/测试平台坑 | [references/troubleshooting.md](references/troubleshooting.md) |
| 误归档 session 定点清理 runbook（足迹表结构/named 对象共享坑/删除顺序） | [references/cleanup-misscoped-sessions.md](references/cleanup-misscoped-sessions.md) |
| 检索 eval（黄金集/真实 Pi case/存错取错诊断/指标与门禁/部署验收 smoke 向量） | [references/retrieval-eval.md](references/retrieval-eval.md) |
| 检索 scope 选择、已知 project 一览、别名映射 | [references/projects.md](references/projects.md) |
| 全链路总览（拓扑/写入/检索/观测/隐患） | [references/system-overview.md](references/system-overview.md) |
| outbox 确认机制/大批量 retry 判读（graphiti 排队 vs 确认失效） | [memory-center/references/ingest-performance.md](../../memory-center/references/ingest-performance.md) |

服务端仓库文档（NAS `/share/Container/memory-hub/docs/`）：`USAGE.md`（完整使用手册）、`API_CONTRACT.md`（接口契约）、`IMPLEMENTATION.md`（模块与状态机）、`DASHBOARD.md`、`REVIEW_PIPELINE.md`、`MULTI_USER_AUTH.md`。

用户在 Memory Hub 语境提到 `eval`、记忆评估或检索效果验证时，立即按
[references/retrieval-eval.md](references/retrieval-eval.md) 执行；先做只读 baseline 和
"存错还是取错"分层，不把非空结果等同于有效召回。

## 身份与 Scope

除健康检查外，所有请求至少需要三个身份头：`X-Agent-Id`、`X-Project-Id`、`X-User-Id`；生产环境（`ENVIRONMENT` 非 development/test）另需 `Authorization: Bearer <MEMORY_HUB_API_KEY>`。只有 `X-Role: trusted_service` 或 `admin` 可写 global scope；普通 agent 不要设置 `X-Role`。

group_id 由服务端按身份计算，客户端不能注入：`global` / `user:{user_id}` / `project:{project_id}` / `agent:{agent_id}`。搜索自动覆盖调用者可读的四个 group，客户端不传 `group_ids`。

## HTTP API 与检索

端点总览、固定写入流程（初始化上传 → 字节流 → complete → SessionVersion → memory → 等 indexed）、Memory 索引状态与错误码表见 [api-notes](references/api-notes.md)。

检索前先根据目标内容选择正确的 project（调 `GET /v1/projects` 或见 [references/projects.md](references/projects.md)）；空结果时先切换其他已知 project 重试，确认都不命中再认为"没有这条记忆"。不要因为 Hub 搜不到就绕过 Hub 直查 Graphiti。检索 curl 见 [api-notes](references/api-notes.md)「常用接口速查」第 1 条。

## Agent hook 集成（归档 + 召回 + 按需检索）

Claude Code / Codex / Pi 三端共用独立应用 `scripts/memory_hook.py`（仅标准库）：capture 先生成确定性快照落本地 SQLite spool（fail-open，断网不丢、恢复后自动补传），再上传 Hub。**三端都有首轮自动召回**（2026-08-29 起）：Pi 走扩展 `before_agent_start`，Claude/Codex 走 `UserPromptSubmit` hook → `memory_hook.py recall`——每个 session 只对首个用户 prompt 做一次 focused recall、fail-open、不重试；后续深挖用 `memory_search`（Pi）/ `memory_hook.py search` CLI（Claude/Codex）。行为契约写在 vault `AGENTS.md`「Memory Hub 按需检索」一节。

- 安装/复检/身份配置/环境变量/首轮召回细节/Pi 扩展 v5+v12 机制与 trace 留痕/e2e 测试 → [agent-integration.md](references/agent-integration.md)
- 改「安装副本」类产物（`assets/pi-memory-hub.ts`、`assets/project-aliases.json`）必须递增版本号并重跑 install；hook 直接按路径引用的脚本（memory_hook.py）改动不需要升版本。
- 低价值过滤：`MEMORY_HUB_TITLE_LLM` 默认关（用启发式标题、不调 LLM），但启发式噪声过滤**始终生效**——纯噪声/纯执行类例行运维会话不上传；判定规则细节见 agent-integration.md「会话标题与低价值过滤判定」。

## 手动批量上传历史 session

`scripts/upload_sessions.py`（仅标准库）把任意机器的历史 session `.jsonl` 批量归档到 Hub（每文件一个独立 session + 一条可检索 summary，幂等、可中断重跑）；`scripts/backfill_missed_pi_sessions.py` 检测漏传并一键补传。用法、幂等机制、project 归属优先级 → [upload-sessions.md](references/upload-sessions.md)。

两条铁律（2026-08-20 用户定版，违反被明确纠正过）：
1. **默认必须双资产一起传（`--hook-namespace`）**：快照 + 完整 session 文件一次到位；单资产模式只用于确实没有完整 jsonl 源的场景。
2. **project 归属必须先经用户 review**：先 `--dry-run` 生成每个 session 的归属清单交给用户确认，用户点头后才去掉 dry-run 执行。

## 关键坑位速查

- **搜索空结果先怀疑 project scope 错了**：记忆按 `project:{project_id}` 隔离，用错 `X-Project-Id` 必然 0 命中（设计行为，不是 bug）。换 project 重试。
- **session 归错 project 先查本机 catch-all**（`project-aliases.local.json` 的 `"*"` 条目，多 workspace 工作站不应设置）；误归档清理见 [cleanup-misscoped-sessions.md](references/cleanup-misscoped-sessions.md)。
- **删 session 对象文件注意 named 对象物理共享**：只按 sha256 判孤儿会误删，必须同时按 storage_key 反查 files 表（同上 cleanup runbook）。
- **`.env` 用相对路径**（`./data/...`），必须从项目目录启动，否则 data 会写到别处。
- **本项目没有 Neo4j 凭证**，也不需要。若 agent 拿着 Neo4j URI/密码说"连不上 memory"，先确认它走的是 Memory Hub 而不是直连 Neo4j。
- **Graphiti 检索不可用 ≠ 空结果**：返回 `GRAPHITI_UNAVAILABLE` 才是后端不可用。
- **健康检查只证明进程活着**：`/health/ready` 的 `dependencies.graphiti` 才反映上游连通；memory 是否真正 `indexed` 要查 `GET /v1/memories/{id}`。
- **不要在对话中回显 `.env` 全文**（虽然当前无 secret，但生产会加 API key）。
- **本机（NAS）跑脚本用 `python3`**，没有 `/usr/bin/python3`。
- **venv 曾是从 macOS 拷来的坏环境**，在 NAS 上需要重建（见 [deploy.md](references/deploy.md)）。
- 深度排障（spool FIFO 队头阻塞、上传 401 积压、`skipped_capture_env` 环境污染、过期 upload 幂等重放、feedback 判死 memory、triage 非法 JSON 等）→ [troubleshooting.md](references/troubleshooting.md)。

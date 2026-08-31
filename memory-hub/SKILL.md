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
| 排障：检索 0 命中/hook 验证/spool 积压/feedback 判死/triage 解析/catch-all 误归/测试平台坑 | [references/troubleshooting.md](references/troubleshooting.md) |
| 误归档 session 定点清理 runbook | [references/cleanup-misscoped-sessions.md](references/cleanup-misscoped-sessions.md) |
| 检索 eval（黄金集/存错取错诊断/指标门禁/部署验收 smoke 向量） | [references/retrieval-eval.md](references/retrieval-eval.md) |
| 检索 scope 选择、已知 project 一览、别名映射 | [references/projects.md](references/projects.md) |
| 全链路总览（拓扑/写入/检索/观测/隐患） | [references/system-overview.md](references/system-overview.md) |
| outbox 确认机制/大批量 retry 判读 | [memory-center/references/ingest-performance.md](../../memory-center/references/ingest-performance.md) |

服务端仓库文档（NAS 项目 `docs/`）：`USAGE.md`、`API_CONTRACT.md`、`IMPLEMENTATION.md`、`DASHBOARD.md`、`REVIEW_PIPELINE.md`、`MULTI_USER_AUTH.md`。

用户在 Memory Hub 语境提到 `eval`、记忆评估或检索效果验证时，立即按 [retrieval-eval.md](references/retrieval-eval.md) 执行；先做只读 baseline 和"存错还是取错"分层，不把非空结果等同于有效召回。

## 身份、Scope 与检索

除健康检查外，请求需三个身份头 `X-Agent-Id` / `X-Project-Id` / `X-User-Id`（生产另需 `Authorization: Bearer <MEMORY_HUB_API_KEY>`）；group_id 由服务端按身份计算（`global` / `user:{uid}` / `project:{pid}` / `agent:{aid}`），搜索自动覆盖可读的四个 group，客户端不传 `group_ids`。写 global 需 `X-Role: trusted_service/admin`，普通 agent 不要设。

**检索先选对 project**（`GET /v1/projects` 或 [projects.md](references/projects.md)）；空结果先换其他 project 重试，都不命中再认为"没有这条记忆"（scope 隔离是设计行为，不是 bug）；不要绕过 Hub 直查 Graphiti；`GRAPHITI_UNAVAILABLE` 才是后端故障。写入流程、索引状态、错误码、curl → [api-notes.md](references/api-notes.md)。

## Hook 集成与批量归档

三端（Claude Code / Codex / Pi）共用 `scripts/memory_hook.py`（仅标准库）：capture 先落本地 spool（fail-open 不丢）再上传；首轮自动召回 + 按需检索（Pi 用 `memory_search`，Claude/Codex 用 `search` CLI）。安装、check、身份、环境变量、Pi 扩展机制 → [agent-integration.md](references/agent-integration.md)。**改 `assets/` 下的安装副本（pi 扩展模板、project-aliases.json）必须递增版本号并重跑 install**。

Pi 扩展 v22+：用户用 `/skill:name` 显式指定 skill 的首轮 prompt **跳过自动预热检索**——pi 会把 skill 展开为 `<skill name="…" location="…">` 块注入 prompt 开头（裸 `/skill:` 未展开命令作兜底匹配），扩展检测到即跳过，trace outcome 记 `skipped_skill_invocation` 并照常写 bootstrap-done 标记（同 session 后续不补检索）。排查「首轮预热没跑」先认这个 outcome，是设计行为不是故障；`memory_search` 工具不受影响，skill 内仍可主动检索。

批量归档历史 session 用 `scripts/upload_sessions.py`（漏传检测用 `backfill_missed_pi_sessions.py`），**执行前必须先读 [upload-sessions.md](references/upload-sessions.md)**。两条铁律（用户定版，违反被纠正过）：① 默认 `--hook-namespace` 双资产一起传；② project 归属先 `--dry-run` 出清单给用户 review，确认后才执行。

更多坑位：深度排障（spool FIFO 阻塞、401 积压、过期 upload 重放、feedback 判死等）→ [troubleshooting.md](references/troubleshooting.md)；运维坑（venv 重建、.env 相对路径、备份）→ [deploy.md](references/deploy.md)。

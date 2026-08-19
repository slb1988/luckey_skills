---
name: memory-hub
description: Memory Hub（agent 中心记忆网关）使用与运维指南。覆盖 HTTP API 写入/检索、session 不可变版本、scope/group_id、幂等与错误码，以及为 Claude Code、Codex、Pi 自动安装、检查、召回、持久化和补传 hooks。当用户提到 memory-hub、memory hub、记忆网关、agent 记忆、session 归档/版本、记忆检索/写入、服务排障，或在 Memory Hub 语境输入 install、安装、配置、检查、补传 Agent hooks 时触发。注意与 memory-center 区分：memory-center 覆盖后端 Graphiti/Neo4j，memory-hub 覆盖面向 Agent 的 HTTP 网关。
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

浏览器打开 `http://10.77.77.6:9288/`：Hub/Metadata/Graphiti 健康、memory 索引状态分布（pending/submitted/indexed/failed）、
outbox 重试与错误、最近更新的 session 列表、Graphiti episode 探测、Hub 日志尾部、检索测试工具。

- 面板是独立服务：`backend/`（FastAPI BFF，:9288）+ `frontend/`（Vue 3 SPA）+ `protocol/`（共用 openapi 契约），
  只读 SQLite 元数据，**不影响** :9287 的写入链路。详见仓库 `docs/DASHBOARD.md`。
- 排障入口优先级：面板 Overview 状态灯 → Outbox 页签（retry/failed 的 last_error）→ Graphiti 页签（episode 探测）→ 日志页签。

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

<memory category="common-patterns">
`MEMORY_HUB_TITLE_LLM` 代码默认 `0`（关闭时退化为启发式标题、不做低价值过滤），置 `1` 才走内网 vLLM。本机是通过 **Machine 作用域**环境变量开启的（`=1`）——在新进程里发现标题走 LLM 属预期；其他机器若想开启须自行设该变量，不要改代码默认值。
</memory>

## 参考文档

| 主题 | 文件 |
|------|------|
| 部署 / 启动 / 重启 / 备份 / 排障 | [references/deploy.md](references/deploy.md) |
| 观测面板（dashboard）开发/部署备忘 | [references/dashboard.md](references/dashboard.md) |
| API 实测备忘（Idempotency-Key、字段约束、错误码、常用 curl） | [references/api-notes.md](references/api-notes.md) |
| 已知 project 一览与检索 scope 选择 | [references/projects.md](references/projects.md) |
| Hook 安装 / 身份配置 / 环境变量 | [references/agent-integration.md](references/agent-integration.md) |
| outbox 确认机制 / 大批量 retry 判读（graphiti 排队 vs 确认失效） | [memory-center/references/ingest-performance.md](../../memory-center/references/ingest-performance.md) |
| 项目完整使用手册（写入/检索示例） | `docs/USAGE.md` |
| HTTP/MCP 接口契约 | `docs/API_CONTRACT.md` |
| 当前实现说明（模块、状态机、已实现/未实现） | `docs/IMPLEMENTATION.md` |

> 运维类问题（启动、重启、日志、venv 重建、备份）先读 [deploy.md](references/deploy.md)。

## 身份请求头

除健康检查外，所有请求至少需要：

```text
X-Agent-Id: claude-code-mac
X-Project-Id: ProjectLungfish
X-User-Id: internal-user-id
```

生产环境（`ENVIRONMENT` 非 development/test）还需要 `Authorization: Bearer <MEMORY_HUB_API_KEY>`。
只有 `X-Role: trusted_service` 或 `admin` 可写 global scope；普通 agent 不要设置 `X-Role`。

## Scope 与 group_id

group_id 由服务端计算，客户端不能注入：

| scope | group_id | 写权限 |
|---|---|---|
| global | `global` | trusted_service / admin |
| user | `user:{user_id}` | 对应用户身份 |
| project | `project:{project_id}` | 对应项目身份 |
| agent | `agent:{agent_id}` | 对应 Agent 身份 |

搜索自动覆盖调用者可读的 `global` + `user:xxx` + `project:xxx` + `agent:xxx` 四个 group，客户端不传 `group_ids`。

## HTTP API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health/live` | 存活探针 |
| GET | `/health/ready` | 就绪探针（含 graphiti/metadata 依赖） |
| POST | `/v1/files/uploads` | 初始化文件上传（只收元数据 + SHA-256） |
| PUT | `/v1/files/uploads/{upload_id}/content` | 上传 session JSON 原始字节流 |
| POST | `/v1/files/uploads/{upload_id}/complete` | 校验并置为 available |
| GET | `/v1/files/{file_id}` / `/download` | 文件元数据 / 下载 |
| POST | `/v1/sessions` | 由 Hub 分配 session_id |
| PUT | `/v1/sessions/{session_id}/versions` | 提交不可变 session 版本 |
| GET | `/v1/sessions/{session_id}` / `/versions/{v}` | 查询 latest / 确定版本 |
| POST | `/v1/memories` | 写入精炼记忆（返回 202，初始 pending） |
| GET | `/v1/memories/{memory_id}` | 查询索引状态 |
| POST | `/v1/memories/search` | 检索记忆 |
| GET | `/v1/projects` | 列出已知 project（含 memory/session 计数，用于选择检索 scope） |

## 完整写入流程（顺序固定）

```text
初始化上传 → 上传字节流 → complete 校验 → 提交 SessionVersion → 写精炼 Memory → 等 submitted/indexed
```

1. `POST /v1/files/uploads`：传 `size_bytes`、`sha256`、`media_type`、`compression`，拿 `upload_id` + `file_id`。
2. `PUT /v1/files/uploads/{upload_id}/content`：`--data-binary @file`，原始字节流，不 base64。
3. `POST .../complete`：等 `status: available`。
4. `PUT /v1/sessions/{id}/versions`：首版本 `base_version=null, update_mode=replace`；后续 `base_version=latest, update_mode=append`（文件仍是完整快照）。
5. `POST /v1/memories`：传 `session_id/session_version/file_id` + `scope_type` + `memory_type` + `distilled_content` + `summary`，拿 `memory_id`（状态 `pending`）。
6. `GET /v1/memories/{id}` 轮询直到 `indexed`。

约束（实测）：**写操作必须带 `Idempotency-Key` 头**；`media_type` 仅 `application/json`/`application/gzip`；
session 文件必须是**合法 JSON 文档**，原始 .jsonl 会被拒。常用 curl 与字段细节见 [api-notes](references/api-notes.md)。
完整带变量的 curl 示例见 `docs/USAGE.md` 第 7 节。

## 检索

搜索只覆盖调用者身份对应的 `global` + `user:*` + `project:{X-Project-Id}` + `agent:{X-Agent-Id}`。
**检索前先根据目标内容选择正确的 project**（调 `GET /v1/projects` 或见 [references/projects.md](references/projects.md)）；
空结果时先切换其他已知 project 重试，确认都不命中再认为"没有这条记忆"。不要因为 Hub 搜不到就绕过 Hub 直查 Graphiti。

检索 curl 见 [api-notes](references/api-notes.md)「常用接口速查」第 1 条。

## Agent 自动记忆集成

Claude Code / Codex / Pi 三端共用独立应用 `scripts/memory_hook.py`（仅标准库），本地 spool + 失败自动补传。

> 详细参考：[agent-integration](references/agent-integration.md)（install、身份配置、环境变量、命令）

<memory category="troubleshooting">
在刚执行完 install 的**同一 shell** 里跑 `install_hooks.py check --agents auto`，`identity.source` 显示 `missing` 是预期——user-id 环境变量已写入 `~/.profile`/`~/.zprofile` 但当前进程未加载；新开终端或重启 agent 后即正常。不要据此重装或重复 configure。
</memory>

<memory category="troubleshooting">
agent-integration.md 的 install/configure 示例命令是 macOS 写法（`/usr/bin/python3`、`/Users/sun/...`）。Windows 上曾发现扩展配置里原样保留了 `/usr/bin/python3` 这个 Unix 路径导致 hook 无法执行——Windows 端 hook 失效先查安装命令里的 python 解释器路径，须改为本机 Windows python 全路径。排查「关窗提示有进程未结束」是否 hook 残留时，按命令行列 python.exe 分辨：本机常驻 python 通常是 UnrealMCP 和 pytest，与 memory-hook 无关；memory_hook.py 是逐事件短进程，正常不常驻。
</memory>

<memory category="troubleshooting">
Spool job 在 capture 时固化 `user_id`（这是设计，防止补传到错误用户）。副作用：身份配置变更（如 install 写入新的 `MEMORY_HUB_CLIENT_USER_ID`）之前积压的 queued job 仍带旧身份，flush 时持续报 `SCOPE_FORBIDDEN` 且不会自愈（实测一次积压 11 个）。看到 spool 反复 403 时直接清理这些旧 job，不要当作服务端权限配置问题排查。
</memory>

## 手动上传历史 session（upload_sessions.py）

`scripts/upload_sessions.py`（仅标准库）把任意机器/目录下的历史 session 记录（`.jsonl`）批量上传到
Hub，每个文件成为独立 session（`{source}:{原始session_id}`），并附一条可检索的 `session_summary`
记忆。适用于 hook 上线前的历史归档、其他电脑导出的 session 等（`memory_hook.py` 没有 backfill 子命令，
capture 只处理当前 live transcript）。

<memory category="code-locations">
历史 session 文件位置（Windows）：Claude Code 在 `%USERPROFILE%\.claude\projects\<slug>\*.jsonl`（文件名即 session UUID）；Pi 在 `%USERPROFILE%\.pi\agent\sessions\<slug>\*.jsonl`（文件名 `<UTC时间戳>_<uuid>.jsonl`，单项目可积累上千个）。两者 slug 方案不同：`E:\sununity` 在 Claude 是 `E--sununity`，在 Pi 是 `--E--sununity--`——定位时按 `sessions/` 实际列表匹配，不要自行推算。
</memory>

幂等保证：对包装后的归档文档（`agent-session-archive/1`，服务端要求 session 文件必须是合法 JSON，
原始 jsonl 不行）计算 SHA-256；上传前比对远端 latest 版本，一致则 `skipped`；所有写操作带确定性
`Idempotency-Key`，中断可直接重跑。内容变化时自动 append 新版本。

<memory category="common-patterns">
不传 `--project-id` 时按**每个 session 的 cwd 文件夹名**逐个派生 project——全机批量归档会散落到 `admin`、`sununity`、`MainDev`、`ObsidianVault` 等十几个 project（实测 3 个 pi session 落进 2 个 project）。检索按 project 隔离，散落后必须逐 project 切换才能搜全。批量归档历史 session 应显式加 `--project-id agent-history`（hook 归档主库）集中存放。
</memory>

```bash
SKILL_DIR="<本 SKILL.md 所在目录的绝对路径>"
# 指定 project，自动识别 claude/pi/codex，agent 按来源分类（claude-code/pi/codex）
python3 "$SKILL_DIR/scripts/upload_sessions.py" --project-id unity2018 <session文件或目录>...
# 干跑只看扫描结果，不碰服务器
python3 "$SKILL_DIR/scripts/upload_sessions.py" --project-id unity2018 --dry-run <目录>
```

- `--user-id` 默认取 hook 的 client-profile；`--source/--agent-id` 可强制来源与身份。
- 目录会递归扫描 `*.jsonl`；`--limit N` 可先小批量验证。
- 大量上传后 memory 经 outbox 异步投递 Graphiti，`indexed` 状态用 `GET /v1/memories/{id}` 跟踪。

## Memory 索引状态

- `pending`：已可靠落库，尚未投递 Graphiti。
- `submitted`：Graphiti 已接受，等待 episode 可查询确认。
- `indexed`：对应 group 最近 episodes 中已确认该 memory_id。
- `failed`：永久错误或重试耗尽（看 `error_code`）。

## 常见错误

| code | 处理 |
|---|---|
| `UNAUTHENTICATED` | 检查 Bearer token、X-Agent-Id/X-Project-Id |
| `SCOPE_FORBIDDEN` | 资源越权；global 写需受信角色 |
| `RAW_SESSION_CONTENT_FORBIDDEN` | 完整内容改走文件上传通道 |
| `FILE_TOO_LARGE` | 超 100MiB 原始 / 250MiB 解压上限 |
| `FILE_NOT_AVAILABLE` | 先 complete，或上传已过期需重新初始化 |
| `SESSION_REFERENCE_MISMATCH` | session/version/file 不是同一确定版本 |
| `SESSION_VERSION_CONFLICT` | base 不是 latest；拉 latest 重生成快照 |
| `IDEMPOTENCY_CONFLICT` | 同 key 用于不同请求；换新 key |
| `GRAPHITI_UNAVAILABLE` | 检查 `10.77.77.6:8005/healthcheck`；≠空结果 |

所有错误返回 `error.code/message/request_id/retryable/details`，`request_id` 同时出现在 `X-Request-Id` 响应头。

## 关键坑位

- **搜索空结果先怀疑 project scope 错了**：记忆按 `project:{project_id}` 隔离，用错 `X-Project-Id` 必然 0 命中（这是设计行为，不是 bug）。先 `GET /v1/projects` 或查 [references/projects.md](references/projects.md) 换 project 重试。
- **`.env` 用相对路径**（`./data/...`），必须从项目目录启动，否则 data 会写到别处。
- **本项目没有 Neo4j 凭证**，也不需要。若 agent 拿着 Neo4j URI/密码说"连不上 memory"，先确认它走的是 Memory Hub 而不是直连 Neo4j。
- **Graphiti 检索不可用 ≠ 空结果**：返回 `GRAPHITI_UNAVAILABLE` 才是后端不可用。
- **健康检查只证明进程活着**：`/health/ready` 的 `dependencies.graphiti` 才反映上游连通；memory 是否真正 `indexed` 要查 `GET /v1/memories/{id}`。
- **不要在对话中回显 `.env` 全文**（虽然当前无 secret，但生产会加 API key）。
- **venv 曾是从 macOS 拷来的坏环境**，在 NAS 上需要重建（见 [deploy.md](references/deploy.md)）。

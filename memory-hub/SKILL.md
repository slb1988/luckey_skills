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

## 参考文档

| 主题 | 文件 |
|------|------|
| 部署 / 启动 / 重启 / 备份 / 排障 | [references/deploy.md](references/deploy.md) |
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
| POST | `/v1/context/assemble` | 待实现 |
| POST | `/v1/feedback` | 待实现 |

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

完整带变量的 curl 示例见 `docs/USAGE.md` 第 7 节。

## 检索

```bash
curl -sS -X POST "$HUB_URL/v1/memories/search" \
  -H 'Content-Type: application/json' \
  -H "X-User-Id: $USER_ID" -H "X-Agent-Id: $AGENT_ID" -H "X-Project-Id: $PROJECT_ID" \
  -d '{"schema_version":"memory-search/1","query":"...","user_id":"...","agent_id":"...","project_id":"...","limit":10,"session_view":"captured"}'
```

## Agent 自动记忆集成

Claude Code / Codex / Pi 三端共用独立应用 `scripts/memory_hook.py`。它不 import、调用或依赖
Memory Hub 项目及其 venv，只使用 Python 标准库访问远端 HTTP API。

每次 capture 先生成确定性 gzip 快照并写入本机 SQLite spool，然后才访问服务器。服务器不可用时
job 永久保留为 `queued`；后续 Stop、SessionEnd、agent_end 或手工 flush 会自动补传。因此 hook
仍可 fail-open，不会阻止 Agent，也不会因短期网络故障丢失 session。

快照格式为 `agent-session/2`，只保存最近 10 条 user/assistant 消息。工具事件、无法解析事件和
Markdown fenced code 不上传；Markdown 标题、列表、链接和解释正文保留。Spool 每个 job 固化
`user_id`，所以稍后 flush 时不会因进程环境变化而补传到错误用户。

### 首次用户身份配置

Hook 客户端没有内置固定用户，也不得用 `agent_id` 代替用户身份。首次 SessionStart 或
UserPromptSubmit hook 若尚无完整配置，会停止检索并向 Agent 注入设置提醒；Agent 必须向用户确认以下
三项信息，不得自行猜测：

- 长期稳定的内部 `user_id`（仅字母、数字、`.`、`_`、`:`、`-`，最长 128 字符）；
- 显示名称；
- 简短概要，例如身份、偏好或长期目标，不得包含密码、API Key 等秘密。

确认后执行：

```bash
/usr/bin/python3 "$SKILL_DIR/scripts/memory_hook.py" configure \
  --user-id 'internal-user-id' \
  --display-name 'Display Name' \
  --summary '身份、偏好或长期目标的简短概要'
```

配置以 `0600` 权限保存到
`${MEMORY_HOOK_STATE_DIR:-~/.local/state/memory-hub-hook}/client-profile.json`。配置完成前，capture
仍会把最近会话安全暂存到本机，但这些 job 使用隔离占位身份，不会进入上传队列；配置成功后会归属到
确认的用户并尝试补传。Recall/search 在配置完成前不会调用 Hub。

### install 关键字

用户在 Memory Hub 语境输入 `install` 或要求安装 hooks 时，直接执行：

```bash
SKILL_DIR="<本 SKILL.md 所在目录的绝对路径>"
/usr/bin/python3 "$SKILL_DIR/scripts/install_hooks.py" install --agents auto
```

必须将占位符替换为加载本 Skill 时获得的实际目录，不得相对当前工作目录猜测。`auto` 配置本机检测到的
Claude Code、Codex、Pi；用户明确要求全部安装时改用 `--agents all`。不得手工拼装 Hook JSON。

安装成功必须同时满足：

- Claude Code/Codex 各有且仅有 4 个 Memory Hub handlers：SessionStart、UserPromptSubmit、Stop、SessionEnd。
- Stop 每轮直接执行 `capture`，不得带 `--flush-limit 0`；SessionEnd 再提交最终幂等快照。
- Codex 必须通过 app-server `hooks/list` 确认 4 个 handlers 均为 `trusted`，且没有 Memory Hub 相关 warning/error。
- Pi 全局扩展必须包含 `before_agent_start`、`agent_end`、`session_shutdown`；`agent_end` 必须直接上传。
- 安装器返回的各 agent `ok=true`。服务健康检查失败可保留 durable spool，但必须明确报告“已安装、尚未端到端验证”，不得宣称上传链路正常。

安装或升级后执行只读复检：

```bash
/usr/bin/python3 "$SKILL_DIR/scripts/install_hooks.py" check --agents auto
```

安装器仅替换命令路径包含 `memory-hub/scripts/memory_hook.py` 的 handlers，保留其他 Hook，并在修改配置前生成
`*.memory-hub.bak` 备份。运行中的 Agent 可能缓存配置；完成后提示重启对应 Agent 或执行其 reload 命令。

环境变量：

```bash
export MEMORY_HUB_URL=http://10.77.77.6:9287
export MEMORY_HUB_AGENT_ID=claude-code-mac
export MEMORY_HUB_ARCHIVE_PROJECT_ID=agent-history
# 可用环境变量代替 client-profile.json，但三项必须同时配置：
# MEMORY_HUB_CLIENT_USER_ID=internal-user-id
# MEMORY_HUB_CLIENT_DISPLAY_NAME='Display Name'
# MEMORY_HUB_CLIENT_SUMMARY='身份、偏好或长期目标的简短概要'
# MEMORY_HUB_API_KEY=...          # 生产必填
# MEMORY_HOOK_TIMEOUT_SECONDS=8
# MEMORY_HOOK_STATE_DIR=~/.local/state/memory-hub-hook
# MEMORY_HOOK_DEBUG=1             # 调试失败原因
```

User ID 解析优先级为命令行 `--user-id`、hook 输入的 `user_id`、
`MEMORY_HUB_CLIENT_USER_ID`，最后为本机 `client-profile.json`；不再回退到
`MEMORY_HUB_AGENT_ID`。命令行或 hook 输入覆盖默认用户时，还必须同时提供该用户的显示名称和概要
（命令行用 `--display-name` / `--summary`，hook 输入用 `user_display_name` / `user_summary`），否则视为
未完成身份配置。多用户调用方应在每次 hook 输入中显式提供这三项；Hub 进程本身不得配置固定用户。

独立应用命令：

```bash
APP=/Users/sun/Documents/ObsidianVault/.claude/skills/memory-hub/scripts/memory_hook.py
/usr/bin/python3 "$APP" configure --user-id user-123 --display-name 'Jane' --summary '偏好简洁、技术性的回答'
/usr/bin/python3 "$APP" search '项目的历史决策和未完成事项' --limit 10
/usr/bin/python3 "$APP" search '用户偏好' --user-id user-456 --display-name 'Alex' --summary '用户概要' --limit 10
/usr/bin/python3 "$APP" status
/usr/bin/python3 "$APP" flush --limit 100
```

全局 hooks 在 SessionStart/UserPromptSubmit/before_agent_start 召回。Stop/agent_end 将当前最新完整快照写入
本地 spool 并立即尝试上传；SessionEnd/session_shutdown 再上传最终幂等快照。服务器不可用时保留 queued job，
下一次 capture 或手工 flush 自动补传。
重复事件安全：以
`{source_agent}:{session_id}` 作为归档 ID，对确定性快照计算 SHA-256；相同内容命中本地与远端
幂等，不重复创建，内容变化时创建同一 session 的下一不可变版本。

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

- **`.env` 用相对路径**（`./data/...`），必须从项目目录启动，否则 data 会写到别处。
- **本项目没有 Neo4j 凭证**，也不需要。若 agent 拿着 Neo4j URI/密码说"连不上 memory"，先确认它走的是 Memory Hub 而不是直连 Neo4j。
- **Graphiti 检索不可用 ≠ 空结果**：返回 `GRAPHITI_UNAVAILABLE` 才是后端不可用。
- **健康检查只证明进程活着**：`/health/ready` 的 `dependencies.graphiti` 才反映上游连通；memory 是否真正 `indexed` 要查 `GET /v1/memories/{id}`。
- **不要在对话中回显 `.env` 全文**（虽然当前无 secret，但生产会加 API key）。
- **venv 曾是从 macOS 拷来的坏环境**，在 NAS 上需要重建（见 [deploy.md](references/deploy.md)）。

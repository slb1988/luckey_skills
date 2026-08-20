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
| project 别名定版 | `assets/project-aliases.json`（install 部署到 state dir，hook 与批传共用） |

<memory category="common-patterns">
`MEMORY_HUB_TITLE_LLM` 代码默认 `0`（关闭时退化为启发式标题、不做低价值过滤），置 `1` 才走内网 vLLM。本机是通过 **Machine 作用域**环境变量开启的（`=1`）——在新进程里发现标题走 LLM 属预期；其他机器若想开启须自行设该变量，不要改代码默认值。低价值判定标准含**纯例行运维操作**（git-tool update/sync/commit、skill 更新提交、memory-hub check/install、批量上传归档等只有命令执行结果的会话）——这类会话不上传；但运维中含真实故障排查/bug 修复/技术决策的仍有价值（2026-08-20 用户要求加入，prompt 见 memory_hook.py 与 upload_sessions.py 的 llm_classify_session，两处保持同步）。
</memory>

## 参考文档

| 主题 | 文件 |
|------|------|
| 部署 / 启动 / 重启 / 备份 / 排障 | [references/deploy.md](references/deploy.md) |
| 观测面板（dashboard）开发/部署备忘 | [references/dashboard.md](references/dashboard.md) |
| API 参考（端点总览、写入流程、索引状态、错误码）与实测备忘（Idempotency-Key、字段约束、常用 curl） | [references/api-notes.md](references/api-notes.md) |
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

## HTTP API 与写入流程

端点总览、固定写入流程（初始化上传 → 字节流 → complete → SessionVersion → memory → 等 indexed）、
Memory 索引状态与错误码表见 [api-notes](references/api-notes.md)。

## 检索

搜索只覆盖调用者身份对应的 `global` + `user:*` + `project:{X-Project-Id}` + `agent:{X-Agent-Id}`。
**检索前先根据目标内容选择正确的 project**（调 `GET /v1/projects` 或见 [references/projects.md](references/projects.md)）；
空结果时先切换其他已知 project 重试，确认都不命中再认为"没有这条记忆"。不要因为 Hub 搜不到就绕过 Hub 直查 Graphiti。

检索 curl 见 [api-notes](references/api-notes.md)「常用接口速查」第 1 条。

<memory category="debug-commands">
编辑器内 `memory_search` 0 命中时，绕过扩展用 CLI 复现：pi/claude 的记忆扩展只是薄封装，实际检索全部在 `scripts/memory_hook.py search`（扩展源码里 grep 不到 project/检索逻辑属正常）。`/usr/bin/python3 scripts/memory_hook.py search "<query>" --project <id> --limit 20 --json` 与编辑器内走同一链路，且 `--project` 可探测当前 cwd 派生 scope 之外的项目（如 agent-history、maindev），`--json` 可看原始返回结构排除展示层问题。
</memory>

<memory category="troubleshooting">
Graphiti 语义检索噪音底线高：乱查（大小写无关）也会返回"近似"结果——**返回非空 ≠ 命中，目标不在 top-N ≠ 不存在**。判定"没有这条记忆"前先调大 `--limit`（默认 10）并换关键词重试，再按 project scope 排查。live hook 同样按写入时 cwd 文件夹名派生 project：Windows 端写的记忆散落在 maindev/unity2018/agent-history 等，Mac 端 ObsidianVault 会话默认只能看到 obsidianvault project——跨机器"重启后搜不到"几乎都是 scope 隔离而非故障。
</memory>

## Agent 自动记忆集成

Claude Code / Codex / Pi 三端共用独立应用 `scripts/memory_hook.py`（仅标准库），本地 spool + 失败自动补传。

<memory category="common-patterns">
Pi 扩展带 EXTENSION_VERSION（模板在 `assets/pi-memory-hub.ts`，改模板必须递增版本号）；check 报
`extension version X is outdated` 时重新 install 发布即可。Pi 端全链路留痕（session_start / recall /
search / capture）写在 `${MEMORY_HOOK_STATE_DIR:-~/.local/state/memory-hub-hook}/pi-trace.jsonl`，
分析检索质量先查这个文件。
</memory>

<memory category="common-patterns">
升级版本号的判定规则（2026-08 定版）：**被 hook 直接按路径引用的 script 改动不需要升版本号**
——Claude/Codex settings 和 Pi 扩展都是直接 spawn 仓库里的 `scripts/memory_hook.py`，repo pull 后逻辑即生效。
**只有「安装副本」类产物才必须升版本号**：① Pi 扩展模板 `assets/pi-memory-hub.ts`（安装时渲染拷贝到
`~/.pi/agent/extensions/`，改模板必须递增 EXTENSION_VERSION 并重跑 install）；② 别名定版
`assets/project-aliases.json`（递增 version 并重跑 install 部署到 state dir）。判断依据：产物是否被
install 复制/渲染到仓库外；复制出去的就必须让 check 能感知版本差。
</memory>

> 详细参考：[agent-integration](references/agent-integration.md)（install、身份配置、环境变量、命令）

<memory category="troubleshooting">
在刚执行完 install 的**同一 shell** 里跑 `install_hooks.py check --agents auto`，`identity.source` 显示 `missing` 是预期——user-id 环境变量已写入 `~/.profile`/`~/.zprofile` 但当前进程未加载；新开终端或重启 agent 后即正常。不要据此重装或重复 configure。
</memory>

<memory category="troubleshooting">
agent-integration.md 的 install/configure 示例命令是 macOS 写法（`/usr/bin/python3`、`/Users/sun/...`）。
Windows 上曾发现扩展配置里原样保留了 `/usr/bin/python3` 这个 Unix 路径导致 hook 无法执行——Pi 扩展模板 v2
把 python 路径硬编码为 `/usr/bin/python3`，Windows 端 spawn 全部 exit 127 静默失败（pi-trace.jsonl 里
recall/capture 全红），且 check 因「副本与模板一致」误报 ok。**v3 起模板改为 `__PYTHON_JSON__` 占位符，
由 install_hooks.py 注入本机解释器路径**（优先 /usr/bin/python3，否则 sys.executable）；老机器 check 报
outdated 后重跑 install 即修复。排查「关窗提示有进程未结束」是否 hook 残留时，按命令行列 python.exe 分辨：
本机常驻 python 通常是 UnrealMCP 和 pytest，与 memory-hook 无关；memory_hook.py 是逐事件短进程，正常不常驻。
</memory>

<memory category="troubleshooting">
Spool job 在 capture 时固化 `user_id`（这是设计，防止补传到错误用户）。副作用：身份配置变更（如 install 写入新的 `MEMORY_HUB_CLIENT_USER_ID`）之前积压的 queued job 仍带旧身份，flush 时持续报 `SCOPE_FORBIDDEN` 且不会自愈（实测一次积压 11 个）。看到 spool 反复 403 时直接清理这些旧 job，不要当作服务端权限配置问题排查。
</memory>

<memory category="troubleshooting">
`scripts/tests/` 在 Windows 本机跑 pytest 稳定有 13 个用例失败（10 passed），失败点全在 tearDown 的 `shutil.rmtree`——spool.sqlite3 文件锁 PermissionError，属 Windows 平台既有环境问题（stash 验证未改动代码同样 13 败），不是 regression。评估改动是否破坏测试时对比改动前后的失败集合；要干净结果去 Linux/macOS 跑。
</memory>

## 手动上传历史 session（upload_sessions.py）

`scripts/upload_sessions.py`（仅标准库）把任意机器/目录下的历史 session 记录（`.jsonl`）批量上传到
Hub，每个文件成为独立 session（`{source}:{原始session_id}`），并附一条可检索的 `session_summary`
记忆。适用于 hook 上线前的历史归档、其他电脑导出的 session 等（`memory_hook.py` 没有 backfill 子命令，
capture 只处理当前 live transcript）。

<memory category="code-locations">
历史 session 文件位置（Windows）：Claude Code 在 `%USERPROFILE%\.claude\projects\<slug>\*.jsonl`（文件名即 session UUID）；Pi 在 `%USERPROFILE%\.pi\agent\sessions\<slug>\*.jsonl`（文件名 `<UTC时间戳>_<uuid>.jsonl`，单项目可积累上千个）；Codex 在 `%USERPROFILE%\.codex\sessions\`（递归子目录，单机可积累数百个、上百 MB）。 slug 方案各家不同：`E:\sununity` 在 Claude 是 `E--sununity`，在 Pi 是 `--E--sununity--`——定位时按 `sessions/` 实际列表匹配，不要自行推算。
</memory>

<memory category="troubleshooting">
Codex 新格式 session 文件首行是 `session_meta` 记录，cwd 与 session uuid 只存在于该行的 payload 内、无法从文件路径推出。旧版 `upload_sessions.py` 不识别该格式时 cwd 全部丢失——实测 238 个 codex session 会全部落入兜底 project 且 session id 退化为文件名；已修补 `scan_session_file` 支持（dry-run 238/238 解析成功）。批量归档不熟悉的来源前，先 `--dry-run` 核对 cwd 解析率和 session id 形态（应为 `{source}:{project}:{uuid}` 三段式）再实际上传。
</memory>

幂等保证：对包装后的归档文档（`agent-session-archive/1`，服务端要求 session 文件必须是合法 JSON，
原始 jsonl 不行）计算 SHA-256；上传前比对远端 latest 版本，一致则 `skipped`；所有写操作带确定性
`Idempotency-Key`，中断可直接重跑。内容变化时自动 append 新版本。

<memory category="common-patterns">
批量上传的两条铁律（2026-08-20 用户定版，违反被明确纠正过）：
1. **默认必须双资产一起传（`--hook-namespace`）**：快照 + 完整 session 文件一次到位，禁止先用普通
   模式传单资产、再 `--backfill-full` 补——那是返工。普通单资产模式只用于确实没有完整 jsonl 源的场景。
2. **project 归属必须先经用户 review**：任何批量上传实际执行前，先 `--dry-run` 生成每个 session 的
   归属 project 清单交给用户确认，用户点头后才去掉 dry-run 执行；不得自作主张选定 `--project-id`
   （包括"按 skill 文档默认 agent-history"也不行——文档默认值也要用户确认）。
</memory>

<memory category="common-patterns">
不传 `--project-id` 时按**每个 session 的 cwd 文件夹名**逐个派生 project——全机批量归档会散落到 `admin`、`sununity`、`MainDev`、`ObsidianVault` 等十几个 project（实测 3 个 pi session 落进 2 个 project）。检索按 project 隔离，散落后必须逐 project 切换才能搜全。批量归档历史 session 可考虑 `--project-id agent-history`（hook 归档主库）集中存放，**但选定前必须先给用户 review 归属方案，确认后才执行**。
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
- 大量上传后 memory 经 outbox 异步投递 Graphiti，`indexed` 状态用 `GET /v1/memories/{id}` 跟踪（索引状态定义见 [api-notes](references/api-notes.md)）。

## 关键坑位

- **搜索空结果先怀疑 project scope 错了**：记忆按 `project:{project_id}` 隔离，用错 `X-Project-Id` 必然 0 命中（这是设计行为，不是 bug）。先 `GET /v1/projects` 或查 [references/projects.md](references/projects.md) 换 project 重试。
- **`.env` 用相对路径**（`./data/...`），必须从项目目录启动，否则 data 会写到别处。
- **本项目没有 Neo4j 凭证**，也不需要。若 agent 拿着 Neo4j URI/密码说"连不上 memory"，先确认它走的是 Memory Hub 而不是直连 Neo4j。
- **Graphiti 检索不可用 ≠ 空结果**：返回 `GRAPHITI_UNAVAILABLE` 才是后端不可用。
- **健康检查只证明进程活着**：`/health/ready` 的 `dependencies.graphiti` 才反映上游连通；memory 是否真正 `indexed` 要查 `GET /v1/memories/{id}`。
- **不要在对话中回显 `.env` 全文**（虽然当前无 secret，但生产会加 API key）。
- **venv 曾是从 macOS 拷来的坏环境**，在 NAS 上需要重建（见 [deploy.md](references/deploy.md)）。

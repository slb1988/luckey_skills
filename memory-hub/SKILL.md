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
| 漏传检测回填 | `scripts/backfill_missed_pi_sessions.py`（diff 本地 pi session 与 Hub 已归档，排除 LLM 分析子 session 后调 upload_sessions 幂等补传） |
| project 别名定版 | `assets/project-aliases.json`（install 部署到 state dir，hook 与批传共用） |

「更新发布前后端」是**完整部署流程，不是单纯重启**——「更新」二字 = 先 `git pull` 拉代码，漏掉只跑重启会被视为没完成。固定顺序：① `git pull`（更新，最先做）→ ② 有冲突优先修复冲突 → ③ 本地有未提交改动，更新后及时 commit（不要等用户提醒）→ ④ `cd frontend && npm run build`（前端重构建）→ ⑤ `sh scripts/stop_all.sh && sh scripts/start_all.sh && sh scripts/status.sh`（重启验证）。只有纯「重启」请求才只做 ⑤。memory-hub 自身结构：Hub API(:9287)=后端，dashboard(:9288)=前端（backend BFF + 静态托管 frontend/dist，二者由 start_all.sh 一并拉起）。不要误跳 auto-server-deploy——那是 py_automation 平台（192.168.2.13，`/data/py_automation`）的部署，与 memory-hub 完全无关；pi 现在跑在 NAS 上，auto-server 未授权 NAS 公钥，SSH `dev@10.77.77.4` 会 publickey 拒绝。

判断当前环境（专门针对 memory-hub）：每次运行 memory-hub 相关操作、不确定当前机器是哪种环境时，先从 `.env` 提取环境变量标识 `MEMORY_HUB_ENV`（区别于已有的 `ENVIRONMENT`）。取值只有两种：`release`（生产/发布环境，正式跑 Hub/dashboard/Graphiti 的服务端）与 `dev`（开发环境，含 agent 端与 Dev 职能）。**标识不存在时先提醒用户创建添加，不要瞎猜环境**；拿到标识后按 release/dev 做各自的特有处理（release：部署/重启/迁移；dev：开发/测试/hook 安装与检索）。

`MEMORY_HUB_TITLE_LLM` 代码默认 `0`（关闭时用启发式标题、不走 LLM 判定），置 `1` 才走内网 vLLM（要开启的机器自行设该环境变量，不改代码默认值）。注意「关闭」只关掉 LLM 判定，**启发式低价值过滤始终生效**（`heuristic_meaningful`）：当一个会话的**全部** user 消息都是噪声时判低价值不上传——`is_noise_user_text` 把以 `<`/`/` 开头的消息（pi 的 skill 注入包装、slash 命令）和纯寒暄都视为噪声，且作用于**未剥 skill 包装的原始文本**，所以一个只有 skill 调用、没有任何口语化追问的会话（典型：单次 `git-tool update & commit`）即使 LLM 关闭也会被过滤（2026-08-22 实测）。低价值判定标准含**纯例行运维操作**（git-tool update/sync/commit、skill 更新提交、memory-hub check/install、批量上传归档等只有命令执行结果的会话）——这类会话不上传；但运维中含真实故障排查/bug 修复/技术决策的仍有价值（2026-08-20 用户要求加入，prompt 见 memory_hook.py 与 upload_sessions.py 的 llm_classify_session，两处保持同步）。

**判定材料必须是整个会话，用户目标必须保留**（2026-08-21 用户定版，曾因此误过滤）：① LLM 分类与标题的输入是整会话的非噪声用户消息（`session_user_texts`，条数 >8 时 `head_tail_sample` 首尾各 4 抽样），绝不能只喂窗口尾部——否则实质会话会被结尾的「commit」误杀（当日 job 125/149 实例）；② 归档摘要 distilled 为三段式「首个用户目标/最近用户目标/会话结果」，目标取**首个非噪声用户消息**且先剥 `<skill>...</skill>` 注入包装（`strip_skill_wrapper`——pi 用户消息常是整份 SKILL.md + 末尾一句真实问题，不剥会把目标污染成模板文本），空目标兜底链 first→last→title；③ live hook 上传时经 `load_session_texts` 从 spool full 包重取全量事件提取文本，不依赖 job 行的尾部快照列。

## 参考文档

| 主题 | 文件 |
|------|------|
| 全链路总览（拓扑 / 写入 / 检索 / 观测 / 隐患） | [references/system-overview.md](references/system-overview.md) |
| 部署 / 启动 / 重启 / 备份 / 排障 | [references/deploy.md](references/deploy.md) |
| 排障与调试（检索 0 命中 / hook 生效验证 / spool / 测试平台坑 / Codex session 格式） | [references/troubleshooting.md](references/troubleshooting.md) |
| 观测面板（dashboard）开发/部署备忘 | [references/dashboard.md](references/dashboard.md) |
| API 参考（端点总览、写入流程、索引状态、错误码）与实测备忘（Idempotency-Key、字段约束、常用 curl） | [references/api-notes.md](references/api-notes.md) |
| 已知 project 一览与检索 scope 选择 | [references/projects.md](references/projects.md) |
| 误归档 session 定点清理 runbook（足迹表结构 / named 对象共享坑 / 删除顺序） | [references/cleanup-misscoped-sessions.md](references/cleanup-misscoped-sessions.md) |
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

## Agent 自动记忆集成

Claude Code / Codex / Pi 三端共用独立应用 `scripts/memory_hook.py`（仅标准库），本地 spool + 失败自动补传。
检索以 agent 按需发起为主：Pi v6 额外在每个 session 首轮按 cwd/project 自动预热一次精炼项目背景
（limit=6、最多 5000 字符、默认 120 秒超时，失败后本 session 不重试），后续深挖用 `memory_search`；
Claude/Codex 用 `memory_hook.py search` CLI。行为契约写在 vault `AGENTS.md`「Memory Hub 按需检索」一节。

Pi 扩展带 EXTENSION_VERSION（模板在 `assets/pi-memory-hub.ts`，改模板必须递增版本号）；check 报
`extension version X is outdated` 时重新 install 发布即可。**v5 起改为回合级持久化（enqueue/flush 拆分）**：
agent_end ① 原子写 write-ahead marker（`pi-pending-enqueues/<sessionId>.json`）→ ② **await**
`capture --no-flush --json`（enqueue 进本地 spool 即 durable，不依赖内存计时器）→ ③ 确认
durable 才删 marker → ④ 排程防抖 flush（`MEMORY_HOOK_PI_CAPTURE_DELAY_MS` 默认 5 分钟，
before_agent_start 取消，hub 版本只在 flush 时产生、无 churn）。session_shutdown 收敛在途
enqueue 后做最终 capture；session_start 有界 catch-up 补传遗留 marker（进程被杀的尾部）。
v4 是纯 AFK 防抖（agent_end 只排程计时器，到期才 capture）——防抖窗口内进程被杀即丢尾部。
行为有 Node e2e 值守（`scripts/tests/test_pi_extension_e2e.py`，需 node，无 node 机器跳过）。
留痕有两个文件，分析检索质量先查它们：
- `${MEMORY_HOOK_STATE_DIR:-~/.local/state/memory-hub-hook}/pi-trace.jsonl`——Pi 扩展侧视角
  （v5 事件名互斥：marker_write/marker_delete/marker_quarantine、enqueue_done（含 outcome/
  job_id/sha256/transcript_bytes）、flush_schedule/flush_cancel/flush_done（outcome=completed/
  busy/failed）、catchup_scan/catchup_done、final_capture、session_start、project_bootstrap、search）；
- 同目录 `hook-trace.jsonl`——脚本侧 ground truth（memory_hook.py 的 search，三端 agent 共用，
  含完整输出、query、project_id、facts_count），claude/codex 无 pi-trace 时只能查这个。

search 输出不包含用户身份与概要（2026-08-20 起，format_context 已移除）：多身份场景下静态
概要是先验知识、会影响模型判断；user_id 仅用于服务端检索 scoping，不作为文本输出。检索无结果时不输出任何内容。
该约束同时适用于 Pi 首轮 `project_bootstrap` 与按需 search 的输出。

升级版本号的判定规则（2026-08 定版）：**被 hook 直接按路径引用的 script 改动不需要升版本号**
——Claude/Codex settings 和 Pi 扩展都是直接 spawn 仓库里的 `scripts/memory_hook.py`，repo pull 后逻辑即生效。
**只有「安装副本」类产物才必须升版本号**：① Pi 扩展模板 `assets/pi-memory-hub.ts`（安装时渲染拷贝到
`~/.pi/agent/extensions/`，改模板必须递增 EXTENSION_VERSION 并重跑 install）；② 别名定版
`assets/project-aliases.json`（递增 version 并重跑 install 部署到 state dir）。判断依据：产物是否被
install 复制/渲染到仓库外；复制出去的就必须让 check 能感知版本差。

> 详细参考：[agent-integration](references/agent-integration.md)（install、身份配置、环境变量、命令）

`test_pi_extension_e2e.py`（Node 驱动 .mjs + fake hook .mjs）可行的前提是 **Node ≥24 原生 type-stripping 直接跑渲染后的 TS 扩展**，无构建步骤。写这类驱动/断言的铁律：capture 完成的权威信号是 **pi-trace.jsonl 落盘**，不是 hub 子进程退出、也不是 fake hook 日志——fake hook 在 stdin `end` 时写日志，而扩展在子进程 `close` 事件后才写 trace，两者之间存在窗口期；按错误信号等待会导致断言失败点逐次漂移（实测同一用例失败位置随机）。驱动失败时保留/打印 tmpdir 现场 artifact 再清理，否则竞态无法事后诊断。

## 手动上传历史 session（upload_sessions.py）

`scripts/upload_sessions.py`（仅标准库）把任意机器/目录下的历史 session 记录（`.jsonl`）批量上传到
Hub，每个文件成为独立 session（`{source}:{原始session_id}`），并附一条可检索的 `session_summary`
记忆。适用于 hook 上线前的历史归档、其他电脑导出的 session 等（`memory_hook.py` 没有 backfill 子命令，
capture 只处理当前 live transcript）。

配套脚本 `scripts/backfill_missed_pi_sessions.py` 回答「有没有漏传」并一键补传（本机专用，2026-08-22 加入）。
检测原理：Hub `sessions` 表是全部已归档 session 的 ground truth（id 形如 `pi:<project>:<uuid>`），本地
pi session 文件名 `<ts>_<uuid>.jsonl` 的 uuid 即 session id，两边按 UUID 求 diff（local − hub）=
全量漏传清单——比查 spool/pi-trace 更直接，且能覆盖 hook 上线前的历史 session。脚本再按首条 user 消息
签名排除 auto-skill extraction 等 LLM 分析子 session，最后以 `--hook-namespace` 调 upload_sessions.py
幂等回填（可中断重跑）。

历史 session 文件位置（Windows）：Claude Code 在 `%USERPROFILE%\.claude\projects\<slug>\*.jsonl`（文件名即 session UUID）；Pi 在 `%USERPROFILE%\.pi\agent\sessions\<slug>\*.jsonl`（文件名 `<UTC时间戳>_<uuid>.jsonl`，单项目可积累上千个）；Codex 在 `%USERPROFILE%\.codex\sessions\`（递归子目录，单机可积累数百个、上百 MB）。 slug 方案各家不同：`E:\sununity` 在 Claude 是 `E--sununity`，在 Pi 是 `--E--sununity--`——定位时按 `sessions/` 实际列表匹配，不要自行推算。

幂等保证：对包装后的归档文档（`agent-session-archive/1`，服务端要求 session 文件必须是合法 JSON，
原始 jsonl 不行）计算 SHA-256；上传前比对远端 latest 版本，一致则 `skipped`；所有写操作带确定性
`Idempotency-Key`，中断可直接重跑。内容变化时自动 append 新版本。

本机 project 归属是**机器级映射（字典）**，写在 state dir 的 `project-aliases.local.json`（
`install_hooks.py install --project <id>` 写入 `{"aliases":{"*":"<id>"}}`，不进 git、不随 skill
模板扩散，其他机器/用户不受影响）。优先级：`--project`/`--project-id` 显式参数 > 本机 local 映射 >
共享模板（`assets/project-aliases.json` 部署）> cwd 派生兜底；映射里 `"*"` 是 catch-all（如
`{"*":"nas"}` = 本机全部归 `nas`，具体条目如 `{"memory-hub":"memory-hub"}` 优先于 `*`）。本机映射
一旦设置，capture/search/批量归档默认按它归 project，与其他机器的项目完全隔离。install 未给
`--project` 时：交互终端询问（默认建议主机名），非交互只输出建议不落盘。**本机映射只能写系统目录
（state dir），绝不允许改 skill 模板 `assets/project-aliases.json` 来映射本机名**（那会污染共享模板、
影响其他用户）。

批量上传的两条铁律（2026-08-20 用户定版，违反被明确纠正过）：
1. **默认必须双资产一起传（`--hook-namespace`）**：快照 + 完整 session 文件一次到位，禁止先用普通
   模式传单资产、再 `--backfill-full` 补——那是返工。普通单资产模式只用于确实没有完整 jsonl 源的场景。
2. **project 归属必须先经用户 review**：任何批量上传实际执行前，先 `--dry-run` 生成每个 session 的
   归属 project 清单交给用户确认，用户点头后才去掉 dry-run 执行；不得自作主张选定 `--project-id`
   （包括"按 skill 文档默认 agent-history"也不行——文档默认值也要用户确认）。

本机 local 映射（`project-aliases.local.json`）未设置时，不传 `--project-id` 会按**每个 session 的 cwd 文件夹名**逐个派生
project——全机批量归档会散落到 `admin`、`sununity`、`MainDev`、`ObsidianVault` 等十几个 project
（实测 3 个 pi session 落进 2 个 project）。检索按 project 隔离，散落后必须逐 project 切换才能搜全。
批量归档历史 session 可考虑 `--project-id agent-history`（hook 归档主库）集中存放，**但选定前必须先给
用户 review 归属方案，确认后才执行**。

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

- **删 session 对象文件时 named 对象可能物理共享**：归档快照是 sha 寻址（`objects/<2hex>/<sha>.json.gz`），但完整 session 文件是**文件名寻址**（`objects/named/<source>/<原始文件名>.json.gz`）——同一 jsonl 重传到别的 project 会撞同一个 storage_key，后上传者覆盖物理文件。只按 sha256 判孤儿会误删正确副本的文件；必须同时按 storage_key 反查 files 表。完整清理流程见 references/cleanup-misscoped-sessions.md。
- **搜索空结果先怀疑 project scope 错了**：记忆按 `project:{project_id}` 隔离，用错 `X-Project-Id` 必然 0 命中（这是设计行为，不是 bug）。先 `GET /v1/projects` 或查 [references/projects.md](references/projects.md) 换 project 重试。
- **`.env` 用相对路径**（`./data/...`），必须从项目目录启动，否则 data 会写到别处。
- **本项目没有 Neo4j 凭证**，也不需要。若 agent 拿着 Neo4j URI/密码说"连不上 memory"，先确认它走的是 Memory Hub 而不是直连 Neo4j。
- **Graphiti 检索不可用 ≠ 空结果**：返回 `GRAPHITI_UNAVAILABLE` 才是后端不可用。
- **健康检查只证明进程活着**：`/health/ready` 的 `dependencies.graphiti` 才反映上游连通；memory 是否真正 `indexed` 要查 `GET /v1/memories/{id}`。
- **不要在对话中回显 `.env` 全文**（虽然当前无 secret，但生产会加 API key）。
- **venv 曾是从 macOS 拷来的坏环境**，在 NAS 上需要重建（见 [deploy.md](references/deploy.md)）。
- **本机跑脚本用 `python3`，不是 `/usr/bin/python3`**（NAS 上无此路径），见 [agent-integration.md](references/agent-integration.md)。
- **`enqueue_done outcome=skipped_capture_env` = 快照根本没进 spool**（write-ahead marker 直接删，不是上传失败，补传也不会捞到）：memory-hub 扩展自身的 `skipCapture` 是**加载时缓存**的，但 spawn 出的 hook 子进程继承的是**当前**进程环境——任何扩展把 `MEMORY_HUB_SKIP_CAPTURE=1` 挂在共享 `process.env` 上，窗口期内所有 capture 都被整段跳过。实测污染源：auto-skill 扩展在 extraction 子 session 的分钟级 `await prompt()` 期间持有了这个变量（已修复收窄到 createAgentSession/dispose 两个毫秒级窗口）；现象特征是「同机其他项目正常 enqueued、某项目连续 skipped_capture_env」。hook 侧另有 transcript 首消息签名检测（`skipped_extraction`）兜底，所以收窄窗口是防误判不是防泄漏。
- **幂等重放拿回过期 upload = FIFO 永久队头阻塞**（2026-08-29 实例，job 1210 卡 106 次、28 个 job 饿一天）：initiate 上传的幂等键是确定性的，服务端按 key 原样重放首次响应，上传会话 TTL 10 分钟过期后重试拿到的仍是同一个失效 upload_id；PUT 失效 URL 时服务端不读 body 直接 404/410 并关连接，大 body 客户端收到的是 WinError 10054（连接重置）而非 404，被误判为瞬时网络错误无限重试。特征：flush 永远 `failed:1`、`last_error=WinError 10054`、queued 堆积但 search 完全正常（GET 不受影响）。排查路径：spool.sqlite3 jobs 表查队头 last_error → curl 复现 GET/POST 正常 → 跟到 PUT expired upload。修复：`_upload_file` 检测 file status `expired` / PUT|complete 失败后换全新幂等键重建上传会话（至多 3 轮，retry_salt=job.attempts），`request()` 把裸 OSError 包成 HubError 让 full 上传降级生效。服务端待修：`initiate_upload` 幂等重放应检查 upload 是否过期、过期则新建而非原样返回。
- **capture/flush 只读进程环境的 `MEMORY_HUB_API_KEY`，注册表回退只有 check 有**：所以 check 报 `token_accepted: true` 不代表运行中的 agent 能上传——key 持久化进注册表**之前**被 Orca/终端拉起的进程环境里没有它，全部 401，必须重启 agent（及其父级 Orca/终端）才继承。spool 的 flush 是 **FIFO 队头阻塞**：队头 job 持续 401 重试会饿死后面 attempts=0 的 job。应急恢复：用注册表里的 key 临时注入当前 shell 环境，手动跑一次 `memory_hook.py flush` 清积压，再重启 agent。

Hub 投递 Graphiti 前会过一道内容清洗层 `strip_archival_boilerplate()`（service.py）：按模式剥掉归档摘要开头的元数据套话，只留知识正文进入抽取。当前覆盖三种前缀：`xx 会话归档，工作目录：…。`（legacy）、`xx 会话「标题」，工作目录：…。`、`xx 会话「标题」（日期，工作目录：…）。`。新前缀出现时在此加模式即可对存量内容生效——它作用于投递时刻而非写入时刻，改模式不需要回写 SQLite。

重建某 group 的图谱映射用 `scripts/reingest_group.py <group> [--noise-only] [--dry-run|--yes]`：删 episode（remove_episode 级联删派生边和独占实体）后把 SQLite 原记忆重入 outbox，episode uuid == memory_id 溯源不变。`--noise-only` 经 cypher-ro 反查命中噪声实体的 episode 定点重建（大 group 必用）。只处理 Hub 有记录的 episode，Graphiti 独有的只报告不删；级联删除会漏孤儿实体，重建后需按模式补一次终扫。事故全文：memory-center `incidents/2026-08-20-entity-extraction-noise.md`。

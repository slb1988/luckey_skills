# Agent 自动记忆集成（Hooks）

Claude Code / Codex / Pi 三端共用独立应用 `scripts/memory_hook.py`。它不 import、调用或依赖
Memory Hub 项目及其 venv，只使用 Python 标准库访问远端 HTTP API。

> **本机（NAS）解释器路径**：这台机器没有 `/usr/bin/python3`，解释器在
> `/share/homes/slb1988/.local/bin/python3`（`which python3` 即此路径）。下文所有示例里的
> `/usr/bin/python3` 在本机都要写成 `python3`，否则 exit 127「No such file or directory」。
> hook 内部 spawn 路径由 install 注入、不受影响；只有手工在 shell 跑脚本
> （install / check / configure / search / status / flush）时才需要注意。

每次 capture 先生成确定性 gzip 快照并写入本机 SQLite spool，然后才访问服务器。服务器不可用时
job 永久保留为 `queued`；后续 Stop、SessionEnd、agent_end 或手工 flush 会自动补传。因此 hook
仍可 fail-open，不会阻止 Agent，也不会因短期网络故障丢失 session。

快照格式为 `agent-session/3`，保存最近 10 条 user/assistant 消息，并通过 `full_session` 指针关联
`agent-session-full/1` 全量事件资产。窗口快照不含工具事件、无法解析事件和 Markdown fenced code；
Markdown 标题、列表、链接和解释正文保留。Spool 每个 job 固化 `user_id`，所以稍后 flush 时不会
因进程环境变化而补传到错误用户。

## 首轮自动召回（recall / bootstrap）

**三端都有首轮自动召回**（2026-08-29 起）：Pi 走扩展 `before_agent_start`；Claude/Codex 走
`UserPromptSubmit` hook → `memory_hook.py recall --source <agent>`。同一语义：首个用户 prompt +
project hint 做一次 focused recall（limit=6、默认最多 4000 字符、120 秒故障上限），**每个 session
只查一次**——recall 用 `recall-markers/` 落盘标记（含失败/空结果），Pi v12 用
`pi-bootstrap-done/` 持久标记（进程内集合仅作同进程快路径）；超时/空结果/
服务故障都不在后续 prompt 重试。结果经 stdout 注入上下文；`MEMORY_HOOK_RECALL=0` 关闭
Claude/Codex 侧，Pi 侧用 `MEMORY_HOOK_PI_BOOTSTRAP_RECALL=0`。后续深挖用 `memory_search`（Pi）/
`memory_hook.py search` CLI（Claude/Codex）；首次预算可用 `MEMORY_HOOK_PI_BOOTSTRAP_LIMIT` 与
`MEMORY_HOOK_PI_BOOTSTRAP_MAX_CHARS` 调整（Pi），避免每个 session 固定注入大段历史。
行为契约写在 vault `AGENTS.md`「Memory Hub 按需检索」一节。

search 输出不包含用户身份与概要（2026-08-20 起，format_context 已移除）：多身份场景下静态
概要是先验知识、会影响模型判断；user_id 仅用于服务端检索 scoping，不作为文本输出。检索无结果时不输出任何内容。
该约束同时适用于 Pi 首轮 `project_bootstrap` 与按需 search 的输出。

## 首次用户身份配置

Hook 客户端没有内置固定用户，也不得用 `agent_id` 代替用户身份。身份在 install 时通过
`--user-id` 持久化（推荐），或用 `configure` 写本机 profile。配置前必须先向用户确认以下
三项信息，不得自行猜测：

- 长期稳定的内部 `user_id`（仅字母、数字、`.`、`_`、`:`、`-`，最长 128 字符）；
- 显示名称；
- 简短概要，例如身份、偏好或长期目标，不得包含密码、API Key 等秘密。

若环境变量未指定用户，客户端会从 hook 工作目录向上查找最近的 `.team/settings.local.json`，读取字符串
字段 `currentMember` 作为候选 `user_id`，优先于本机 profile。文件缺失、JSON 无效或 `currentMember`
不是合法字符串时，安全回退到本机 profile 或未配置状态。

确认后执行：

```bash
/usr/bin/python3 "$SKILL_DIR/scripts/memory_hook.py" configure \
  --user-id 'internal-user-id' \
  --display-name 'Display Name' \
  --summary '身份、偏好或长期目标的简短概要'
```

> 更推荐的做法是直接运行 `install_hooks.py install --user-id ...`：
> 它会把 user-id 持久化到用户级环境变量（见「install 关键字」一节），全局所有进程统一从环境变量取值；
> `configure` 写入的本机 `client-profile.json` 仅作为环境变量缺失时的 fallback。

配置以 `0600` 权限保存到
`${MEMORY_HOOK_STATE_DIR:-~/.local/state/memory-hub-hook}/client-profile.json`。配置完成前，capture
仍会把最近会话安全暂存到本机，但这些 job 使用隔离占位身份，不会进入上传队列；配置成功后会归属到
确认的用户并尝试补传。search 在配置完成前不会调用 Hub（打印配置提醒并退出码 2）。

## install 关键字

用户在 Memory Hub 语境输入 `install` 或要求安装 hooks 时，直接执行：

```bash
SKILL_DIR="<本 SKILL.md 所在目录的绝对路径>"
/usr/bin/python3 "$SKILL_DIR/scripts/install_hooks.py" install --agents auto \
  --user-id 'internal-user-id' \
  --project 'nas'   # 可选：本机级 project，见下
```

必须将占位符替换为加载本 Skill 时获得的实际目录，不得相对当前工作目录猜测。`auto` 配置本机检测到的
Claude Code、Codex、Pi；用户明确要求全部安装时改用 `--agents all`。不得手工拼装 Hook JSON。
install 同时会把进程环境里的 `MEMORY_HUB_API_KEY` 一并持久化，所以生产环境应先 export key 再跑 install。

> 全新机器无法自助生成 token：dashboard 的 `POST /api/v1/auth/tokens` 本身也要求
> `DASHBOARD_API_KEY`，首次接入必须有人在面板 UI 手工生成 agent token（mhu_...）。

### Windows pty 下 install 的历史交互坑（2026-08 实测，project prompt 已移除）

旧版 install 有两处交互输入：

1. 未给 `--project` 且本机无映射时，曾用 `sys.stdin.readline()` 询问本机 project；agent 的伪终端可能
   把空输入当成确认，按主机名建议值静默写入 `{"*": "<建议值>"}`。该分支现已删除：**只有显式
   `--project` 才能新建或修改 catch-all**；普通 install 只报告并保留已有映射，无映射时只输出建议，
   不读 stdin、不落盘。
2. API key 既不在进程环境也不在持久化位置：`getpass.getpass()` 隐藏输入 token。

agent 的 pty shell（pi bash tool 等）里仍需注意 API key prompt：Windows 的 getpass 实现是
`win_getpass`（msvcrt 直读控制台），**完全无视 stdin 重定向**，没人敲键盘就会一直阻塞
（install 自身无超时）。

非交互正确姿势：

- 首选：预先把 `MEMORY_HUB_API_KEY` 持久化（或写进进程环境）；仅在确定整台机器只服务一个
  project 时才显式加 `--project <id>`；
- 备选：monkeypatch 包住 main——
  ```bash
  python -c "import getpass,sys; getpass.getpass=lambda prompt='':''; \
    sys.argv=['install_hooks.py','install','--agents','auto','--user-id','<id>']; \
    sys.path.insert(0, r'<SKILL_DIR>\scripts'); import install_hooks; raise SystemExit(install_hooks.main())"
  ```
- 已卡住时定位：`python -X faulthandler` 并在调 main 前
  `faulthandler.dump_traceback_later(25, exit=True)`，栈直接指到阻塞行。

误落盘的本机映射在 state dir `project-aliases.local.json`，删文件即恢复 cwd 派生归属；它与用户身份
（`MEMORY_HUB_CLIENT_USER_ID` / `client-profile.json`）是两套独立配置，删映射不影响身份。

**只有单一 project 的专用机器才建议指定 `--project`**：它写入 state dir 的
`project-aliases.local.json`（机器级字典映射 `{"aliases":{"*":"<id>"}}`，不进 git、不随 skill
模板扩散），本机所有 capture/search/批量归档默认都落该 project。多 workspace 工作站不应设置
`"*"` catch-all；需要例外时使用具体条目（如 `{"memory-hub":"memory-hub"}`）。未提供 `--project`
时，install 不再交互询问或自动持久化主机名，只保留已有配置；没有本机映射时按 cwd 派生
（含 `assets/project-aliases.json` 部署的共享别名）。

**install 必须指定用户身份**：`--user-id` 必填（或已预设 `MEMORY_HUB_CLIENT_USER_ID`）。
安装器会把它**持久化到用户级环境变量**：
Windows 写入注册表 `HKCU\Environment` 并广播 `WM_SETTINGCHANGE`；POSIX 写入 `~/.profile`
标记块（macOS 同时写 `~/.zprofile`）。之后本机所有新启动的 agent / hook 进程都默认从环境变量取身份，
优先级高于 `.team/settings.local.json` 与 `client-profile.json`；已在运行的进程需重启才能看到。
环境身份只携带 user_id；display_name / summary 仅来自本机 `client-profile.json`（`configure` 写入）。

安装成功必须同时满足：

- Claude Code/Codex 各有且仅有 3 个 Memory Hub handlers：UserPromptSubmit（首轮自动召回，
  `recall` 子命令，2026-08-29 恢复：每 session 一次、fail-open、恒 exit 0）、Stop、SessionEnd。
- Stop 每轮直接执行 `capture`，不得带 `--flush-limit 0`；SessionEnd 再提交最终幂等快照。
- Codex 必须通过 app-server `hooks/list` 确认 3 个 handlers 均为 `trusted`，且没有 Memory Hub 相关 warning/error。
- Pi 全局扩展必须包含 `before_agent_start`、`agent_end`、`session_shutdown`；`before_agent_start` 在每个
  session 的首轮按 cwd/project 阻塞执行一次精炼背景检索（默认 limit=6、最多 4000 字符、120 秒超时），
  然后取消挂起归档。无结果、报错或超时均 fail-open，且本 session 后续 prompt 不重试；`agent_end`
  走 AFK 防抖上传（默认空闲 5 分钟才归档，新 prompt 取消重计），`session_shutdown` 立即归档。
- 安装器返回的各 agent `ok=true`。服务健康检查失败可保留 durable spool，但必须明确报告"已安装、尚未端到端验证"，不得宣称上传链路正常。

安装或升级后执行只读复检：

```bash
/usr/bin/python3 "$SKILL_DIR/scripts/install_hooks.py" check --agents auto
```

check 的复检项除 hook 安装副本外还包括：

- **auth（2026-08 起）**：探测服务端是否强制认证（匿名请求 `/v1/projects` 返 401 即为生产模式）。
  强制认证时校验 `MEMORY_HUB_API_KEY`：进程环境缺失会回退解析 `~/.profile`/`~/.zprofile`
  （Windows 读注册表）区分「完全没配」与「已持久化但本进程未加载」，探测身份也按同一回退链解析
  （避免占位用户被 scope 拦截误判 token 无效）；两者皆无 → check 失败并按平台给出持久化指引；
  已配置还会实测 token 是否被服务端接受（401 → 失败提醒重新生成）。服务端不可达时 auth 项降级为
  warning 不影响总结果。补配 key 后，认证失败期积压的 queued job 用 `memory_hook.py flush --limit 100`
  重放（重复跑到 queued=0）；job 入队时已固化 user/project，事后改本机映射不回写已入队 job。
- **Pi 扩展 EXTENSION_VERSION**：已安装副本的版本号与模板
（`assets/pi-memory-hub.ts`）不一致时报 `extension version X is outdated (managed Y); rerun install`，
重新执行 install 即可重新发布。修改模板后必须递增模板里的版本号，否则 check 无法感知升级。

## Pi 扩展机制与全链路留痕

Pi 扩展带 EXTENSION_VERSION（模板在 `assets/pi-memory-hub.ts`，改模板必须递增版本号）；check 报
`extension version X is outdated` 时重新 install 发布即可。**v5 起改为回合级持久化（enqueue/flush 拆分）**：
agent_end ① 原子写 write-ahead marker（`pi-pending-enqueues/<sessionId>.json`）→ ② **await**
`capture --no-flush --json`（enqueue 进本地 spool 即 durable，不依赖内存计时器）→ ③ 确认
durable 才删 marker → ④ 排程防抖 flush（`MEMORY_HOOK_PI_CAPTURE_DELAY_MS` 默认 5 分钟，
before_agent_start 取消，hub 版本只在 flush 时产生、无 churn）。session_shutdown 收敛在途
enqueue 后做最终 capture；session_start 有界 catch-up 补传遗留 marker（进程被杀的尾部）。
v4 是纯 AFK 防抖（agent_end 只排程计时器，到期才 capture）——防抖窗口内进程被杀即丢尾部
（v4→v5 的设计定版依据与丢失窗口分析见 [troubleshooting.md](troubleshooting.md)）。
行为有 Node e2e 值守（`scripts/tests/test_pi_extension_e2e.py`，需 node，无 node 机器跳过）。

**v18 起首轮与手工 `memory_search` 都由 Hub 做同步 LLM 质量门禁**：客户端请求
`search-v2 quality_mode=llm`，服务端也是该默认值；Hub 先检索候选，再用一次批量 LLM 调用逐条判
0-3 分，只返回 2/3 分。审核不可用、超时或响应不完整时返回 503，客户端不得回退 v1 绕过。
Pi 的 `before_agent_start` 会等待该在线请求，但不再弹出玩家逐条评分 UI；只把服务端放行结果注入
system prompt。被拒候选、理由、证据、冲突和错误只写服务端 `retrieval_judgments`，不会污染玩家或
agent 上下文。单次候选上限 10，首轮仍取 6 条/最多 4000 字符，客户端等待预算 120 秒，服务端
审核调用预算 110 秒。

v12-v17 的玩家评分 UI、`pi-recall-scores.jsonl` 和 feedback 上报路径现为历史兼容代码，不再由 v18
首轮触发；旧环境变量 `MEMORY_HOOK_PI_BOOTSTRAP_SCORE` 也不再恢复该 UI。跨进程 session 去重和
后端门禁行为都有 Node e2e 值守。

**v13-v17 的评分 widget 已在 v18 停用**。首个用户问题仍会被提炼为检索 query，但问题与内部候选
不再通过 widget/select 暴露；需要复盘时按 retrieval_id 查询服务端 judgment 日志。

**v14 起 Orca worker 的首问会先提取最后一个 `=== TASK ===` 之后的真实任务，再做 1200 字截断**；
旧逻辑先截断整段 prompt，8KB 编排说明会把 TASK 完全挤掉，导致 query 与评分界面只显示 Orca
操作样板。review/trace 增加 `prompt_source=orca_task|user_prompt`，便于后续区分入口质量与排序质量。

**v15 起 search-v2 会把 Hub 返回的 `retrieval_id/query_hash/policy_version` 透传给 Pi**；v18 又透传
聚合 `quality` 元数据。当前评分由服务端在返回前完成并直接写 `retrieval_judgments`，不再依赖玩家
fire-and-forget feedback 才形成评估样本。只有 v2 明确 404（旧服务完全没有端点）时允许兼容回退 v1；
审核 503、坏响应或其他错误都必须 fail-open 到“本轮不注入”，不能用 v1 返回未审核候选。

**v16 起清理两类真实体验缺口**：① auto-skill extraction prompt（以及加载时已明确
`MEMORY_HUB_SKIP_CAPTURE=1` 的 opt-out session）跳过自动 bootstrap，记录
`project_bootstrap.outcome=skipped_extraction|skipped_capture_env` 并写完成 marker；手工
`memory_search` 工具仍可用。这样 extraction 不再被旧 extraction 记忆递归污染，也不浪费检索和注入
预算。② `memory_search` 新增可选 `project` 参数；任务实际属于其他 project、但 Pi 从当前仓库启动时，
可显式切换 scope（如 `project="maindev"`），不必换工作目录或绕到 shell CLI。首轮所有候选被用户
打 0 时，候选本身仍全部剔除，只给 agent 注入一条很短的跨 project 重试提示，避免模型不知道召回已
失败而继续猜测。三项均不增加服务端请求次数、LLM 或 embedding 成本。

**v17 起把“检索留痕”与“注入模型”拆开**：无 UI session 没有玩家评分能力，候选只进入
`pi-recall-reviews.jsonl`，不再像 v12-v16 那样把 `score=null` 的候选当作可注入候选。这样仍可在后续
集体 review 中评估 headless/worker 的召回准确度，同时避免未验证信息污染子任务和浪费最多 4000 字符
上下文。另支持首问开头的 `project:<id>` scope 指令（包括 Orca `=== TASK ===` 后的第一段），例如
`project:maindev 调研 SyncStaticMeshAssetMetaDT`；扩展会从 query 中移除指令，并给 bootstrap search
显式传 `--project maindev`。只识别 focused prompt 开头且 project id 通过严格字符校验的指令，正文中
偶然出现的 `project:` 不会改 scope。trace/review 增加 `project_override`，不增加查询次数。

**Pi 的 session memory 写入带本地可读审计稿**：`memory_hook.py` 从 full-session spool 提取出
首个用户目标、最近用户目标和最终助手结果并生成 `distilled_content` 后，必须先把两者原子写入
`${MEMORY_HOOK_STATE_DIR:-~/.local/state/memory-hub-hook}/memory-drafts/pi/<project>/`
下的 Markdown 文件，才允许调用 `POST /v1/memories`。文件名由 source session id 加 snapshot SHA
组成，相同内容幂等覆盖，不同内容版本分别保留；不同 project 不冲突。草稿保留每条
最多 32 KiB 的提取源文本以及实际受 700/700/1400 字符预算约束的提交文本，适合直接比较定位
“存前抽取不完整”还是“提交预算截断”。本地落盘失败时远端 memory 写入也失败，durable spool job
保持 queued 等待下次 flush，不能绕过审计前置条件。草稿在 job 完成后仍保留；完整原始事件仍以
full-session 资产为准。该改动只在直接引用的 Python script 中，不需要升级 Pi 扩展版本或重装。

分析检索质量优先查以下留痕文件：

- `${MEMORY_HOOK_STATE_DIR:-~/.local/state/memory-hub-hook}/pi-trace.jsonl`——Pi 扩展侧视角，
  每次与 Memory Hub 的交互追加为 JSONL。当前事件名（v5+ 互斥）：

| kind | 时机 | 关键字段 |
|---|---|---|
| `session_start` | 会话开始 | session_id、cwd |
| `project_bootstrap` | session 首轮项目背景预热（v12+） | query、limit、project_override、outcome（v18：injected/empty/error/timeout/disabled/skipped_extraction/skipped_capture_env）、exit_code、duration_ms、result_chars；审核细节按 retrieval_id 在服务端查 |
| `project_bootstrap_skip` | 已有持久完成标记，恢复旧 session 不重复回溯（v12） | session_id、outcome=already_completed |
| `recall_score` / `recall_score_wait` | v12-v17 历史玩家评分事件；v18 不再产生 | total、scored、dropped、kept / rank、outcome |
| `search` | memory_search 工具调用 | query、limit、exit_code、duration_ms、result（结果全文） |
| `marker_write` / `marker_delete` / `marker_quarantine` | write-ahead marker 生命周期（v5） | sessionId 等 |
| `enqueue_done` | `capture --no-flush` 入队完成（v5） | outcome、job_id、sha256、transcript_bytes |
| `flush_schedule` / `flush_cancel` / `flush_done` | 防抖 flush 排程 / 取消 / 完成（v5） | outcome=completed/busy/failed |
| `catchup_scan` / `catchup_done` | session_start 有界 catch-up 补传遗留 marker（v5） | — |
| `final_capture` | session_shutdown 收敛在途 enqueue 后的最终 capture（v5） | — |

  v4 及更早的事件名（`capture_schedule`/`capture_cancel`/`capture`）已随 v5 废弃，只会在老 trace 里出现。
- 同目录 `hook-trace.jsonl`——脚本侧 ground truth（memory_hook.py 的 search，三端 agent 共用，
  含完整输出、query、project_id、facts_count），claude/codex 无 pi-trace 时只能查这个。
- 同目录 `pi-recall-reviews.jsonl` / `pi-recall-scores.jsonl`——v12 起的 session 级完整首轮回溯包与
  候选级真实用户标注；集体 review 时先按 `session_id` 与 Pi transcript 关联。
- 同目录 `memory-drafts/pi/<project>/*.md`——Pi 向 Hub 写 session memory 前的可读提取稿；同时包含
  较完整源字段与实际 outbound `distilled_content`，不受 trace 单字段 20k 字符截断影响。

每轮检索测试/分析前用 `python3 scripts/rotate_pi_trace.py`（可加 `--include-hook-trace`）把旧
trace 轮转到 `trace-backups/`，保证当轮数据干净；扩展按事件 append 写 trace、无持久句柄，
会话运行中轮转也安全。

单字段超 20k 字符截断；写日志失败不阻断 agent。Claude/Codex 端的留痕在 spool
（`memory_hook.py status` 可查 job 状态），不在此文件。

安装器仅替换命令路径包含 `memory-hub/scripts/memory_hook.py` 的 handlers，保留其他 Hook，并在修改配置前生成
`*.memory-hub.bak` 备份。运行中的 Agent 可能缓存配置；完成后提示重启对应 Agent 或执行其 reload 命令。

## 版本号升级判定规则（2026-08 定版）

**被 hook 直接按路径引用的 script 改动不需要升版本号**——Claude/Codex settings 和 Pi 扩展都是直接
spawn 仓库里的 `scripts/memory_hook.py`，repo pull 后逻辑即生效。
**只有「安装副本」类产物才必须升版本号**：① Pi 扩展模板 `assets/pi-memory-hub.ts`（安装时渲染拷贝到
`~/.pi/agent/extensions/`，改模板必须递增 EXTENSION_VERSION 并重跑 install）；② 别名定版
`assets/project-aliases.json`（递增 version 并重跑 install 部署到 state dir）。判断依据：产物是否被
install 复制/渲染到仓库外；复制出去的就必须让 check 能感知版本差。

## Pi 扩展 e2e 测试铁律

`test_pi_extension_e2e.py`（Node 驱动 .mjs + fake hook .mjs）可行的前提是 **Node ≥24 原生 type-stripping 直接跑渲染后的 TS 扩展**，无构建步骤。写这类驱动/断言的铁律：capture 完成的权威信号是 **pi-trace.jsonl 落盘**，不是 hub 子进程退出、也不是 fake hook 日志——fake hook 在 stdin `end` 时写日志，而扩展在子进程 `close` 事件后才写 trace，两者之间存在窗口期；按错误信号等待会导致断言失败点逐次漂移（实测同一用例失败位置随机）。驱动失败时保留/打印 tmpdir 现场 artifact 再清理，否则竞态无法事后诊断。

## 环境变量

```bash
export MEMORY_HUB_URL=http://10.77.77.6:9287
export MEMORY_HUB_AGENT_ID=claude-code-mac
export MEMORY_HUB_ARCHIVE_PROJECT_ID=agent-history
#   ↑ 仅空 cwd 时的兜底；真正的本机级 project 是 state dir 的 project-aliases.local.json
#     （install --project 写入 {"aliases":{"*":"<id>"}} 字典映射，支持 "*" catch-all），
#     设置后覆盖 cwd 派生，本机所有写入/检索默认都落该 project
# 可用环境变量指定全局用户身份
# （install_hooks.py install 会把它持久化到用户级环境变量，全局生效）：
# MEMORY_HUB_CLIENT_USER_ID=internal-user-id
# MEMORY_HUB_API_KEY=...          # 生产必填（mhu_ agent token，面板 http://10.77.77.6:9288/ 生成）；
#                                  # 可手工写进 profile 标记块；install 没有 --api-key 参数
#                                  # （install_hooks.py 全部参数只有 --agents/--home/--codex-bin/--cwd/
#                                  # --user-id/--project），而是自动沿用进程环境/profile 里已有的 key
#                                  # 并持久化（升级重装不丢）；check 的 auth 项会校验它是否设置且被服务端接受
# MEMORY_HOOK_TIMEOUT_SECONDS=8
# MEMORY_HOOK_STATE_DIR=~/.local/state/memory-hub-hook
# MEMORY_HOOK_DEBUG=1             # 调试失败原因
# MEMORY_HOOK_PI_CAPTURE_DELAY_MS=300000  # Pi agent_end AFK 防抖归档延时；默认 5 分钟，置 0 逐轮立即上传
# MEMORY_HOOK_PI_BOOTSTRAP_RECALL=0        # 可选：关闭 Pi 每 session 首轮 project 背景预热
# MEMORY_HOOK_PI_BOOTSTRAP_TIMEOUT_MS=120000 # 首轮预热超时；失败后当前 session 不重试
# MEMORY_HOOK_PI_BOOTSTRAP_SCORE=0         # v18 起已废弃；在线评分固定由 Hub LLM 完成，
                                           # 不再弹出玩家评分 UI，也不能用此变量绕过服务端门禁。
# 会话标题 / 低价值过滤（内网 vLLM，hook 与 upload_sessions.py 共用，默认关）：
# MEMORY_HUB_TITLE_LLM=1          # 默认 0 关闭；置 1 开启，关闭时退化为启发式标题
#                                  # （启发式低价值过滤始终生效，见「会话标题与低价值过滤判定」）
# MEMORY_HUB_TITLE_LLM_BASE_URL=http://192.168.2.76:8000/v1
# MEMORY_HUB_TITLE_LLM_MODEL=qwen3-30b
# MEMORY_HUB_TITLE_LLM_API_KEY=vllm
# MEMORY_HUB_TITLE_LLM_TIMEOUT=15
# MEMORY_HUB_PROJECT_ALIASES=sununity=unity2018,foo=bar   # project 名归并，内置默认 sununity=unity2018
#   ↑ 优先级低于 install 部署的别名 JSON（见下），仅作无安装环境的 fallback
# MEMORY_HUB_SKIP_CAPTURE=1     # extraction 子 session 专用 opt-out：变量为 "1" 且
#                               # transcript 首条 user 消息命中 extraction 签名时才跳过
#                               # （2026-08-25 起必须双重命中——变量是进程级共享状态，
#                               # auto-skill 在子 session 运行期间持有，同进程主 session
#                               # 的 hook 也会继承，仅凭变量曾误杀主 session 归档）
# MEMORY_HUB_API_KEY 回退：进程环境缺失时 memory_hook.py 自动读用户级持久化位置
# （Windows 注册表 / ~/.profile 系列），持久化之前启动的 agent 无需重启即可 401 自愈
```

Project 别名定版文件：skill 仓库 `assets/project-aliases.json` 是版本化模板（进 git），
`install_hooks.py install` 会把它部署到 `${MEMORY_HOOK_STATE_DIR:-~/.local/state/memory-hub-hook}/project-aliases.json`；
`memory_hook.py`（三端 hook capture）与 `upload_sessions.py`（批量归档）都读取这份本地副本，
优先级：内置默认 < 环境变量 < 安装的 JSON < CLI `--project-alias`。修改模板后递增 `version`
并重跑 install；`check` 会对本地副本做版本比对（outdated 时提示 rerun install）。
已知映射一览见 [projects.md](projects.md)。

标题与低价值判断按内容 SHA-256 缓存在 `MEMORY_HOOK_STATE_DIR/title-cache.jsonl`（追加式），
重跑不重复调 LLM。判定为低价值（无信息量，如只发了 hi 测模型）的会话不上传：
hook 侧 job 直接 `completed/skipped_meaningless`，批传侧计 `skipped`。
批量归档的 session 文件内嵌标题（`agent-session-archive/2` 的 `archive.title` 字段）。

User ID 解析优先级为命令行 `--user-id`、hook 输入的 `user_id`、
`MEMORY_HUB_CLIENT_USER_ID`、当前项目最近的 `.team/settings.local.json.currentMember`，最后为本机
`client-profile.json`；不再回退到
`MEMORY_HUB_AGENT_ID`。

安装器持久化身份的方式是 **shell-profile backend**：以标记块
（`# >>> memory-hub identity >>>`）把 `export MEMORY_HUB_CLIENT_USER_ID=<id>` 写入
`~/.profile`（macOS 加写 `~/.zprofile`）。注意 `install_hooks.py check` 的 identity
探测**只读进程环境变量**，不读 client-profile.json——在未 source `.profile` 的 shell
里会误报 `"source": "missing"`；确认真实身份解析结果用 `memory_hook.py status`
（输出 `identity_source` 与 `default_user_id`）。命令行或 hook 输入覆盖默认用户时，还必须同时提供该用户的显示名称和概要
（命令行用 `--display-name` / `--summary`，hook 输入用 `user_display_name` / `user_summary`），否则视为
未完成身份配置。多用户调用方应在每次 hook 输入中显式提供这三项；Hub 进程本身不得配置固定用户。

## 会话标题与低价值过滤判定

`MEMORY_HUB_TITLE_LLM` 代码默认 `0`（关闭时用启发式标题、不走 LLM 判定），置 `1` 才走内网 vLLM（要开启的机器自行设该环境变量，不改代码默认值）。注意「关闭」只关掉 LLM 判定，**启发式低价值过滤始终生效**（`heuristic_meaningful`）：当一个会话的**全部** user 消息都是噪声时判低价值不上传——`is_noise_user_text` 把以 `<`/`/` 开头的消息（pi 的 skill 注入包装、slash 命令）和纯寒暄都视为噪声，且作用于**未剥 skill 包装的原始文本**，所以一个只有 skill 调用、没有任何口语化追问的会话（典型：单次 `git-tool update & commit`）即使 LLM 关闭也会被过滤（2026-08-22 实测）。低价值判定标准含**纯执行类例行运维**（git-tool update/sync/commit、任意项目的部署/发布/构建上传（前后端 build、dist 同步、服务重启）、skill 更新提交、memory-hub check/install、批量上传归档等按既定流程执行、只有命令执行结果的会话）——这类会话不上传；但运维中含真实故障排查/bug 修复/技术决策的仍有价值（2026-08-20 用户要求加入；2026-08-29 放宽到任意项目的部署发布类，prompt 见 memory_hook.py 与 upload_sessions.py 的 llm_classify_session，两处保持同步）。

**判定材料必须是整个会话，用户目标必须保留**（2026-08-21 用户定版，曾因此误过滤）：① LLM 分类与标题的输入是整会话的非噪声用户消息（`session_user_texts`，条数 >8 时 `head_tail_sample` 首尾各 4 抽样），绝不能只喂窗口尾部——否则实质会话会被结尾的「commit」误杀（当日 job 125/149 实例）；② 归档摘要 distilled 为三段式「首个用户目标/最近用户目标/会话结果」，目标取**首个非噪声用户消息**且先剥 `<skill>...</skill>` 注入包装（`strip_skill_wrapper`——pi 用户消息常是整份 SKILL.md + 末尾一句真实问题，不剥会把目标污染成模板文本），空目标兜底链 first→last→title；③ live hook 上传时经 `load_session_texts` 从 spool full 包重取全量事件提取文本，不依赖 job 行的尾部快照列。

## 独立应用命令

```bash
APP=/Users/sun/Documents/ObsidianVault/.claude/skills/memory-hub/scripts/memory_hook.py
/usr/bin/python3 "$APP" configure --user-id user-123 --display-name 'Jane' --summary '偏好简洁、技术性的回答'
/usr/bin/python3 "$APP" search '项目的历史决策和未完成事项' --limit 10
/usr/bin/python3 "$APP" search '用户偏好' --user-id user-456 --display-name 'Alex' --summary '用户概要' --limit 10
/usr/bin/python3 "$APP" status
/usr/bin/python3 "$APP" flush --limit 100
```

检索以按需发起为主：Pi 额外在每个 session 首轮自动预热一次当前 project 的概况、架构、历史决策、
进展、待办与约定，后续深挖仍用 `memory_search`；Claude/Codex 用上面的 `search` CLI 按需检索。
行为契约（何时检索、query 怎么写、scope 怎么切）写在 vault `AGENTS.md`「Memory Hub 按需检索」。
Stop/agent_end 将当前最新完整快照写入
本地 spool 并立即尝试上传；SessionEnd/session_shutdown 再上传最终幂等快照。服务器不可用时保留 queued job，
下一次 capture 或手工 flush 自动补传。

Esc 中断保护（2026-08 起）：capture 由 **Stop** 事件触发且 transcript 尾部最新一条 user/assistant 消息是
中断标记（`[Request interrupted by user…]`）时直接跳过，不入队不上传——避免把被用户放弃的半成品轮次
立刻归档。SessionEnd/session_shutdown 触发的最终快照不受影响、始终归档；Esc 后继续对话，下一个正常
Stop 会照常上传。pi 扩展 capture 固定传 `hook_event_name=SessionEnd`，不受此分支影响。
重复事件安全：以
`{source_agent}:{session_id}` 作为归档 ID，对确定性快照计算 SHA-256；相同内容命中本地与远端
幂等，不重复创建，内容变化时创建同一 session 的下一不可变版本。

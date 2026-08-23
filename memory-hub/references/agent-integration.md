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

快照格式为 `agent-session/2`，只保存最近 10 条 user/assistant 消息。工具事件、无法解析事件和
Markdown fenced code 不上传；Markdown 标题、列表、链接和解释正文保留。Spool 每个 job 固化
`user_id`，所以稍后 flush 时不会因进程环境变化而补传到错误用户。

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

**install 建议指定本机 project（`--project`）**：它写入 state dir 的 `project-aliases.local.json`
（机器级字典映射 `{"aliases":{"*":"<id>"}}`，不进 git、不随 skill 模板扩散），本机所有
capture/search/批量归档默认都落该 project，与其他机器的项目完全隔离。映射里 `"*"` 是 catch-all，
具体条目（如 `{"memory-hub":"memory-hub"}`）优先于 `*`。未提供时：交互终端会询问（默认建议主机名）；
非交互只输出建议、不落盘。未设置本机映射时才退回按 cwd 派生（`assets/project-aliases.json` 部署的别名）。

**install 必须指定用户身份**：`--user-id` 必填（或已预设 `MEMORY_HUB_CLIENT_USER_ID`）。
安装器会把它**持久化到用户级环境变量**：
Windows 写入注册表 `HKCU\Environment` 并广播 `WM_SETTINGCHANGE`；POSIX 写入 `~/.profile`
标记块（macOS 同时写 `~/.zprofile`）。之后本机所有新启动的 agent / hook 进程都默认从环境变量取身份，
优先级高于 `.team/settings.local.json` 与 `client-profile.json`；已在运行的进程需重启才能看到。
环境身份只携带 user_id；display_name / summary 仅来自本机 `client-profile.json`（`configure` 写入）。

安装成功必须同时满足：

- Claude Code/Codex 各有且仅有 2 个 Memory Hub handlers：Stop、SessionEnd（v4 起移除了
  SessionStart/UserPromptSubmit 的自动 recall，检索改为 agent 按需发起）。
- Stop 每轮直接执行 `capture`，不得带 `--flush-limit 0`；SessionEnd 再提交最终幂等快照。
- Codex 必须通过 app-server `hooks/list` 确认 2 个 handlers 均为 `trusted`，且没有 Memory Hub 相关 warning/error。
- Pi 全局扩展必须包含 `before_agent_start`、`agent_end`、`session_shutdown`；`before_agent_start` 只负责
  取消挂起归档（不再 recall），`agent_end` 走 AFK 防抖上传（默认空闲 5 分钟才归档，新 prompt 取消重计），`session_shutdown` 立即归档。
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
  warning 不影响总结果。
- **Pi 扩展 EXTENSION_VERSION**：已安装副本的版本号与模板
（`assets/pi-memory-hub.ts`）不一致时报 `extension version X is outdated (managed Y); rerun install`，
重新执行 install 即可重新发布。修改模板后必须递增模板里的版本号，否则 check 无法感知升级。

## Pi 扩展全链路留痕

Pi 扩展（v2 起）把每次与 Memory Hub 的交互追加为 JSONL，写到
`${MEMORY_HOOK_STATE_DIR:-~/.local/state/memory-hub-hook}/pi-trace.jsonl`，供离线分析检索质量：

| kind | 时机 | 关键字段 |
|---|---|---|
| `session_start` | 会话开始 | session_id、cwd |
| `search` | memory_search 工具调用 | query、limit、exit_code、duration_ms、result（结果全文） |
| `capture_schedule` | agent_end 排程 AFK 延时归档 | trigger、delay_ms |
| `capture_cancel` | 新 prompt / reschedule / shutdown 取消挂起归档 | reason、trigger |
| `capture` | 空闲延时（agent_end_idle）/ session_shutdown 归档 | trigger、exit_code、duration_ms、skipped（no_transcript/reentrant） |

Pi 扩展 v4 起 agent_end 不再逐轮立即上传：等会话空闲
`MEMORY_HOOK_PI_CAPTURE_DELAY_MS` 毫秒（默认 5 分钟，置 0 恢复逐轮立即上传）后才 capture；
计时器 unref，不拖住进程退出，提前退出由 session_shutdown 立即归档兜底。

单字段超 20k 字符截断；写日志失败不阻断 agent。Claude/Codex 端的留痕在 spool
（`memory_hook.py status` 可查 job 状态），不在此文件。

安装器仅替换命令路径包含 `memory-hub/scripts/memory_hook.py` 的 handlers，保留其他 Hook，并在修改配置前生成
`*.memory-hub.bak` 备份。运行中的 Agent 可能缓存配置；完成后提示重启对应 Agent 或执行其 reload 命令。

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
#                                  # 可手工写进 profile 标记块，或 install 时传 --api-key；
#                                  # install 会自动沿用进程环境/profile 里已有的 key（升级重装不丢）；
#                                  # install_hooks.py check 的 auth 项会校验它是否设置且被服务端接受
# MEMORY_HOOK_TIMEOUT_SECONDS=8
# MEMORY_HOOK_STATE_DIR=~/.local/state/memory-hub-hook
# MEMORY_HOOK_DEBUG=1             # 调试失败原因
# MEMORY_HOOK_PI_CAPTURE_DELAY_MS=300000  # Pi agent_end AFK 防抖归档延时；默认 5 分钟，置 0 逐轮立即上传
# 会话标题 / 低价值过滤（内网 vLLM，hook 与 upload_sessions.py 共用，默认关）：
# MEMORY_HUB_TITLE_LLM=1          # 默认 0 关闭；置 1 开启，关闭时退化为启发式标题且不做低价值过滤
# MEMORY_HUB_TITLE_LLM_BASE_URL=http://192.168.2.76:8000/v1
# MEMORY_HUB_TITLE_LLM_MODEL=qwen3-30b
# MEMORY_HUB_TITLE_LLM_API_KEY=vllm
# MEMORY_HUB_TITLE_LLM_TIMEOUT=15
# MEMORY_HUB_PROJECT_ALIASES=sununity=unity2018,foo=bar   # project 名归并，内置默认 sununity=unity2018
#   ↑ 优先级低于 install 部署的别名 JSON（见下），仅作无安装环境的 fallback
# MEMORY_HUB_SKIP_CAPTURE=1     # capture 完全跳过（不入队不发请求）；auto-skill extraction
#                               # 子 session 等明确不归档的场景由扩展自行设置，见 memory_hook.py
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

## 独立应用命令

```bash
APP=/Users/sun/Documents/ObsidianVault/.claude/skills/memory-hub/scripts/memory_hook.py
/usr/bin/python3 "$APP" configure --user-id user-123 --display-name 'Jane' --summary '偏好简洁、技术性的回答'
/usr/bin/python3 "$APP" search '项目的历史决策和未完成事项' --limit 10
/usr/bin/python3 "$APP" search '用户偏好' --user-id user-456 --display-name 'Alex' --summary '用户概要' --limit 10
/usr/bin/python3 "$APP" status
/usr/bin/python3 "$APP" flush --limit 100
```

检索全部由 agent 按需发起（2026-08-20 起）：Pi 用 `memory_search` 工具，Claude/Codex 用上面的
`search` CLI；行为契约（何时检索、query 怎么写、scope 怎么切）写在 vault `AGENTS.md`「Memory Hub 按需检索」。
hooks 不再在任何事件自动召回注入。Stop/agent_end 将当前最新完整快照写入
本地 spool 并立即尝试上传；SessionEnd/session_shutdown 再上传最终幂等快照。服务器不可用时保留 queued job，
下一次 capture 或手工 flush 自动补传。

Esc 中断保护（2026-08 起）：capture 由 **Stop** 事件触发且 transcript 尾部最新一条 user/assistant 消息是
中断标记（`[Request interrupted by user…]`）时直接跳过，不入队不上传——避免把被用户放弃的半成品轮次
立刻归档。SessionEnd/session_shutdown 触发的最终快照不受影响、始终归档；Esc 后继续对话，下一个正常
Stop 会照常上传。pi 扩展 capture 固定传 `hook_event_name=SessionEnd`，不受此分支影响。
重复事件安全：以
`{source_agent}:{session_id}` 作为归档 ID，对确定性快照计算 SHA-256；相同内容命中本地与远端
幂等，不重复创建，内容变化时创建同一 session 的下一不可变版本。

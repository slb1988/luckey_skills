# Agent 自动记忆集成（Hooks）

Claude Code / Codex / Pi 三端共用独立应用 `scripts/memory_hook.py`。它不 import、调用或依赖
Memory Hub 项目及其 venv，只使用 Python 标准库访问远端 HTTP API。

每次 capture 先生成确定性 gzip 快照并写入本机 SQLite spool，然后才访问服务器。服务器不可用时
job 永久保留为 `queued`；后续 Stop、SessionEnd、agent_end 或手工 flush 会自动补传。因此 hook
仍可 fail-open，不会阻止 Agent，也不会因短期网络故障丢失 session。

快照格式为 `agent-session/2`，只保存最近 10 条 user/assistant 消息。工具事件、无法解析事件和
Markdown fenced code 不上传；Markdown 标题、列表、链接和解释正文保留。Spool 每个 job 固化
`user_id`，所以稍后 flush 时不会因进程环境变化而补传到错误用户。

## 首次用户身份配置

Hook 客户端没有内置固定用户，也不得用 `agent_id` 代替用户身份。首次 SessionStart 或
UserPromptSubmit hook 若尚无完整配置，会停止检索并向 Agent 注入设置提醒；Agent 必须向用户确认以下
三项信息，不得自行猜测：

- 长期稳定的内部 `user_id`（仅字母、数字、`.`、`_`、`:`、`-`，最长 128 字符）；
- 显示名称；
- 简短概要，例如身份、偏好或长期目标，不得包含密码、API Key 等秘密。

若环境变量未指定用户，客户端会从 hook 工作目录向上查找最近的 `.team/settings.local.json`，读取字符串
字段 `currentMember` 作为候选 `user_id`，优先于本机 profile。提醒和配置命令会自动带上该候选值；仍须
让用户确认，并补充显示名称与概要。文件缺失、JSON 无效或 `currentMember` 不是合法字符串时，安全回退
到本机 profile 或未配置状态。

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

## install 关键字

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
- 安装器返回的各 agent `ok=true`。服务健康检查失败可保留 durable spool，但必须明确报告"已安装、尚未端到端验证"，不得宣称上传链路正常。

安装或升级后执行只读复检：

```bash
/usr/bin/python3 "$SKILL_DIR/scripts/install_hooks.py" check --agents auto
```

安装器仅替换命令路径包含 `memory-hub/scripts/memory_hook.py` 的 handlers，保留其他 Hook，并在修改配置前生成
`*.memory-hub.bak` 备份。运行中的 Agent 可能缓存配置；完成后提示重启对应 Agent 或执行其 reload 命令。

## 环境变量

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
`MEMORY_HUB_CLIENT_USER_ID`、当前项目最近的 `.team/settings.local.json.currentMember`，最后为本机
`client-profile.json`；不再回退到
`MEMORY_HUB_AGENT_ID`。命令行或 hook 输入覆盖默认用户时，还必须同时提供该用户的显示名称和概要
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

全局 hooks 在 SessionStart/UserPromptSubmit/before_agent_start 召回。Stop/agent_end 将当前最新完整快照写入
本地 spool 并立即尝试上传；SessionEnd/session_shutdown 再上传最终幂等快照。服务器不可用时保留 queued job，
下一次 capture 或手工 flush 自动补传。
重复事件安全：以
`{source_agent}:{session_id}` 作为归档 ID，对确定性快照计算 SHA-256；相同内容命中本地与远端
幂等，不重复创建，内容变化时创建同一 session 的下一不可变版本。

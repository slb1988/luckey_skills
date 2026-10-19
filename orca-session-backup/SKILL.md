---
name: orca-session-backup
description: "把 Orca 里打开的 agent 终端会话（Pi / Claude Code）备份成一份可读的 .md「待 Review 清单」，每条带首问/末问/最后回复/产出文件和可复制的恢复命令，之后可放心关闭终端，按需单条或一键全部恢复到 Orca 新标签。当用户提到备份 Orca 会话、收藏/存档 agent 终端、终端太多想关又怕丢、会话书签、恢复之前关掉的 Orca 会话、orca session backup/restore 时触发。即使用户只说「把 angelscript-merge 的会话存一下」「这些 agent 我还没看完先收起来」「把上次备份的会话恢复回来」也应触发。"
---

# Orca 会话备份 / 恢复

场景：Orca 里堆了一堆 agent 终端，大多已经跑完，但产出还没 review / 没消化完，不敢关。
备份 = 生成一份 .md「待 Review 清单」；之后关掉终端也不会漏，需要时按清单恢复原会话（带完整上下文）。

脚本：`scripts/orca_session_backup.py`（只依赖 Python 3.10+ 和 `orca` CLI）。

## 备份

```bash
python .claude/skills/orca-session-backup/scripts/orca_session_backup.py backup --worktree angelscript-merge
python .claude/skills/orca-session-backup/scripts/orca_session_backup.py backup --all
```

- `--worktree` 接受裸目录名（`angelscript-merge`）、绝对路径或 Orca selector；不传 = 当前 active 工作区。
  不要用 `name:<目录名>`——Orca 的 `name:` 匹配 displayName，git 仓库通常是分支名。
- `--out DIR` 输出目录，默认 `~/.orca/session-backups/`，文件名 `orca-sessions-<scope>-<YYYYMMDD-HHMM>.md`。
- 备份是**只读**的：不关闭、不修改任何终端和会话文件。

把生成的文件路径告诉用户；不要替用户执行文末的「关闭终端」命令，除非用户明确要求。

## 恢复

```bash
python .claude/skills/orca-session-backup/scripts/orca_session_backup.py restore <备份.md> [--only 1,3] [--dry-run] [--force]
```

- 每条会话在原工作区新开一个 Orca 标签，执行 `pi --session <id>` / `claude --resume <id>`。
- 已经在某个打开终端里的会话自动跳过（`--force` 强制再开）。
- 用户也可以直接从 .md 复制单条的「手动」或「Orca 新标签」命令。
- 条目的机器可读信息在每条末尾的 `<!-- orca-session-backup {...} -->` 注释里；编号即清单编号。

## 会话是怎么认出来的

Orca 不记录终端里 agent 的会话 ID，脚本按证据把会话文件分配给终端（每个会话只归属一个终端，总分高者优先）：

| 证据 | 分 | 说明 |
|---|---|---|
| 终端标题 = 会话标题 | 5 | Claude 把 ai-title / custom-title 写成终端标题 |
| 启动时间吻合（±20s） | 3 | Orca terminal-history `meta.json.startedAt` vs Pi 会话头 / Claude SessionStart 时间 |
| 终端内容命中 | 每条 1 | 会话里的用户提问（去空白后前 24 字、≥10 字）出现在终端历史中 |

- 只有内容命中时要求同类 agent，且 ≥2 条或会话在终端打开后仍有活动——否则 `continue`、`git commit`、共享路径会串台。
- Orca 的 `agentIdentity` 不可靠（pi 标签里可能跑着 claude），所以两种 agent 的会话都参与匹配，恢复命令按会话实际类型生成。
- Orca 重启时会在新 PTY 里 resume Claude 会话，此时会话最后活动早于终端启动，所以不按终端启动时间过滤会话（只看最近 30 天）。
- agent 在同一终端里被重启过时，可能出现多个会话归同一终端，较早的会标「同一终端内较早的会话」；匹配不上的近期会话列在
  「同工作区近期、但不在任何打开终端里的会话」，不进一键恢复。

数据来源：`orca terminal list --json`、`%APPDATA%/orca/terminal-history/<urlencoded ptyId>/{meta.json,output.log,checkpoint.json}`、
`~/.pi/agent/sessions/--<cwd>--/*.jsonl`、`~/.claude/projects/<cwd 非字母数字→->/*.jsonl`。

## 限制

- 支持 Pi 和 Claude Code；Codex 和普通 shell 终端列在「未备份的终端」里。
- 手动恢复命令按当前系统生成（Windows 用 `cd /d`）。
- 「最后活动」取会话文件里的最后时间戳，不是 Orca 的 lastOutputAt（Orca 重启重绘也会刷新后者）。

---
name: pi-agent
description: Pi agent（pi，@earendil-works 的 coding agent）使用与排障指南。记录 pi 使用过程中的各种小问题：扩展加载冲突、插件卸载、配置位置、npm 包管理、启动报错等。当用户提到 pi 报错、pi 扩展冲突、pi 插件卸载、pi-subagents、Tool conflicts、Failed to load extension、pi 配置、pi 启动失败，或排查 pi 的扩展/配置/npm 包问题时触发。即使用户只说"pi 又报错了""pi 启动不了""pi 扩展冲突"也应触发。
---

# Pi Agent 使用排障指南

记录使用 `pi`（Pi coding agent）过程中遇到的小问题与解法。本技能只记录**使用与排障**；扩展**开发**（写扩展、注册 provider、hook API）见项目内 `.pi/extensions/SKILL.md`（pi-extensions 技能）。

## 关键路径速查

| 项目 | 路径 |
|------|------|
| 全局配置 | `~/.pi/agent/settings.json` |
| 全局扩展（单文件 .ts） | `~/.pi/agent/extensions/` |
| 全局 npm 包 | `~/.pi/agent/npm/node_modules/` |
| 系统全局 npm 包 | `/opt/homebrew/lib/node_modules/` |
| 调试日志 | `~/.pi/agent/pi-debug.log` |
| 会话历史 | `~/.pi/agent/sessions/` |
| 项目配置 | `<project>/.pi/settings.json` |
| 项目扩展 | `<project>/.pi/extensions/` |

## 参考文档

| 主题 | 文件 |
|------|------|
| 已知问题与解法（扩展冲突、插件卸载、配置与扩展加载源） | [references/troubleshooting.md](references/troubleshooting.md) |

<memory category="troubleshooting">
`ws:` 路由（.pi/extensions/workspace-routing → agentctl.py）解析需要两份数据同时就位：共享 catalog `.claude/agent-control/workspaces.json`（只有名字，可入库）+ 本机注册表 `%LOCALAPPDATA%\agent-control\workspaces.json`（机器路径绑定，不共享）。新机器报 `unknown workspace` 或 `has no local binding or remote route` 时先查本机注册表是否存在——没跑过 add 流程时它根本不存在。
</memory>

## 快速排查

- 扩展加载失败，先 `pi -ne`（无扩展启动）确认是扩展问题还是 pi 本身问题。
- 报错细节看 `~/.pi/agent/pi-debug.log`。
- 扩展冲突 / 插件卸载 / 配置问题 → 读 [references/troubleshooting.md](references/troubleshooting.md)。
- auto-server 上更新 `.pi/skills` 必须先 `cd /home/dev/.pi/skills`：更新脚本按 cwd 定位仓库根，在 `/home/dev` 下运行会静默失败（exit 128，无输出）。
- `ws:<name>` 报 unknown workspace / no local binding → 见 [references/troubleshooting.md](references/troubleshooting.md) 第 6 节。
- `workflow` 编排的 agent() 全部秒回 null（subagent 未启动）→ 见 [references/troubleshooting.md](references/troubleshooting.md) 第 8 节（tier 模型 `undefined.create`）。

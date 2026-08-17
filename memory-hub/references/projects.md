# Memory Hub 已知 Project 一览

Memory Hub 自 2026-08 版本起提供 `GET /v1/projects` 列出已知 project（含 memory/session 计数与最近活动时间）；
旧版本无此 API 时，以本表为准手动切换。本表同时记录每个 project 的用途，**发现新 project 时追加**。

检索时的规则：

1. 搜索前确定目标记忆最可能属于哪个 project，用它作为 `X-Project-Id` / `project_id`。
2. 搜到空结果时，**先换下表中的其他 project 重试**，不要立刻断定"没有这条记忆"。
3. 不要因为 Hub 搜不到就绕过 Hub 直查 Graphiti——scope 隔离是设计行为，直查会得出错误结论。

## Project 表

| project_id | 内容 / 用途 | 备注 |
|---|---|---|
| `unity2019` | Unity 2019.4 源码项目：Apple Silicon Mac 构建（MacEditor/MacPlayer、Rosetta 2、nxxbuild.sh）、授权排查（SUNSET_LAUNCHER=1 硬编码、独立 LicensingClient 进程），文档见该项目 `docs/unity2019-license-crack-and-hub-disable.md`、`docs/unity2019-troubleshooting-guide.md` | 2026-08 确认有 indexed 记忆 |
| `ObsidianVault` | 本 Obsidian vault 仓库相关的 agent 记忆 | Pi 端默认使用 |
| `agent-history` | session 归档（`MEMORY_HUB_ARCHIVE_PROJECT_ID` 默认值） | 归档用 |
| `ProjectLungfish` | SKILL.md 示例中出现的 project，实际内容待确认 | 待确认 |

## scope 速查

| scope_type | group_id | 典型用途 |
|---|---|---|
| global | `global` | 跨项目通用事实（写需 trusted_service/admin） |
| user | `user:{user_id}` | 用户偏好、身份 |
| project | `project:{project_id}` | 单项目决策、构建/排障记录 |
| agent | `agent:{agent_id}` | 单个 agent 的私有记忆 |

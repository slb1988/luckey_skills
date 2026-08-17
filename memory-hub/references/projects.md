# Memory Hub 已知 Project 一览

Memory Hub 提供 `GET /v1/projects` 列出已知 project（含 memory/session 计数与最近活动时间），检索前优先调用它；
本表记录每个 project 的用途，**发现新 project 时追加**。

检索时的规则：

1. 搜索前确定目标记忆最可能属于哪个 project，用它作为 `X-Project-Id` / `project_id`。
2. 搜到空结果时，**先换下表中的其他 project 重试**，不要立刻断定"没有这条记忆"。
3. 不要因为 Hub 搜不到就绕过 Hub 直查 Graphiti——scope 隔离是设计行为，直查会得出错误结论。

## Project 表

| project_id | 内容 / 用途 | 备注 |
|---|---|---|
| `agent-history` | Claude Code 的 session 归档主库（`MEMORY_HUB_ARCHIVE_PROJECT_ID` 默认归档目标） | 最大归档 project（数百条 memory/session），2026-08 活跃 |
| `claude-history` | Claude Code 会话历史提炼记忆 | 2026-08 活跃 |
| `unity2019` | Unity 2019.4 源码项目：Apple Silicon Mac 构建（MacEditor/MacPlayer、Rosetta 2、nxxbuild.sh）、授权排查（SUNSET_LAUNCHER=1 硬编码、独立 LicensingClient 进程），文档见该项目 `docs/unity2019-license-crack-and-hub-disable.md`、`docs/unity2019-troubleshooting-guide.md` | 8 条 indexed 记忆 |
| `home` | 家庭/个人环境相关记录 | 少量记忆，用途待补充 |

## scope 速查

| scope_type | group_id | 典型用途 |
|---|---|---|
| global | `global` | 跨项目通用事实（写需 trusted_service/admin） |
| user | `user:{user_id}` | 用户偏好、身份 |
| project | `project:{project_id}` | 单项目决策、构建/排障记录 |
| agent | `agent:{agent_id}` | 单个 agent 的私有记忆 |

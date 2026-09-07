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
| `maindev` | 主游戏项目 `D:\MainDev`（UE 引擎+客户端）session 归档 | 最大 project（1200+ sessions，pi + claude），2026-08 活跃 |
| `unity2018` | Unity 2018 源码项目（E:\\sununity）历史 session 归档：1094 个 Pi session + 1 个 Claude session（agent 分别为 `pi` / `claude-code`），2026-08 由 `upload_sessions.py` 手动批量归档 | 755 sessions / 755 memories |
| `agent-history` | Claude Code 的 session 归档主库 + 杂项兜底（Downloads、`C:\Users\admin`、`E:\`、中文目录等派生不出合法名字的 cwd） | 430+ sessions，2026-08 活跃 |
| `obsidianvault` | Obsidian 知识库仓库 | 136 sessions（pi + claude），含别名归并（见下节） |
| `xiaoyingtao` | 小樱桃（机主女儿）的 chat-hub 微信会话 + 成长档案（`manual:xiaoyingtao:profile`） | 2026-09-06 按人分池定版：chat-hub 单一非机主说话人会话自动归其 profile_id 同名 project（见 agent-integration.md「chat-hub 会话按人归 project」） |
| `admin_sun_depot_7184` | DevOps 主仓库 `D:\work\admin_sun_depot_7184` | 54 sessions，含 pyAutomation frontend/backend 别名归并 |
| `claude-history` | Mac 端 Claude Code 会话历史提炼记忆 | claude-code-mac，2026-08 活跃 |
| `memory-hub` | memory-hub 项目自身 | pi 端为主 |
| `mini-as` | 教学脚本引擎 `D:\Github\mini-as` | 2026-08 手动归档新建 |
| `sun-p4` | QNAP P4 depot（`E:\My\pc_qnap_depot_9516`）工具区：claude-code 源码分析/二开（去遥测、/buddy、打包 exe、TUI 渲染、SKILL.md 整理） | 2026-08 codex 归档新建，15 sessions |
| `admin` | `C:\Users\admin` cwd 派生 + `embedding` merge 目标 | merged_sources: embedding |
| `devops` | 旧 DevOps 仓库 `D:\SunLaibing_Depot_8603\DevOps`（PreCheckin / SKILL.index） | 2026-08 手动归档新建 |
| `evavm` | EvaVM `D:\Github\EvaVM` | |
| `unrealengine` | Epic 上游 UnrealEngine `E:\My\UnrealEngine`（ue6-main） | 2026-08 手动归档新建，含 Engine\\Source 别名归并 |
| `sub2api` | `D:\Github\sub2api` | 2026-08 手动归档新建 |
| `codegraph` | `D:\MainDev\Tools\codegraph` | |
| `unity2019` | Unity 2019.4 源码项目：Apple Silicon Mac 构建（MacEditor/MacPlayer、Rosetta 2、nxxbuild.sh）、授权排查（SUNSET_LAUNCHER=1 硬编码、独立 LicensingClient 进程），文档见该项目 `docs/unity2019-license-crack-and-hub-disable.md`、`docs/unity2019-troubleshooting-guide.md` | claude-code-mac，8 条 indexed 记忆 |
| `home` | 家庭/个人环境相关记录 | claude-code-mac，少量记忆 |
| `speech_to_text` / `examples` / `luckey_skills` / `helloworld` | pi 端小型/试验项目 | 各 1-2 sessions |

## Project 派生的 worktree 归一规则（2026-09-07 起）

`project_id_for_cwd` 在查别名表**之前**先做两级 worktree 归一（`memory_hook.py` 与
`upload_sessions.py` 各持一份相同实现）：

1. **Orca 工作区路径段规则**：cwd 含 `orca/workspaces/<repo>/` 段 → 直接派生 `<repo>`。
   Orca 给编排任务开的 worktree 目录名是一次性任务名（如 `memory-hub-attribution-project`），
   不归一时每个 worktree 都会生成独立 project / graph group（实体碎片化，审核面板存在性
   标注随之失真）。
2. **git linked worktree 规则**：`git rev-parse --git-dir --git-common-dir` 两者不同 →
   linked worktree，派生名取 common-dir 父目录名（主检出目录名）。主检出（含仓库子目录）、
   非 git 目录、cwd 不存在、git 异常全部 fail-open 回退到 cwd 末级目录名。

归一后才查别名表，因此别名仍可覆盖 worktree 归一结果。排查「session 归错了 project」时
先看该 cwd 是否命中这两条规则。

## Project 别名定版（assets/project-aliases.json）

派生名（cwd 末级目录小写）→ 目标 project 的映射**以 skill 仓库
`assets/project-aliases.json` 为准**（版本化模板，带 `version` 字段）。
`install_hooks.py install` 会把它部署到 `${MEMORY_HOOK_STATE_DIR:-~/.local/state/memory-hub-hook}/project-aliases.json`，
三端 hook capture 与 `upload_sessions.py` 批量归档共用；`check` 对本地副本做版本比对，
修改模板后递增 `version` 并重跑 install。优先级：内置默认 < `MEMORY_HUB_PROJECT_ALIASES`
环境变量 < 安装的 JSON < CLI `--project-alias`。

> **本机级映射优先**：state dir 的 `project-aliases.local.json`（`install --project <id>` 写入
> `{"aliases":{"*":"<id>"}}`，机器级、不进 git）设置后覆盖共享模板，本机 capture/search/批量归档
> 默认按它归 project（`"*"` catch-all = 全部）；未设置时才按本表派生。

2026-08 定版的完整映射（Windows 本机 Claude Code + Codex 大批量归档）：

| 派生名 | 实际 cwd | 目标 project |
|---|---|---|
| source | `E:\My\UnrealEngine\Engine\...\Source` | `unrealengine` |
| riderlink | `D:\MainDev\Main\Plugins\Marketplace\RiderLink` | `maindev` |
| frontend / backend | `...\admin_sun_depot_7184\pyAutomation\{frontend,backend}` | `admin_sun_depot_7184` |
| notes | `ObsidianVault\luckey\07_assets\notes` | `obsidianvault` |
| feishu_ragflow_sync | `ObsidianVault\.claude\scripts\feishu_ragflow_sync` | `obsidianvault` |
| embedding | `...\300-Learning\LLM\Embedding` | `admin`（hub 侧已 merge） |
| downloads / admin | `C:\Users\admin\Downloads`、`C:\Users\admin` | `agent-history` |
| angelscript / mem0 / hindsight | 一次性仓库调研（内容少或与仓库无关） | `agent-history` |
| sununity | `E:\sununity` | `unity2018`（脚本内置别名） |
| claude-code / claude-code-best | `...\pc_qnap_depot_9516\001-Common\Tools\claude-code[-best]`、`D:\Github\claude-code` | `sun-p4` |
| pc_qnap_depot_9516 | `E:\My\pc_qnap_depot_9516`（depot 根，内容同样是 claude-code 分析） | `sun-p4` |
| unrealengine-angelscript | `D:\UnrealEngine-Angelscript` | `maindev` |
| system32 / a / subapi / n-r / da-mo / rag / zep-graphs-1-entities-facts-episodes | `C:\Windows\System32`、`C:\Users\admin\Documents\Codex\*` 一次性 scratch | `agent-history` |

归档命令定版：`--hook-namespace --agent-id claude`（与本机 hook 三段式 session id
同轨，resume 后 hook 接续追加版本）；`E--sununity` 那条两段式旧归档用
`--existing-map` + `--skip-existing` 跳过，避免双轨重复。
2026-08 Codex 归档（238 sessions）同轨执行：`--hook-namespace`（agent-id 默认 codex），
别名全部由安装的 JSON 提供，无需 CLI 传入；LLM 判定 35 个低价值会话未上传。

## scope 速查

| scope_type | group_id | 典型用途 |
|---|---|---|
| global | `global` | 跨项目通用事实（写需 trusted_service/admin） |
| user | `user:{user_id}` | 用户偏好、身份 |
| project | `project:{project_id}` | 单项目决策、构建/排障记录 |
| agent | `agent:{agent_id}` | 单个 agent 的私有记忆 |

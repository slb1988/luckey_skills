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

<memory category="code-locations">
a2a-mentions 扩展的平台 token 存在全局文件 `~/.pi/agent/a2a-mentions.json`（格式 `{baseUrl, token, expiresAt?}`），不是按项目存的——ObsidianVault 与 MainDev 共用一份，写一次两边生效。`loadTokenStore` 两条非显然语义：(1) 只在 `expiresAt` 为 number 时判过期，**省略该字段即永久 token**（平台已支持签发永久 token，用户规则：本地一律按永久存，不写 expiresAt）；(2) 故意不校验 baseUrl 匹配（两个项目默认 baseUrl 不同：10.77.77.4:5000 vs 192.168.2.13:5000，严格匹配会互相踢登录）；同一 token 两个入口都认。改 token 后当前 session 需 `/a2a-reload` 或重开才生效；真过期会暴露为 HTTP 401 / status.code=101。
</memory>

<memory category="troubleshooting">
skill-gateway「skill 未命中/未匹配到」且耗时显示 (0.0s)：先查项目根有没有 `SKILL.index.json`。`serverSelect()` 第一步就是读 `<项目根>/SKILL.index.json`，文件缺失时直接 return null，**根本不发网络请求**，所以耗时恒为 0。判据看审计日志 `.pi/extensions/skill-gateway/.audit/skill-gateway.jsonl` 里是否每轮都是 `index_missing` 事件。索引由生成器产出（MainDev 用 `.claude/build-index-unreal.js` + `skill_index_gen.bat`，v3.0.0 格式；ObsidianVault 长期没有生成器，gateway 从启用起一直空转）。另外两项目的 `.pi/extensions/` 会漂移：同名扩展（skill-gateway、dynamic-workflows、auto-skill、a2a-mentions、plan-mode、team-profile）ObsidianVault 曾落后 MainDev 一个多月；从 MainDev 覆盖同步时**保留 ObsidianVault 独有的 `workspace-routing`**。
</memory>

<memory category="common-patterns">
把 npm 发布的 pi 扩展（或 narumiruna/pi-extensions monorepo 里的包）vendor 进项目 `.pi/extensions/`：构建后只需拷 `dist/ + package.json`——pi loader 靠子目录 package.json 里的 `pi.extensions` 字段（如 `["./dist/index.ts"]`）自动发现并加载。在扩展目录内装依赖必须 `npm install --omit=dev --legacy-peer-deps`：`@earendil-works/pi-ai|pi-tui|pi-coding-agent|pi-agent-core` 由 pi 运行时 virtualModules/jiti alias 提供，**不能落进扩展自己的 node_modules**（不加 --legacy-peer-deps 时 npm 会把 peerDeps 自动装进扩展目录，多余且可能冲突）。加载失败信号是 `Failed to load extension "<path>"` diagnostic；冒烟：`pi -p "reply with just: ok" --no-session` 无该错误即成功（TUI-only 命令如 /btw 需进 TUI 实测）。完整迁移 runbook 见 `.team/sunlaibing/reference_pi-extensions-migration.md`。
</memory>

<memory category="common-patterns">
pi-btw 扩展同步基线：从 narumiruna/pi-extensions 的 commit `0eb67035f39790033c42be200999847cf620ce0d` 迁移 + 二次修改而来；上游本地 clone 在 `/Users/sun/Documents/GitHub/pi-extensions`。**项目内入口固定为源码优先**：`package.json` 的 `pi.extensions` 指向 `./src/index.ts`（`src/` 下 10 个原始源文件是本地权威源码，pi loader 直接加载 TS 源码），`dist/index.ts` 只作上游构建产物保留、必须保持未修改——本地修复一律改 `src/`（如 UI 修复在 `src/fullscreen-ui.ts`），禁止把修复落在 dist bundle。**同步官方更新的流程**：上游 clone `git fetch` → `git diff 0eb67035..<新基线> -- packages/pi-btw/` 找出官方 diff → 按迁移 runbook 落地（保留本地二次修改）→ **修改前必须先给用户 review diff**（硬性规则）→ 同步完更新基线 commit 记录。
</memory>

<memory category="troubleshooting">
`SessionManager.listAll()` 会**递归扫描** `~/.pi/agent/sessions/` 的所有子目录，凡是 `.jsonl` 结尾的文件都会进会话列表——所以批量清理会话时不能把裸 .jsonl 挪进 `backup/` 之类子目录（会以伪项目 `backup` 重新污染列表）。既定约定：打包成 `.tar.gz` 存 `~/.pi/agent/sessions/backup/`，先校验归档再删原件，并在该目录 `README.md` 的 Records 节登记。auto-skill extraction 子会话曾是主要污染源（累计数千个），2026-08 已修根因：extraction 子会话改用 `SessionManager.inMemory()`，不再落盘；之后再看到 extraction 会话说明扩展是旧版，从 MainDev 同步 auto-skill 即可。
</memory>

## 快速排查

- 扩展加载失败，先 `pi -ne`（无扩展启动）确认是扩展问题还是 pi 本身问题。
- 报错细节看 `~/.pi/agent/pi-debug.log`。
- 扩展冲突 / 插件卸载 / 配置问题 → 读 [references/troubleshooting.md](references/troubleshooting.md)。
- auto-server 上更新 `.pi/skills` 必须先 `cd /home/dev/.pi/skills`：更新脚本按 cwd 定位仓库根，在 `/home/dev` 下运行会静默失败（exit 128，无输出）。
- `ws:<name>` 报 unknown workspace / no local binding → 见 [references/troubleshooting.md](references/troubleshooting.md) 第 6 节。
- `workflow` 编排的 agent() 全部秒回 null（subagent 未启动）→ 见 [references/troubleshooting.md](references/troubleshooting.md) 第 8 节（tier 模型 `undefined.create`）。

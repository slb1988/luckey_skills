# Pi 已知问题与解法

记录 pi 使用中遇到的坑。每个问题按「症状 → 原因 → 解决」组织，末尾附可复用的通用结论。遇到新问题请往这里追加。

---

## 1. 扩展 Tool 冲突（pi-subagents 与 subagent）

**症状**

```
Error: Failed to load extension "/opt/homebrew/lib/node_modules/pi-subagents/src/extension/index.ts": Tool "subagent" conflicts with /Users/sun/Documents/ObsidianVault/.pi/extensions/subagent/index.ts
Hint: Start without extensions using "pi -ne".
```

**原因**

pi 会从多个来源加载扩展。本例两个扩展都注册了名为 `subagent` 的 tool，同名冲突导致 pi 拒绝启动：

- `npm:pi-subagents`（在 `settings.json` 的 `packages` 数组里，`npm:` 前缀 → 解析到系统全局 `/opt/homebrew/lib/node_modules/pi-subagents`）
- 项目本地 `<project>/.pi/extensions/subagent/index.ts`

**解决**

卸载 `pi-subagents`（全局 npm 装的插件，与项目本地 `subagent` 扩展功能重叠）。见「2. 卸载 npm 扩展要清三处」。

**排查技巧**

- `pi -ne`：不带扩展启动，快速确认是扩展问题还是 pi 本身问题。

---

## 2. 卸载 npm 扩展要清三处（否则报错依旧）

删除/卸载一个通过 npm 安装的 pi 扩展（如 `pi-subagents`），必须清理**三处**，漏一处 pi 仍会尝试加载：

| # | 位置 | 操作 |
|---|------|------|
| 1 | 系统全局 npm | `npm uninstall -g pi-subagents` |
| 2 | 本地 npm | `rm -rf ~/.pi/agent/npm/node_modules/pi-subagents` |
| 3 | `~/.pi/agent/settings.json` 的 `packages` 数组 | 删掉 `"npm:pi-subagents"` 这一行 |

**关键**：`settings.json` 的 `packages` 数组是扩展的**加载清单**。只要数组里还留着 `"npm:pi-subagents"`，pi 启动时仍会尝试加载它（即使包目录已删），报「Failed to load extension」。所以第 3 步是根治，前两步是清干净残留。

**典型报错**（只删了目录、没改 settings.json 时）：

```
Error: Failed to load extension "/opt/homebrew/lib/node_modules/pi-subagents/src/extension/index.ts": Tool "subagent" conflicts with ...
```

---

## 3. 扩展加载源与优先级（速查）

pi 从以下位置加载扩展，**项目级优先于全局**：

| 来源 | 路径 | 说明 |
|------|------|------|
| 项目扩展 | `<project>/.pi/extensions/*.ts` 或 `*/index.ts` | 项目级，优先 |
| 全局扩展 | `~/.pi/agent/extensions/*.ts` | 单文件扩展 |
| `settings.json` 的 `packages[]` | `npm:<pkg>` / 绝对路径 `.ts` | 显式加载清单 |
| 全局本地 npm | `~/.pi/agent/npm/node_modules/` | 本地 npm 包 |
| 系统全局 npm | `/opt/homebrew/lib/node_modules/` | `npm:` 前缀的解析目标 |

`packages` 数组支持两种条目：

- `"npm:<包名>"` → 作为 npm 包加载（本例解析到系统全局 npm）
- `"/绝对/路径/index.ts"` → 直接加载该扩展入口文件

---

## 4. 配置位置速查

| 文件 | 作用 |
|------|------|
| `~/.pi/agent/settings.json` | 主配置：`defaultProvider`、`defaultModel`、`packages[]`（扩展清单）、`enabledModels`、`dashboardPluginBridges`、`theme` 等 |
| `~/.pi/agent/auth.json` | 认证（权限 600） |
| `~/.pi/agent/models.json` / `models-store.json` | 模型配置 / 缓存 |
| `~/.pi/agent/providers.json` | LLM provider 配置 |
| `~/.pi/agent/pi-debug.log` | 调试日志（排障首选） |
| `~/.pi/agent/sessions/` | 会话历史 |
| `<project>/.pi/settings.json` | 项目级配置（如 `skills` 路径、`quietStartup`） |

---

## 5. auto-server 更新 `.pi/skills`：脚本按 cwd 定位仓库根

**症状**

在 auto-server（dev@auto-server）上执行 `.pi/skills` 更新脚本时无任何输出、静默失败，exit code 128。

**原因**

更新脚本用**当前工作目录**定位 git 仓库根。当时 cwd 是 `/home/dev`（不是 git 仓库），脚本内的 git 命令直接失败，且错误未被打印，表现为「什么都没发生」。

**解决**

先进入仓库目录再执行：

```bash
ssh dev@auto-server
cd /home/dev/.pi/skills && <更新脚本>
```

**注意**：该仓库带 submodule `axton-obsidian-visual-skills`，更新后主库可能只剩 submodule 指针变更需要提交；两边都已是最新时无需提交。

**通用结论**：任何「按 cwd 找仓库根」的脚本，静默失败先查 cwd 是否在仓库内。

---

## 6. `ws:` 解析失败：catalog 有名字不等于本机有绑定

**症状**

- `ws:MainDev` → `unknown workspace`
- `ws:obsidianvault` → `workspace obsidianvault has no local binding or remote route`

**原因**

`ws:`/`host:` 路由由项目扩展 `.pi/extensions/workspace-routing` 提供，后端是 `.claude/scripts/agent_control/agentctl.py`。解析依赖**两处数据源同时就位**：

| 数据源 | 位置（Windows） | 内容 |
|------|------|------|
| 共享 catalog | `.claude/agent-control/workspaces.json` | 只有逻辑名字，无机器路径，可入库共享 |
| 本机注册表 | `%LOCALAPPDATA%\agent-control\workspaces.json` | 机器路径绑定，每台机器私有，**从不入库** |

两种报错对应不同缺失：

- `unknown workspace`：名字既不在 catalog 也不在本机绑定里。
- `has no local binding or remote route`：catalog 里有名字，但本机注册表里没有对应路径绑定，也没配远程路由。

在从没跑过 add 流程的机器上，本机注册表文件**根本不存在**，所以所有 `ws:` 都失败——这不是 bug，是还没做本机绑定。

**解决**

逐目录执行 add 流程（两阶段、幂等，重复跑报 `alreadyApplied` 不会重复写）：

1. pi TUI 里 `/workspace-add <已存在目录>`，或让 agent 调 `workspace_add` 工具（每次弹 UI 确认框）。
2. 命令行批量：
   ```bash
   python .claude/scripts/agent_control/agentctl.py add-plan <path> --name X --alias Y
   python .claude/scripts/agent_control/agentctl.py add-apply <proposalId> --confirm <proposalId>
   ```

机制要点：

- proposal 带 SHA256 完整性校验，不可变；注册表原子写入+文件锁。
- apply 时校验 Orca 注册状态：已注册则跳过，未注册自动 `orca repo add`。
- 名字命中已有 catalog 条目会自动挂靠；**机器路径只写本机注册表，不进共享 catalog**，所以换机器后必须重新 add 一遍。

---

## 7. Skill 名称冲突告警：`.agents/skills` 扫描把命令模板当成 skill

**症状**

pi 启动时报 `Skill conflicts`：

```
"commands" collision:
  ✓ auto (project) .../.agents/skills/diagram-design/commands/export-diagram.md
  ✗ .../commands/import-drawio.md (skipped)  ...
```

**原因**

pi 对 `.agents/skills/`（含 cwd 及祖先目录）的扫描规则与 `.pi/skills` 不同：**分组目录里任何带 `description` frontmatter 的嵌套 .md 都会被当作 skill**（见 `dist/core/package-manager.js` 的 `collectSkillEntries`，mode="agents" 时 `dir !== root` 的 .md 全收）。名字回落到父目录名 → `diagram-design/commands/*.md` 全部叫 "commands"、prompts/ 全部叫 "prompts" → 同名冲突，第一个胜出，其余 skipped，还污染系统提示里的 skills 列表。

本仓库踩坑点：`diagram-design` 是 vendored 的多 harness 仓库，**根目录没有 SKILL.md**（真身在 `skills/diagram-design/SKILL.md`），扫描器不会在它的根目录停住，于是递归撞上 Claude Code 斜杠命令模板 `commands/*.md` / `prompts/*.md`（它们必须带 `description` frontmatter）。根目录有 SKILL.md 的 skill（如 frontend-slides）不受影响——扫到 SKILL.md 就停止递归。

**解决**

pi 的资源扫描器**尊重 `.gitignore` / `.ignore` / `.fdignore`**（`addIgnoreRules`，每层目录累积规则）。在 skills 仓库根放 `.ignore`：

```
diagram-design/commands/
diagram-design/prompts/
```

已落地：`.claude/skills/.ignore`（luckey_skills 仓库，commit c12813b）。用 `.ignore` 而非 `.gitignore`：git 不读它，语义上只是「扫描器忽略」，且不动 vendored 树，上游更新不冲突；对其他 harness（Codex 等）无影响。

**排查技巧**

- 复现/验证扫描结果：用 pi 自带 `node_modules/ignore` 写个复刻 `collectSkillEntries` 的小脚本跑 `.agents/skills`，对比加 `.ignore` 前后（本次验证：9 个 bogus skill → 0，59 个真 skill 全保留）。
- 判断某 skill 发现来源：看冲突报告里的路径前缀——`.agents/skills/...` 走 agents 分组规则；settings `skills[]` 数组路径只递归收 SKILL.md，嵌套 .md 不会误收。

---

## 8. dynamic-workflows 编排全部 agent() 秒回 null：tier 模型在 subagent 运行时无法实例化

**症状**

`workflow` 工具创建的 Run 正常启动，但所有 `agent()` 调用在 ~0.1s 内全部返回 `null`——不是任务本身失败，是 subagent 根本没跑起来（真实 eval/部署任务不可能在 0.1s 内完成）。

**原因**

tier 映射（`/workflows-models` 配置）把 tier 解析到 `anthropic/kimi-k3`，该模型在 subagent 进程里实例化失败，报 `undefined.create`，spawn 即崩。主会话能用同一模型不代表 subagent 运行时能加载它。

**排查**

- 不要重跑 workflow 碰运气；直接查该 Run 的 workflow 运行日志，找 spawn 阶段的报错（如 `undefined.create`）。
- 判别特征：agent() 返回耗时 <1s 且结果为 null ≈ subagent 未启动，而非任务失败。

**解决**

- 应急：放弃 workflow 编排，改为直接顺序执行（已验证可行）。
- 根治：修 `/workflows-models` 的 tier 映射，把各 tier 指到 subagent 会话能实际实例化的模型，修好后才能再用 workflow fan-out。

---

> 扩展**开发**细节（扩展布局、hook API、注册 provider、多机共享原则）见项目内 `.pi/extensions/SKILL.md`（pi-extensions 技能）。

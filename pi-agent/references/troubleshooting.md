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

> 扩展**开发**细节（扩展布局、hook API、注册 provider、多机共享原则）见项目内 `.pi/extensions/SKILL.md`（pi-extensions 技能）。

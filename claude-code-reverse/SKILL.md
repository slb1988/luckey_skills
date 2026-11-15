---
name: claude-code-reverse
description: 逆向分析 Claude Code CLI 本体（2.x 为 Bun 编译的单文件原生二进制）。提取内嵌的混淆 JS bundle 为可解析模块，用于分析 feature 实现逻辑、版本 diff、prompt/工具/权限机制考古。每当用户想拆解/逆向/分析 Claude Code 本身、问"claude code 是怎么实现 X 的"、对比 Claude Code 版本差异、提取其中的 system prompt 或工具定义时使用。也适用于其他 Bun build --compile 单文件二进制的 JS 提取问题。Trigger whenever the user wants to reverse engineer, unpack, or analyze the Claude Code binary itself or any Bun-compiled standalone executable.
---

# Claude Code 逆向分析

## 目标形态认知（先读）

- Claude Code 2.x 不再发布 `cli.js`：npm 包 `@anthropic-ai/claude-code` 只是 wrapper（`cli-wrapper.cjs` + `install.cjs`），真实代码在平台原生二进制里（Windows: `claude.exe`，~350MB PE）。
- 二进制是 `bun build --compile` 产物：JS bundle 以明文嵌在文件尾部区域，但与二进制 blob（.node/WASM/ICU/JSC 字节码）交错，**不能**用 `strings` 或括号匹配提取（会碎裂，见 references/extraction-methodology.md）。
- 本机已装版本在 `~/.local/share/claude/versions/<版本号>`；当前版 `claude --version` 可查。
- 提取产物是可再生的：默认放临时目录，不要提交进仓库。

## 快速上手

```bash
# 依赖（一次性）
pip install click jsbeautifier tree-sitter tree-sitter-javascript

# 看二进制基本信息（不提取）
python scripts/extract_bundle.py info --binary "C:/Users/admin/.local/share/claude/versions/2.1.321"

# 完整提取（~1-2 分钟，346MB 二进制 → ~50MB JS → 2200+ 模块）
python scripts/extract_bundle.py extract --binary <二进制路径> -o /tmp/claude-re/v<版本>
```

产物：
- `bundle.js` — 缝合后的原始 bundle（检索用，行内仍是压缩的）
- `claude-app.js` — 美化后的 app 代码（约 18MB / 21 万行，主要阅读对象）
- `manifest.txt` — 模块清单（按大小排序的 app 模块 + vendored 分类统计）

模块形态：`var <名>=<wrapper>(()=>{...})`（wrapper 名每个版本都变，脚本自动探测众数，不要硬编码）。

## 分析一个 feature 的标准流程

1. **定关键词**：官方 CHANGELOG（`gh api repos/anthropics/claude-code/contents/CHANGELOG.md -H "Accept: application/vnd.github.raw"`）找到引入版本与描述，从中提取配置项名、env var、命令名、UI 文案作为检索锚点。env var（`CLAUDE_CODE_*`）和 setting key 是最稳定的锚点。
2. **定位模块**：在 `claude-app.js` 里 grep 锚点 → 找到所在 `var X=p(()=>{...})` 模块 → 读该模块全体。
3. **追数据流**：从入口（命令注册/工具定义/hook 点）跟到状态变化与输出；注意 minified 代码里字符串字面量（prompt、错误消息）是最可靠的路标。
4. **区分观察与推测**：minified 标识符不可信，凡是靠语义猜的用途必须标注「推测」；能交叉验证（字符串、changelog、行为）的才写定论。
5. **写文档**：每个独立 feature 一个 `references/feature-<slug>.md`，大 feature 拆成 `feature-<slug>.md`（索引）+ `feature-<slug>-<子主题>.md`，并在下方索引登记。

## 版本对比 / 找新 feature

- 新 feature 清单：CHANGELOG 里筛 `- Added`（见上方 gh api 命令）。
- SDK 表面变化：`npm pack @anthropic-ai/claude-code@<旧> @<新>`，diff 两版的 `sdk-tools.d.ts`。
- 二进制级对比：对两个版本分别 extract，然后按模块名 diff manifest，或对 `claude-app.js` 做 `git diff --no-index --stat` 找变动区域。旧版本二进制本机 `~/.local/share/claude/versions/` 通常有留存。

## 新版本失效时的排查

wrapper 自动探测覆盖了最常见的失效（minified 名重排）。若仍失败，按 references/extraction-methodology.md 的「Updating for new versions」节排查：trailer 是否还在、模块包装形态是否变了、二进制是否改为压缩存储。

## References

- [extraction-methodology.md](references/extraction-methodology.md) — 提取管线原理、失败模式、社区方案对比
- Feature 分析（按引入版本组织，持续累积）：
  - [feature-code-mode.md](references/feature-code-mode.md) — Code Mode（2.1.323，实验性 JS 工具调用）
  - [feature-mod-runtime.md](references/feature-mod-runtime.md) — Mod 插件运行时（engine.create、`$` nouns、panes）
  - [feature-mcp-tasks.md](references/feature-mcp-tasks.md) — MCP tasks 终端后台化与 `/tasks`（2.1.319）
  - [feature-subagent-summaries.md](references/feature-subagent-summaries.md) — 子代理进度摘要（2.1.318/323）
  - [feature-permissions-guardrails.md](references/feature-permissions-guardrails.md) — 权限新语义（denyInsteadOfPrompting、blockWritesOutsideWorkingDirectories 等）
  - [feature-remote-control.md](references/feature-remote-control.md) — Remote Control 主机端（跨设备接管会话）

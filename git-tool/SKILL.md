---
name: git-tool
description: Git 仓库工具，支持两个命令：(1) update/sync：将主仓库和所有 git submodule 递归更新到远端最新；(2) commit <submodule名>：将指定 submodule 的本地变更提交并推送，再同步更新主仓库的 submodule 指针。当用户说 "git-tool update"、"git-tool sync"、"git-tool commit skills"、"提交 submodule"、"同步 submodule" 时触发。出现冲突或错误时立即中断，给出具体的手动解决命令。
---

# git-tool: 递归更新主库 + 所有 Submodule

## 命令一览

| 命令 | 说明 |
|------|------|
| `git-tool update` / `git-tool sync` | 主库 pull + 所有 submodule 更新到远端最新 |
| `git-tool update submodule` | 仅更新 submodule，跳过主库 pull（工作区有改动时使用） |
| `git-tool commit <submodule名>` | 提交指定 submodule 的变更并推送，再更新主库指针 |

---

## `git-tool commit <submodule名>`

**专用于提交 submodule 内部的改动**，同时将主库的 submodule 指针一并更新提交。不处理主库的其他改动。

### 执行流程

**Step 1：定位 submodule 路径** — 从 `.gitmodules` 匹配名字；匹配到多个或找不到时，停止并列出所有 submodule。

**Step 2：检查有无改动** — `git -C <path> status --porcelain`；工作区为空则停止。

**Step 3：确认非 detached HEAD** — `git -C <path> branch --show-current`；若空则 `checkout main`（不要立刻 pull，在 push 时处理 non-fast-forward）。

**Step 4：提交** — `git -C <path> add -A && git -C <path> commit -m "update: <描述>"`

**Step 5：推送** — `git -C <path> push origin <branch>`；non-fast-forward 先 `pull --rebase` 再推。

**Step 6：更新主库指针** — `git -C <root> add <path> && git -C <root> commit -m "chore: update <name> submodule"`

**Step 7：推送主库** — `git -C <root> push origin <branch>`

**Step 8：汇报结果**
```
✅ git-tool commit <submodule名> 完成
<path>：已提交并推送（abc1234）
主库：submodule 指针已更新并推送（def5678）
```

---

## `git-tool update` / `git-tool sync`

### Step 1：确认工作区干净

```bash
git -C <root> status --porcelain
```

输出非空时**停止**并提示：
```
⚠️ 工作区有未提交的修改，更新前请先处理：
  暂存改动：  git stash --include-untracked
  提交改动：  git add -A && git commit -m "wip"

如只想同步 submodule，可运行：git-tool update submodule
```

### Step 2：主库 pull

```bash
git -C <root> pull --rebase origin $(git -C <root> branch --show-current)
```

> 详细冲突解决：[references/conflict-resolution.md](references/conflict-resolution.md)

### Step 3：初始化未 init 的 submodule

```bash
git -C <root> submodule update --init --recursive
```

### Step 4：递归更新所有 submodule 到远端最新

```bash
git -C <root> submodule update --remote --merge --recursive
```

**嵌套 submodule 克隆失败的恢复方式**（`--recursive` 进不去某个嵌套子模块时）：

`--remote --recursive` 在父 submodule 的工作目录内递归执行，从主库根目录无法用路径参数指定嵌套子模块。恢复方式是进入父 submodule 目录单独 init：

```bash
# 失败示例：致命错误：无法递归进入子模组路径 '.claude/skills'
# 正确做法：进入父 submodule，在其内部 init 失败的子模块
git -C <root>/.claude/skills submodule update --init huashu-design notebooklm-py
```

不要尝试 `git -C <root> submodule update --init .claude/skills/huashu-design`——主库的 `.gitmodules` 不知道嵌套 submodule，路径不匹配。

### Step 5：提交 submodule 指针变更

```bash
git -C <root> diff --submodule   # 确认有变化
git -C <root> add .claude/skills  # 只 add 已更新的 submodule，避免混入工作区其他改动
git -C <root> commit -m "chore: update submodules to latest"
git -C <root> push origin <branch>
```

无变化则跳过，告知用户「已是最新，无需提交」。

### Step 6：汇报结果

```
✅ git-tool update 完成

主库：已拉取到最新（abc1234）

Submodule 更新情况：
  .claude/skills    旧: 2c8adab → 新: 36ce08a
  PluginDev/...     已是最新
```

---

## `git-tool update submodule`（仅更新 submodule）

工作区有未提交改动时的替代方案，跳过主库 pull，直接执行 Step 3-6。

提交主库指针时**只 add submodule 路径**，不要用 `add --all`（会混入工作区无关改动）：

```bash
git -C <root> add .claude/skills
git -C <root> commit -m "chore: update .claude/skills submodule to latest"
```

---

## 注意事项

- **`--remote` 的含义**：更新到远端最新，而非主库记录的 commit hash。
- **不要强制 push**：本 skill 只做 pull/update，不涉及强制操作。
- **主库 `index.lock` 残留**：`Unable to create '.git/index.lock': File exists` 时，确认无其他 git 进程后删除：`rm <root>/.git/index.lock`。
- **SSH vs HTTPS**：HTTPS 推送持续超时时切换：`git remote set-url origin git@github.com:<user>/<repo>.git`

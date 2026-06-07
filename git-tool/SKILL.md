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

### 用法示例

```
git-tool commit skills        # submodule 路径含 "skills" 的
git-tool commit .claude/skills
```

### 执行流程

**Step 1：定位 submodule 路径**

从 `.gitmodules` 中匹配用户输入的名字，找到对应的 `path`。若匹配到多个或找不到，停止并列出所有 submodule 让用户确认。

**Step 2：进入 submodule，检查有无改动**

```bash
git -C <submodule_path> status --porcelain
```

若工作区为空（无改动、无暂存），停止并提示：「<submodule名> 没有需要提交的改动」。

**Step 3：确认 submodule 在正常分支上（非 detached HEAD）**

```bash
git -C <submodule_path> branch --show-current
```

若输出为空（detached HEAD），切回 main：
```bash
git -C <submodule_path> checkout main
```

> **注意**：`checkout main` 后不要立刻 `pull`——网络不通时 pull 会失败并阻断流程。
> 继续执行 Step 4 commit，在 Step 5 push 时再处理远端同步（non-fast-forward 用 `pull --rebase` 解决）。

**Step 4：在 submodule 内 stage 全部改动并提交**

```bash
git -C <submodule_path> add -A
git -C <submodule_path> commit -m "update: <由改动内容自动生成的简短描述>"
```

**Step 5：推送 submodule 到远端**

```bash
git -C <submodule_path> push origin <当前分支>
```

失败时：

- **non-fast-forward（remote 有更新的 commit）**：先 rebase 再推送：
  ```bash
  git -C <submodule_path> pull --rebase origin <当前分支>
  git -C <submodule_path> push origin <当前分支>
  ```
- **其他失败**：停止并提示：
  ```
  ⚠️ 推送失败，请手动处理：
  cd <submodule_path>
  git push origin main
  ```

**Step 6：回到主库，更新 submodule 指针并提交**

```bash
git -C <repo_root> add <submodule_path>
git -C <repo_root> commit -m "chore: update <submodule名> submodule"
```

**Step 7：推送主库到远端**

```bash
git -C <repo_root> push origin $(git -C <repo_root> branch --show-current)
```

失败时停止并提示：
```
⚠️ 主库推送失败，请手动处理：
git push origin main
```

**Step 8：汇报结果**

```
✅ git-tool commit <submodule名> 完成

<submodule_path>：已提交并推送（<commit hash 前7位>）
主库：submodule 指针已更新并推送（<commit hash 前7位>）
```

---

## `git-tool update` / `git-tool sync`

### 执行顺序：先主库 pull → 再递归更新所有 submodule。每步出错立即停止并给出手动解决方案。

### Step 1：确认当前工作区干净

```bash
git -C <repo_root> status --porcelain
```

输出非空时**停止**并提示：
```
⚠️ 工作区有未提交的修改，更新前请先处理：

查看改动：  git status
暂存改动：  git stash --include-untracked
提交改动：  git add -A && git commit -m "wip"

如只想同步 submodule，可运行：git-tool update submodule
```

### Step 2：主库 pull

```bash
git -C <repo_root> pull --rebase origin $(git -C <repo_root> branch --show-current)
```

失败时的常见原因和解决方案：

| 错误关键词 | 原因 | 手动解决 |
|-----------|------|---------|
| `CONFLICT` / `conflict` | rebase 冲突 | 见 [references/conflict-resolution.md](references/conflict-resolution.md) |
| `rejected` | 本地有远端没有的 commit | `git push` 先推送，或 `git pull --no-rebase` |
| `no such remote` | remote 未配置 | `git remote add origin <url>` |
| `Authentication failed` | 认证失败 | 检查 SSH key 或 token |

### Step 3：初始化未 init 的 submodule

```bash
git -C <repo_root> submodule update --init --recursive
```

这一步确保新增的 submodule 被正确初始化。

失败时：
```
⚠️ Submodule 初始化失败，请手动执行：
git submodule update --init --recursive

可能原因：
- 子模块仓库地址变更：检查 .gitmodules 中的 url
- 网络问题：确认可访问 GitHub
```

### Step 4：递归将所有 submodule 更新到远端最新

```bash
git -C <repo_root> submodule update --remote --merge --recursive
```

这会将**每个 submodule** 拉到其远端默认分支（通常是 main/master）的最新 commit。

失败时：
```
⚠️ Submodule 更新失败：<submodule路径>

手动更新单个 submodule：
cd <repo_root>/<submodule路径>
git pull origin main   # 或 master，视该仓库默认分支而定

如果有冲突，见 references/conflict-resolution.md
```

**嵌套 submodule 克隆失败的恢复方式**（`--recursive` 进不去某个嵌套子模块时）：

`--remote --recursive` 在父 submodule 的工作目录内递归执行，从主库根目录无法用路径参数指定嵌套子模块。恢复方式是进入父 submodule 目录单独 init：

```bash
# 失败示例：致命错误：无法递归进入子模组路径 '.claude/skills'
# 正确做法：进入父 submodule，在其内部 init 失败的子模块
git -C <repo_root>/.claude/skills submodule update --init huashu-design notebooklm-py
```

不要尝试 `git -C <repo_root> submodule update --init .claude/skills/huashu-design`——主库的 `.gitmodules` 不知道嵌套 submodule，路径不匹配。

### Step 5：提交 submodule 指针变更

submodule 更新后，主库会检测到 submodule 指向了新的 commit，需要提交这个变更：

```bash
git -C <repo_root> diff --submodule   # 先确认有变化
git -C <repo_root> add .claude/skills  # 只 add 已更新的 submodule，避免混入工作区其他改动
git -C <repo_root> commit -m "chore: update submodules to latest"
git -C <repo_root> push origin <branch>
```

如果没有任何变化（submodule 本就是最新），跳过提交步骤，告知用户「已是最新，无需提交」。

### Step 6：汇报结果

```
✅ git-tool update 完成

主库：已拉取到最新（<当前 commit hash 前7位>）

Submodule 更新情况：
  .claude/skills          旧: abc1234 → 新: def5678
  PluginDev/.obsidian/plugins/obsidian-sample-plugin  已是最新

如有 submodule 指针变更已自动提交到主库。
```

---

## `git-tool update submodule`（仅更新 submodule）

工作区有未提交改动时的替代方案，跳过主库 pull，直接执行 Step 3-6。

提交主库指针时**只 add submodule 路径**，不要用 `add --all`（会混入工作区无关改动）：

```bash
git -C <repo_root> add .claude/skills
git -C <repo_root> commit -m "chore: update .claude/skills submodule to latest"
```

---

## 注意事项

- **`--remote` 的含义**：将 submodule 更新到其远端最新，而不是主库记录的那个 commit hash。这正是「同步到最新」的语义。
- **嵌套 submodule**：`--recursive` 确保 submodule 里的 submodule（如 .claude/skills 内部的各 skill 子模块）也一并更新。
- **不要强制 push**：本 skill 只做 pull/update，不涉及强制操作。
- **认证**：确保 SSH key 或 HTTPS token 对所有涉及的仓库有效。
- **主库 `index.lock` 残留**：Obsidian 等工具在后台读写时可能持有 git index 锁；若主库 commit 报 `Unable to create '.git/index.lock': File exists`，先确认没有其他 git 进程，再删除锁文件：`rm <repo_root>/.git/index.lock`，然后重试 commit。
- **SSH vs HTTPS**：HTTPS 推送持续超时时切换：`git remote set-url origin git@github.com:<user>/<repo>.git`

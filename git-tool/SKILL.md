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

> 详细执行流程：[commit-flow](references/commit-flow.md) · [update-flow](references/update-flow.md) · [conflict-resolution](references/conflict-resolution.md)

---

## `git-tool commit <submodule名>`

专用于提交 submodule 内部的改动，同时更新主库 submodule 指针。

关键判断点：
- submodule 处于 detached HEAD 时先 `checkout main`，**不要立刻 pull**（网络问题会阻断流程）
- push 失败且为 non-fast-forward → `pull --rebase` 后重试
- 只 `add <submodule_path>` 更新主库指针，不要 `add -A`

---

## `git-tool update` / `git-tool sync`

执行顺序：主库 pull → submodule init → submodule update --remote → 提交指针变更

关键判断点：
- `??` untracked 文件、submodule 指针变更（`M <path>`）→ **不需要停止**，可继续
- tracked 文件改动 → 停止，提示 stash 或先 commit
- `pull --rebase` 报「未暂存变更」→ 自动回退 `--no-rebase`
- submodule 没变化 → 跳过 commit 步骤，告知「已是最新」

### 嵌套 submodule 的作用域边界

`--remote --recursive` 在父 submodule 的工作目录内递归执行。**主库的 `.gitmodules` 不知道嵌套 submodule**，无法从主库根目录用路径指定它们。

嵌套 submodule init 失败时，正确做法是进入父 submodule 目录：
```bash
# 错误：从主库根目录无法定位嵌套路径
git -C <repo_root> submodule update --init .claude/skills/huashu-design  # 不起作用

# 正确：进入父 submodule，在其内部 init
git -C <repo_root>/.claude/skills submodule update --init huashu-design
```

---

## `git-tool update submodule`（仅更新 submodule）

跳过主库 pull，直接执行 init → update --remote → 提交指针。

提交主库指针时只 add submodule 路径：
```bash
git -C <repo_root> add .claude/skills
git -C <repo_root> commit -m "chore: update .claude/skills submodule to latest"
```

---

## 移除失效的 nested submodule

当某个嵌套 submodule 的远端仓库已删除或设为私有（`remote: Repository not found`），需要将其从父 submodule 中完整清除：

```bash
# 1. deinit：清空工作目录、注销 .git/config 登记
git -C <parent_submodule_path> submodule deinit -f <submodule_name>

# 2. git rm：从 index 和 .gitmodules 中移除
git -C <parent_submodule_path> git rm -f <submodule_name>

# 3. 清理 .git/modules 缓存（防止重新 add 时冲突）
rm -rf <parent_submodule_path>/.git/modules/<submodule_name>

# 4. 提交
git -C <parent_submodule_path> commit -m "chore: remove <submodule_name> submodule (repo not found)"
git -C <parent_submodule_path> push origin main
```

移除后如果父 submodule 处于 detached HEAD，需要先切回 main 再 merge：
```bash
git -C <parent_submodule_path> checkout main
git -C <parent_submodule_path> merge <commit_hash>
git -C <parent_submodule_path> push origin main
```

最后在主库更新 submodule 指针并推送。

---

## 注意事项

- **`--remote` 的含义**：将 submodule 更新到其远端最新，而不是主库记录的 commit hash
- **嵌套 submodule**：`--recursive` 确保 submodule 里的 submodule 也一并更新
- **不要强制 push**：本 skill 只做 pull/update，不涉及强制操作
- **主库 `index.lock` 残留**：若 commit 报 `Unable to create '.git/index.lock': File exists`，确认无其他 git 进程后删除：`rm <repo_root>/.git/index.lock`
- **SSH vs HTTPS**：HTTPS 推送持续超时时切换：`git remote set-url origin git@github.com:<user>/<repo>.git`

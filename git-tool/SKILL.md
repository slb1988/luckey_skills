---
name: git-tool
description: Git 仓库全量更新工具，将主仓库和所有 git submodule 递归更新到远端最新状态。当用户说 "git-tool update"、"git-tool sync"、"更新仓库"、"同步 submodule"、"git 更新"、"pull 最新"、"更新所有 submodule" 时触发。出现冲突或错误时立即中断，给出具体的手动解决命令。
---

# git-tool: 递归更新主库 + 所有 Submodule

## 触发词

用户输入 `git-tool update`、`git-tool sync` 或类似意图（更新仓库、同步 submodule）时执行以下流程。

## 执行流程

执行顺序：**先主库 pull → 再递归更新所有 submodule**。每步出错立即停止并给出手动解决方案。

### Step 1：确认当前工作区干净

```bash
git -C <repo_root> status --porcelain
```

- 如果有未提交的修改（输出非空），**停止**并提示：
  ```
  ⚠️ 工作区有未提交的修改，更新前请先处理：
  
  查看改动：  git status
  暂存改动：  git stash
  提交改动：  git add -A && git commit -m "wip"
  
  处理后重新运行 git-tool update
  ```

### Step 2：主库 pull

```bash
git -C <repo_root> pull --rebase origin $(git -C <repo_root> branch --show-current)
```

失败时的常见原因和解决方案：

| 错误关键词 | 原因 | 手动解决 |
|-----------|------|---------|
| `CONFLICT` / `conflict` | rebase 冲突 | 见下方「冲突解决」 |
| `rejected` | 本地有远端没有的 commit | `git push` 先推送，或 `git pull --no-rebase` |
| `no such remote` | remote 未配置 | `git remote add origin <url>` |
| `Authentication failed` | 认证失败 | 检查 SSH key 或 token |

**Rebase 冲突手动解决：**
```bash
# 1. 查看冲突文件
git status

# 2. 手动编辑冲突文件，解决 <<<< ==== >>>> 标记

# 3. 标记为已解决
git add <冲突文件>

# 4. 继续 rebase
git rebase --continue

# 或放弃 rebase，回到更新前状态
git rebase --abort
```

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

如果有冲突：
git status             # 查看冲突
# 解决冲突后：
git add <冲突文件>
git merge --continue
```

### Step 5：在主库提交 submodule 指针变更

submodule 更新后，主库会检测到 submodule 指向了新的 commit，需要提交这个变更：

```bash
git -C <repo_root> diff --submodule   # 先确认有变化
git -C <repo_root> add --all
git -C <repo_root> commit -m "chore: update submodules to latest"
```

如果没有任何变化（submodule 本就是最新），跳过提交步骤，告知用户「已是最新，无需提交」。

### Step 6：汇报结果

成功后输出摘要，格式如下：

```
✅ git-tool update 完成

主库：已拉取到最新（<当前 commit hash 前7位>）

Submodule 更新情况：
  .claude/skills          旧: abc1234 → 新: def5678
  PluginDev/.obsidian/plugins/obsidian-sample-plugin  已是最新

如有 submodule 指针变更已自动提交到主库。
```

## 注意事项

- **`--remote` 的含义**：将 submodule 更新到其远端最新，而不是主库记录的那个 commit hash。这正是「同步到最新」的语义。
- **嵌套 submodule**：`--recursive` 确保 submodule 里的 submodule（如 .claude/skills 内部的各 skill 子模块）也一并更新。
- **不要强制 push**：本 skill 只做 pull/update，不涉及强制操作。
- **认证**：确保 SSH key 或 HTTPS token 对所有涉及的仓库有效。

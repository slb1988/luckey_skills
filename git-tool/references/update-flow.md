# git-tool update — 详细执行流程

执行顺序：先主库 pull → 再递归更新所有 submodule。每步出错立即停止并给出手动解决方案。

## Step 1：检查工作区

```bash
git -C <repo_root> status --porcelain
```

**不要无脑停止**。只有 tracked 文件改动（行首非 `??`、非纯 submodule 指针变更）才需要停下。

- `??` untracked 文件 → pull 不会碰，可继续
- `M <submodule路径>` → pull 时用 `--no-rebase` 绕过

停止时提示：
```
⚠️ 工作区有 tracked 文件改动，可能与远端冲突，建议先处理：
查看改动：  git status
暂存改动：  git stash --include-untracked
提交改动：  git add -A && git commit -m "wip"
如只想同步 submodule，可运行：git-tool update submodule
```

## Step 2：主库 pull

```bash
git -C <repo_root> pull --rebase origin $(git -C <repo_root> branch --show-current)
```

若报错含「未暂存的变更」（submodule 指针导致），自动回退到：
```bash
git -C <repo_root> pull --no-rebase origin $(git -C <repo_root> branch --show-current)
```

| 错误关键词 | 原因 | 手动解决 |
|-----------|------|---------|
| `CONFLICT` / `conflict` | rebase 冲突 | 见 [conflict-resolution.md](conflict-resolution.md) |
| `rejected` | 本地有远端没有的 commit | `git push` 先推送，或 `git pull --no-rebase` |
| `no such remote` | remote 未配置 | `git remote add origin <url>` |
| `Authentication failed` | 认证失败 | 检查 SSH key 或 token |
| 长时间无输出 / 超时 | QNAP 等低 I/O 设备 `index-pack` 慢，瓶颈不在网络 | 不杀进程，等待完成（575 对象约 8 分钟）。可预先设 `core.compression=0` 加速。详见 SKILL.md 注意事项 |

## Step 3：初始化未 init 的 submodule

```bash
git -C <repo_root> submodule update --init --recursive
```

## Step 4：递归更新所有 submodule 到远端最新

```bash
git -C <repo_root> submodule update --remote --merge --recursive
```

**嵌套 submodule 克隆失败的恢复**（`--recursive` 进不去某个嵌套子模块时）：

`--remote --recursive` 在父 submodule 的工作目录内递归执行，从主库根目录无法用路径参数指定嵌套 submodule。正确做法是进入父 submodule 目录单独 init：

```bash
git -C <repo_root>/.claude/skills submodule update --init huashu-design notebooklm-py
```

不要尝试 `git -C <repo_root> submodule update --init .claude/skills/huashu-design`——主库的 `.gitmodules` 不知道嵌套 submodule，路径不匹配。

## Step 5：提交 submodule 指针变更

```bash
git -C <repo_root> diff --submodule   # 确认有变化
git -C <repo_root> add .claude/skills  # 只 add 已更新的 submodule
git -C <repo_root> commit -m "chore: update submodules to latest"
git -C <repo_root> push origin <branch>
```

如果没有变化，跳过提交，告知用户「已是最新，无需提交」。

## Step 6：汇报结果

```
✅ git-tool update 完成

主库：已拉取到最新（<当前 commit hash 前7位>）

Submodule 更新情况：
  .claude/skills          旧: abc1234 → 新: def5678
  ...                     已是最新

如有 submodule 指针变更已自动提交到主库。
```

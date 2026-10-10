# git-tool commit — 详细执行流程

## 用法示例

```
git-tool commit skills        # submodule 路径含 "skills" 的
git-tool commit .claude/skills
```

## 执行流程

**Step 1：定位 submodule 路径**

从 `.gitmodules` 中找所有 `path =` 行，用用户输入的名字做**子串匹配**（不区分大小写）。若匹配到多个或找不到，停止并列出所有 submodule 让用户确认。

**Step 2：检查有无改动**

```bash
git -C <submodule_path> status --porcelain
```

若工作区为空，停止并提示：「<submodule名> 没有需要提交的改动」。

**Step 3：确认非 detached HEAD**

```bash
git -C <submodule_path> branch --show-current
```

若输出为空（detached HEAD），切回 main：
```bash
git -C <submodule_path> checkout main
```

> checkout main 后不要立刻 pull——继续执行 Step 4，push 时再处理 non-fast-forward（用 `pull --rebase`）。

**Step 4：Stage 全部改动并提交**

```bash
git -C <submodule_path> add -A
git -C <submodule_path> commit -m "update: <由改动内容自动生成的简短描述>"
```

> **skills 仓库例外**：仓库内长期存在运行残留 untracked 文件（见文末「Scoped 提交的残留甄别」），scoped commit 时不要 `add -A`，改为精确 stage 目标文件。

**Step 5：推送 submodule**

```bash
git -C <submodule_path> push origin <当前分支>
```

失败时：
- **non-fast-forward**：`pull --rebase` 后再 push
- **其他失败**：停止并提示手动处理

**Step 6：更新主库 submodule 指针**

```bash
git -C <repo_root> add <submodule_path>
git -C <repo_root> commit -m "chore: update <submodule名> submodule"
```

**Step 7：推送主库**

```bash
git -C <repo_root> push origin $(git -C <repo_root> branch --show-current)
```

**Step 8：汇报结果**

```
✅ git-tool commit <submodule名> 完成

<submodule_path>：已提交并推送（<commit hash 前7位>）
主库：submodule 指针已更新并推送（<commit hash 前7位>）
```

---

## Scoped 提交的残留甄别（2026-10 实测）

skills 仓库长期存在一批运行残留 untracked 路径，**不属于 skill 本体，不要提交**：

- `memory-review/`：`*.log`（drive/scan）、`decisions_*`、`review_packet*`、`receipts_*`、`run_*/` 等工作文件
- `daily-report/logs/`
- `vscode-as-workspace/`（skill-eval 工作区；同类 `*-workspace` 目录在 `.gitignore` 已有先例，残留模式稳定后也可补进 `.gitignore`）

**untracked 文件的入库判定**：先查是否被 tracked 文档/代码引用——被引用的必须随 commit 入库（实测：`daily-report/scripts/run_scheduled.ps1` 与 `scheduled_prompt.txt` 被 `references/scheduled-automation.md` 引用，漏交会破坏文档引用）；纯运行产物一律不提交。

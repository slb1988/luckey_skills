# git-tool 排障参考

> 从 SKILL.md 移出的排障条目（提交/推送/嵌套 submodule 类）。

- **pre-commit hook 因只读文件报 PermissionError**：`.pi/extensions` 等从 Perforce 拷出的文件带只读属性，Python 编写的 pre-commit hook 无法读取/处理它们。提交前对已暂存文件批量解除只读：`git diff --cached --name-only -z | xargs -0 chmod +w 2>/dev/null`（或针对具体目录 `chmod -R +w .pi/extensions`）。
- **更新嵌套 submodule 指针前先确认其 HEAD 已在远端**：父 submodule 记录了嵌套 submodule（如 `.claude/skills/axton-obsidian-visual-skills`）的指针。若嵌套 submodule 本地领先但未 push，先提交推送其父指针会导致远端无法解析。确认方法：进入嵌套 submodule 执行 `git branch -r --contains HEAD`，有输出才安全。
- **`__pycache__` 已加入 skills .gitignore**（2025-07 修复）：skills 仓库的 `.gitignore` 现包含 `__pycache__/` 和 `*.pyc`，已入库的 `.pyc` 文件已通过 `git rm -r --cached` 清除。`git-tool-commit.sh` 仍会无差别提交所有变更——新增含 Python 脚本的 skill 时，确认 `.gitignore` 覆盖其生成物。
- **detached HEAD 且 `checkout main` 被拒时的安全路径**：实测 HEAD/main/origin/main 同一提交但 checkout 因脏工作区被拒——不要强 checkout 或 stash。在 detached 上直接 commit，然后 `git branch -f main HEAD`（或 `git update-ref refs/heads/main HEAD`）把 main 快进过来，再 `git checkout main`、push；提交不会丢。另外 ObsidianVault 的 `.claude/skills` 仓库里 memory-hub 等 skill 是普通目录、**由 skills 仓库直接跟踪，无独立嵌套 .git**——排查结构时别再进 skill 子目录找独立仓库。
- **下游拉取「submodule 已 inline」的仓库会报 untracked 冲突**（2026-08 实测）：从父仓库视角，submodule 目录内的文件全部是 untracked（父仓库只记录 gitlink）。上游把 submodule inline 成普通文件后，仍保留旧 submodule checkout 的下游克隆 pull 会失败：`error: The following untracked working tree files would be overwritten by merge: diagram-design/...`。上游做 inline 时不会有此冲突（先 `rm --cached` 再 add），只有下游旧克隆会踩。处理顺序：
  ```bash
  # 1. 确认各 submodule 本地干净且 HEAD 已在远端（branch -r --contains 有输出才安全）
  git -C <name> status --short
  git -C <name> branch -r --contains HEAD

  # 2. deinit + 删目录 + 清 .git/modules 缓存
  git submodule deinit -f <name>...
  rm -rf <name>... .git/modules/<name>...

  # 3. 重新 merge，再按新 .gitmodules 初始化剩余 submodule
  git merge origin/main --no-edit
  git submodule update --init --recursive
  ```
  若 update 脚本已 auto-stash，merge 成功后记得 `git stash pop`。
- **`git-tool-update.sh` 以 cwd 定位仓库根**：脚本用 `git rev-parse --show-toplevel` 取 ROOT，从仓库外（如 `$HOME`）执行会以 exit 128 静默失败、无任何输出。必须先 `cd` 进仓库目录再运行脚本。

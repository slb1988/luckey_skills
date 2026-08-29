---
name: git-tool
description: "Git 仓库工具，支持两个命令：(1) update/sync 将主仓库和所有 git submodule 递归更新到远端最新；(2) commit [submodule名] 将指定 submodule 的本地变更提交并推送，再同步更新主仓库的 submodule 指针。当用户说 git-tool update、git-tool sync、git-tool commit skills、提交 submodule、同步 submodule 时触发。出现冲突或错误时立即中断，给出具体的手动解决命令。"
---

# git-tool: 递归更新主库 + 所有 Submodule

## 命令一览

| 命令 | 说明 |
|------|------|
| `git-tool update` / `git-tool sync` | 主库 pull + 所有 submodule 更新到远端最新 |
| `git-tool update submodule` | 仅更新 submodule，跳过主库 pull（工作区有改动时使用） |
| `git-tool commit` | 提交主库 + 所有有改动的 submodule，更新指针并推送 |
| `git-tool commit <submodule名>` | 仅提交指定 submodule（已废弃，推荐用一键脚本） |

> 详细执行流程：[commit-flow](references/commit-flow.md) · [update-flow](references/update-flow.md) · [conflict-resolution](references/conflict-resolution.md) · [troubleshooting](references/troubleshooting.md)

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

## nested submodule 转普通文件（inline，保留内容）

当用户要求「只保留本体文件、与源断开」时，不要删目录再重新拷贝——直接在父仓库里把 gitlink 换成普通文件（2026-08 实测：diagram-design/frontend-slides/huashu-design 三个 skill 共 778 文件入库）：

```bash
# 1. 从 index 移除 gitlink（工作区文件保留）
git -C <parent> rm --cached <name>

# 2. 注销 submodule 登记（三处都要清，缺一不可）
git -C <parent> config -f .gitmodules --remove-section submodule.<name>
git -C <parent> config --remove-section submodule.<name>
rm -rf <parent>/.git/modules/<name>

# 3. 关键坑：删掉目录内的 .git 文件（指向 .git/modules 的指针文件）。
#    不删的话下一步 git add 会把目录重新登记成 gitlink
#    （警告 "adding embedded git repository"），前功尽弃。
rm <parent>/<name>/.git

# 4. 重新 add + 提交
git -C <parent> add .gitmodules <name>
git -C <parent> commit -m "chore: inline <name>, drop submodule link"
```

两个注意点：
- **入库前先扫密钥**：外部仓库内容从未按本仓库标准审过，重点看 `.env*` / `*.example` / 配置里的 `sk-` `key=`（本次三个 skill 的 `.env.example` 均为占位符，安全）。
- inline 保留上游原始目录结构，skill 本体可能不在顶层——如 `diagram-design` 的 SKILL.md 实际在 `diagram-design/skills/diagram-design/` 下。
- **下游旧克隆 pull 这个改动会报 untracked 冲突**，需要 deinit + 删目录后重新 merge，处理流程见 [troubleshooting](references/troubleshooting.md)。

---

## 仓库位置（重要）

**仓库根统一写 `~/.pi/skills`，不要写死具体机器路径**（`/home/dev/...`、`/home/ubuntu/...`、QNAP 的 `/share/...` 都是同一仓库在不同机器上的不同挂载点，文档里出现具体绝对路径会在其他机器上误导）。

- 仓库根：`~/.pi/skills`（早期文档里的 `.claude/skills` 为旧路径，一律按 `~/.pi/skills` 理解）
- 脚本位置：`~/.pi/skills/git-tool/git-tool-update.sh` / `git-tool-commit.sh`
- 脚本内部用 `git rev-parse --show-toplevel` 以 **cwd** 定位 ROOT：**必须先 `cd` 进仓库再执行**，在仓库内任意位置均可；从仓库外运行会 exit 128 静默失败（见 [troubleshooting](references/troubleshooting.md)）
- 该仓库自身现仅含 1 个 submodule：`axton-obsidian-visual-skills`（`diagram-design`/`frontend-slides`/`huashu-design` 已于 2026-08 转为普通文件 inline 入库，见上文「nested submodule 转普通文件」）

**脚本自带了保留本地修改的能力**（`git-tool-update.sh` 自动 stash→pull→恢复 stash），所以即使仓库有未提交改动，也可以放心执行 update，改动会被暂存保护后还原。

---

## 一键脚本

推荐用脚本替代手动交互流程，避免浪费 token：

```bash
cd ~/.pi/skills && bash git-tool/git-tool-update.sh   # 更新
cd ~/.pi/skills && bash git-tool/git-tool-commit.sh   # 提交所有有改动的 submodule
```

### git-tool-update.sh

**自动处理：** stash tracked 改动 → pull → submodule init+update → 提交指针变更 → 恢复 stash。

触碰边界时只警告不停止：
- submodule 内部有 tracked 改动 → 警告，不自动处理（需手动决定）
- 嵌套 submodule init 失败 → 自动尝试从父 submodule 层重新 init

### git-tool-commit.sh

**自动处理：** 提交主库 tracked 改动 → 扫描所有 submodule 提交 + 推送 → 更新主库指针 → 推送。

三个层次的变更一次搞定：主库代码、submodule 内变更、主库指针。

**适用边界（2026-08 实测）：** 脚本的「提交主库」实为 `git add -A`（tracked + untracked 全量，自动提交信息 `update: <文件名>`），不止 tracked 改动。用户要求 scoped 提交（如只说「commit skills」）而主库还有无关未提交改动时，**不要用本脚本**——无关改动会被一并卷入。改用手动精确流程：submodule 内 commit+push → 主库只 `add <submodule_path>` 提交指针。（实测：主库 `.pi/extensions/auto-skill/index.ts` 的未提交改动就差点被「commit skills」卷进去。）

---

## 注意事项

- **`--remote` 的含义**：将 submodule 更新到其远端最新，而不是主库记录的 commit hash
- **嵌套 submodule**：`--recursive` 确保 submodule 里的 submodule 也一并更新
- **不要强制 push**：本 skill 只做 pull/update，不涉及强制操作
- **主库 `index.lock` 残留**：若 commit 报 `Unable to create '.git/index.lock': File exists`，确认无其他 git 进程后删除：`rm <repo_root>/.git/index.lock`
- **SSH vs HTTPS**：HTTPS 推送持续超时时切换：`git remote set-url origin git@github.com:<user>/<repo>.git`
- **QNAP / 低性能设备**：瓶颈通常是 `index-pack` 而非网络。fetch 收到数据后可能卡 5-10 分钟解包对象。降低压缩开销可加速：
  ```bash
  git config http.version HTTP/1.1      # HTTP/2 在弱设备上多路复用可能更慢
  git config http.postBuffer 524288000   # 增大 buffer 减少分块
  git config core.compression 0          # 关闭传输压缩，省 CPU
  git config pack.windowMemory 16m       # 限制 delta 搜索窗口
  git config pack.packSizeLimit 16m      # 限制单包大小
  ```
  操作完成后记得 `--unset` 这些临时配置。若 fetch 多次中断留下 `tmp_pack_*` 残留文件，下次 fetch 会更慢——清理 `rm .git/objects/pack/tmp_pack_*`。
- **`index.lock` / `shallow.lock` 残留**：除 `index.lock` 外，`--depth` 浅克隆中断会在 `.git/` 留下 `shallow.lock`，清理命令：`rm -f .git/index.lock .git/shallow.lock`

- **提交 skills submodule 前检查未追踪的 scratch 测试文件是否硬编码了密钥**：`git-tool commit` 会扫描并提交 submodule 内所有改动，若误用 `add -A` 会把含硬编码 API Key 的临时文件（如 `memory-hub/scripts/zep_test.py`，内含真实 Zep Key）提交进 git 历史，密钥将永久泄露且无法通过删除文件清除。这类 `zep_test.py`/`*_test.py` 调试残留应直接删除而非提交；若只是临时验证工具，改用环境变量读取密钥。提交前对扫描到的未追踪文件先 `cat` 检查是否含 `sk-`/`z_`/`key=` 等敏感串。

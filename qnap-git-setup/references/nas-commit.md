# NAS Git 提交 / 更新（GitHub）

记录在 QNAP NAS 上向 GitHub 提交代码的系统属性与正确做法。

## 系统属性

### 1. NAS 无全局 git 身份，commit 会直接失败

本机没有 `~/.gitconfig`（`git config --global --list` 报 `unable to read config file`）。
直接 `git commit` 报 `unable to auto-detect email address`。两个解法：

| 方式 | 命令 |
|---|---|
| 一次性 | `git -c user.name=... -c user.email=... commit -m "..."` |
| 持久 | `git config --global user.name ... && git config --global user.email ...` |

身份值存 `~/.env`（见下），文档/skill 里只引用变量名，不写明文。

### 2. GitHub 认证走 SSH，HTTPS 无凭据

NAS 的 `~/.ssh/id_ed25519` 已绑定 GitHub（`ssh -T git@github.com` → `Hi slb1988!`）。
HTTPS remote（`https://github.com/...`）在本机没有 credential，`git ls-remote` / `git push`
报 `could not read Username`。

→ remote 必须用 **SSH 形式** `git@github.com:USER/REPO.git`，而不是 HTTPS。

### 3. 提交身份应沿用仓库历史作者

同一仓库的 commit author 应与历史一致（避免提交者分裂）。查历史身份：

```bash
git log -1 --format='%an <%ae>'
```

## 敏感信息存放约定

git 身份（name/email）、GitHub 用户名等敏感值放 **`~/.env`**，`chmod 600`，**不提交**。
md / skill 文档里只引用 `$GIT_USER_NAME` / `$GIT_USER_EMAIL` / `$GITHUB_USER` 变量名。

## 提交模板

```bash
cd /path/to/repo
source ~/.env   # 载入 GIT_USER_NAME / GIT_USER_EMAIL / GITHUB_USER

# remote 用 SSH（HTTPS 无凭据会失败）
git remote set-url origin git@github.com:${GITHUB_USER}/REPO.git

git add -A
git -c user.name="$GIT_USER_NAME" -c user.email="$GIT_USER_EMAIL" commit -m "..."
git push origin main
```

## 忽略规则

本地环境残留应进 `.gitignore`，不提交：

- `.venv.bak-macos` — macOS 虚拟环境备份
- `.idea/` — PyCharm/IDE 配置（默认模板里是注释掉的 `# .idea/`，需取消注释启用）

# 绑定已有仓库到 GitHub Remote

## 场景

本地已有 `.pi/skills` 等 git 仓库，需要关联到 GitHub 远程仓库。

## 设置 / 修改 Remote

```bash
cd /path/to/your/repo

# 查看当前 remote（可能已存在旧地址、或空）
git remote -v

# 设置 SSH remote（推荐）
git remote set-url origin git@github.com:USERNAME/REPO.git

# 如果是首次添加 remote
git remote add origin git@github.com:USERNAME/REPO.git
```

## 更新嵌套 submodule 的 remote

如果仓库包含从别人 fork 来的 submodule（如 `.gitmodules` 中 URL 指向原作者），需要给每个 submodule 也更新 remote：

```bash
cd /path/to/your/repo

# 逐个更新
git submodule foreach 'git remote set-url origin git@github.com:YOUR_USERNAME/$(basename $sm_path).git'

# 或者手动进入每个 submodule 修改
cd submodule-name
git remote set-url origin git@github.com:YOUR_USERNAME/submodule-name.git
```

**注意**：submodule 的 URL 修改后，主仓库的 `.gitmodules` 文件不会自动更新。如需永久修改，手动编辑：

```ini
# .gitmodules
[submodule "submodule-name"]
    path = submodule-name
    url = git@github.com:YOUR_USERNAME/submodule-name.git   # 从 https 改为 SSH
```

然后提交：
```bash
git add .gitmodules
git commit -m "update: switch submodule URLs to SSH"
```

## 首次推送

如果 GitHub 上的仓库是空的（没有初始 commit），首次推送：

```bash
git push -u origin main
```

如果 GitHub 上有 README / LICENSE 等初始化文件（与本地冲突），先拉取合并：

```bash
git pull origin main --allow-unrelated-histories
# 解决冲突后
git push origin main
```

## 测试完整流程

```bash
cd /path/to/your/repo

# 1. 确认 SSH agent 有 key
ssh-add -l

# 2. 测试 SSH 连接
ssh -T git@github.com

# 3. 确认 remote
git remote -v

# 4. 拉取
git fetch origin --verbose

# 5. 查看状态
git status
git log --oneline -3
```

预期：fetch 成功、status 显示分支与 origin 同步。

## 常见问题

### remote origin already exists

```
error: remote origin already exists.
```

**解决**：用 `set-url` 代替 `add`：

```bash
git remote set-url origin git@github.com:USERNAME/REPO.git
```

### 想同时保留 HTTPS 和 SSH remote

可以添加多个 remote：

```bash
git remote add origin-ssh git@github.com:USERNAME/REPO.git
git remote add origin-https https://github.com/USERNAME/REPO.git
```

根据需要选择：
```bash
git fetch origin-ssh
git fetch origin-https
```

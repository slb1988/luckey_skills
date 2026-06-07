# 冲突解决参考

## 主库 pull --rebase 冲突

```bash
git status                  # 查看冲突文件
# 手动编辑，解决 <<<< ==== >>>> 标记
git add <冲突文件>
git rebase --continue       # 或 git rebase --abort 放弃
```

## submodule --remote --merge 冲突

```bash
cd <repo_root>/<submodule路径>
git status
git add <冲突文件>
git merge --continue
```

## 常见 pull 失败原因

| 错误关键词 | 原因 | 手动解决 |
|-----------|------|---------| 
| `CONFLICT` / `conflict` | rebase 冲突 | 见上方「rebase 冲突」 |
| `rejected` | 本地有远端没有的 commit | `git push` 先推送，或 `git pull --no-rebase` |
| `no such remote` | remote 未配置 | `git remote add origin <url>` |
| `Authentication failed` | 认证失败 | 检查 SSH key 或 token |

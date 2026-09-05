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

## `<memory>` 块 / 索引行同位置追加的冲突形态（auto-skill 高频复发）

多台机器的 auto-skill 都会往 SKILL.md 同一锚点追加 `<memory>` 块、往 `.team/*/memory.md` 同一位置追加索引行，stash pop / merge 时冲突形态固定：

- **共享闭合标签**：双方各插一个 `<memory>` 块时，冲突区里两块常共用一个 `</memory>`（git 把相邻相同行当上下文）。不能简单「两边都留」——必须拆成两个各自带完整 `<memory ...>`/`</memory>` 的独立块，否则 XML 畸形。（2026-08 实测 find-skills/SKILL.md）
- **索引行冲突**：`.team/*/memory.md` 双方各加一行索引 → 两行都保留即可。
- **语义有张力时先验证再合并**：两块结论看似矛盾时不要二选一——先在目标机器实测，确认互补后两块都留并加桥接说明（实例见 find-skills/SKILL.md 中 -g 安装位置 vs `~/.agents/skills` symlink 传播的两块）。

## 常见 pull 失败原因

| 错误关键词 | 原因 | 手动解决 |
|-----------|------|---------| 
| `CONFLICT` / `conflict` | rebase 冲突 | 见上方「rebase 冲突」 |
| `rejected` | 本地有远端没有的 commit | `git push` 先推送，或 `git pull --no-rebase` |
| `no such remote` | remote 未配置 | `git remote add origin <url>` |
| `Authentication failed` | 认证失败 | 检查 SSH key 或 token |

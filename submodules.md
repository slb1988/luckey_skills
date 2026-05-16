# Git Submodules 管理记录

## 已添加的子模块

| 路径 | 仓库 |
|------|------|
| `axton-obsidian-visual-skills` | https://github.com/axtonliu/axton-obsidian-visual-skills.git |
| `notebooklm-py` | https://github.com/teng-lin/notebooklm-py.git |
| `huashu-design` | https://github.com/alchaincyf/huashu-design.git |
| `diagram-design` | https://github.com/cathrynlavery/diagram-design.git |
| `frontend-slides` | https://github.com/zarazhangrui/frontend-slides.git |
| `ai-morning-brief` | https://github.com/EA-Studio-SHARK/ai-morning-brief |

## 添加子模块

```bash
git submodule add <仓库URL> <本地路径>
# 示例：
git submodule add https://github.com/alchaincyf/huashu-design.git huashu-design
```

执行后会自动：
1. 克隆仓库到指定路径
2. 在 `.gitmodules` 中追加配置
3. 将子模块目录作为一个 commit 指针暂存

## 克隆含子模块的仓库

```bash
# 方式一：克隆时一并初始化
git clone --recurse-submodules <仓库URL>

# 方式二：克隆后补充初始化
git clone <仓库URL>
git submodule update --init --recursive
```

## 更新子模块到最新 commit

```bash
# 更新所有子模块
git submodule update --remote --merge

# 更新单个子模块
git submodule update --remote --merge huashu-design
```

## 提交子模块变更

子模块本身的 commit 指针变化需要在父仓库中单独提交：

```bash
git add .gitmodules huashu-design
git commit -m "add huashu-design submodule"
```

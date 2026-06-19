---
name: write-article
description: 写公众号文章并发布到微信公众号。触发场景：(1) 用户说"帮我写一篇关于 XX 的文章"、"把这个整理成文章"、"写篇公众号"；(2) 用户指向某个文件/工具/使用记录/会话内容，说"整理成博文/文章/分享出去"。即使用户只说"发个文章"或"写篇分享"也应触发。输出统一放在 writing/ 目录下，生成封面，并自动发布到微信公众号草稿箱。
---

# write-article

从话题或已有素材出发，写一篇中文公众号风格博文，生成封面，然后发布到微信公众号草稿箱。

## 工作目录约定

```
writing/
└── YYYYMMDD-关键词/          # 今天日期 + 话题关键词（2-4个汉字或英文）
    ├── 公众号文章_标题关键词.md  # 文章正文
    └── imgs/
        └── cover.png         # 封面图 1800×766
```

- 日期取今天（从 currentDate context 读取）
- 目录关键词：话题的最短中文缩写，如 `oss图床`、`每日晨报`
- 文章文件名：`公众号文章_` + 标题核心词（不含标点）

## 完整流程

### 第一步：写文章

**如果用户给了素材**（文件路径、会话内容、工具 SKILL.md 等）：
- 先读取素材，理解核心内容
- 从读者视角提炼"这对我有什么用/为什么有趣"

**文章结构**：

```markdown
---
title: "文章标题"
description: "一句话摘要，120字以内，说清楚文章价值"
author: Luckey
coverImage: imgs/cover.png
---

# 文章标题

---

## 一、章节名

正文...

## 二、章节名

正文...

（通常 4-6 个章节，最后一章收尾点题）
```

**写作风格**：
- 中文，口语化，有温度，不堆术语
- H2 用中文序号（一、二、三...）
- 代码块用真实可运行的命令，不造假路径
- 无需"总结"节，最后一章自然收尾即可
- 不加 emoji，不加多余的加粗

### 第二步：生成封面

调用封面生成脚本，把文章标题叠加到背景图上：

```bash
bun /path/to/write-article/scripts/generate-cover.ts \
  --title "文章标题" \
  --output writing/YYYYMMDD-关键词/imgs/cover.png \
  --bg writing/common-bgs/background-1.png
```

- 背景图从 `writing/common-bgs/` 随机选一张
- 封面尺寸：1800×766
- 脚本用 Chrome headless 渲染 HTML 模板后截图，原始背景图不做任何修改

如果脚本报错，检查 Chrome 路径；如果 `common-bgs/` 为空，提示用户先放一张背景图进去。

### 第三步：发布到微信

文章和封面都就绪后，调用 post-to-wechat skill 的 API 方法：

```bash
bun /path/to/post-to-wechat/scripts/wechat-api.ts \
  writing/YYYYMMDD-关键词/公众号文章_XXX.md \
  --theme default \
  --author Luckey \
  --cover writing/YYYYMMDD-关键词/imgs/cover.png
```

发布成功后告知用户 media_id，并提示去草稿箱确认。

## 脚本路径

- `scripts/generate-cover.ts` — 封面生成脚本
- `assets/cover-template.html` — 封面 HTML 模板
- post-to-wechat skill 路径：`.claude/skills/post-to-wechat/`

## 注意事项

- `writing/common-bgs/` 里的背景图不要修改或删除
- 发布前确认封面图片文件存在，避免微信 API 报错
- 如果用户希望先审阅文章再发布，写完后停下来让他看，确认后再继续生成封面和发布

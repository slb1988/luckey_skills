# Article Posting (文章发表)

Post markdown articles to WeChat Official Account with full formatting support.

## Cover Image Generation from HTML

封面图通常由 `imgs/cover_design.html` 生成，包含两类元素：

- **Canvas 层**：背景、流程图、方块等纯绘图内容
- **HTML 覆盖层**：标题、tag、subtitle 等 DOM 文字元素（`position: absolute` 叠在 canvas 上）

**正确的截图方式**：必须用浏览器截图（含 HTML 层），不能只 export canvas。

```
Chrome DevTools emulate viewport 900x383x2   ← deviceScaleFactor=2
→ 截图输出 1800×766 PNG，HTML 和 canvas 全部包含，字体清晰
```

直接 `canvas.toDataURL()` 只拿到 canvas 部分，HTML 文字层会丢失。

**HiDPI 渲染**：canvas 元素需设为物理 2x 尺寸并 scale context，否则截图发虚：

```html
<canvas id="c" width="1800" height="766" style="width:900px;height:383px"></canvas>
<script>
const ctx = c.getContext('2d');
ctx.scale(2, 2);  // 所有绘制坐标仍用逻辑尺寸（900×383）
const W = 900, H = 383;
</script>
```

## Usage

```bash
# Post markdown article
${BUN_X} ./scripts/wechat-article.ts --markdown article.md

# With theme
${BUN_X} ./scripts/wechat-article.ts --markdown article.md --theme grace

# Disable bottom citations for ordinary external links
${BUN_X} ./scripts/wechat-article.ts --markdown article.md --no-cite

# With explicit options
${BUN_X} ./scripts/wechat-article.ts --markdown article.md --author "作者名" --summary "摘要"
```

## Parameters

| Parameter | Description |
|-----------|-------------|
| `--markdown <path>` | Markdown file to convert and post |
| `--theme <name>` | Theme: default, grace, simple, modern |
| `--no-cite` | Keep ordinary external links inline instead of converting them to bottom citations |
| `--title <text>` | Override title (auto-extracted from markdown) |
| `--author <name>` | Author name |
| `--summary <text>` | Article summary |
| `--html <path>` | Pre-rendered HTML file (alternative to markdown) |
| `--profile <dir>` | Chrome profile directory |

## Markdown Format

```markdown
---
title: Article Title
author: Author Name
---

# Title (becomes article title)

Regular paragraph with **bold** and *italic*.

## Section Header

![Image description](./image.png)

- List item 1
- List item 2

> Blockquote text

[Link text](https://example.com)
```

Markdown mode converts ordinary external links into bottom citations by default for WeChat-friendly output. Use `--no-cite` to disable that behavior.

## Image Handling

1. **Parse**: Images in markdown are replaced with `WECHATIMGPH_N`
2. **Render**: HTML is generated with placeholders in text
3. **Paste**: HTML content is pasted into WeChat editor
4. **Replace**: For each placeholder:
   - Find and select the placeholder text
   - Scroll into view
   - Press Backspace to delete the placeholder
   - Paste the image from clipboard

## Scripts

| Script | Purpose |
|--------|---------|
| `wechat-article.ts` | Main article publishing script |
| `md-to-wechat.ts` | Markdown to HTML with placeholders |
| `md/render.ts` | Markdown rendering with themes |

## Example Session

```
User: /post-to-wechat --markdown ./article.md

Claude:
1. Parses markdown, finds 5 images
2. Generates HTML with placeholders
3. Opens Chrome, navigates to WeChat editor
4. Pastes HTML content
5. For each image:
   - Selects WECHATIMGPH_1
   - Scrolls into view
   - Presses Backspace to delete
   - Pastes image
6. Reports: "Article composed with 5 images."
```

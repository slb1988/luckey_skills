---
name: video-downloader
description: 下载网络视频（单个或批量），支持 B站（bilibili）和 YouTube/油管。当用户提到下载视频、下载B站/bilibili/YouTube/油管/抖音内容、下载空间/收藏夹/合集/播放列表/频道、使用 you-get 或 yt-dlp 下载、批量下载等场景时触发。即使用户只说"帮我把这个视频存下来"或"把这个合集都下了"，也应该考虑使用此 Skill。
---

## 支持的平台

| 平台 | 工具 | 参考文档 |
|------|------|----------|
| B站（bilibili） | you-get | `references/bilibili.md` |
| YouTube / 油管 | yt-dlp | `references/youtube.md` |

---

## 通用工作流

1. **确认平台** — 根据 URL 或用户描述判断平台
2. **读取对应 reference** — 按上表找到详细操作说明
3. **确认 cookies** — 文件位于 `config/<platform>_cookies.txt`，若为空模板请先填入
4. **执行下载** — 单个视频直接用工具命令；批量下载生成 for 循环或列表
5. **已存在自动跳过** — you-get 重复下载会覆盖；yt-dlp 用 `--download-archive` 跳过

---

## Cookies 认证

登录状态通过 cookies 文件传给下载工具，文件路径：

- B站：`config/bilibili_cookies.txt`
- YouTube：`config/youtube_cookies.txt`

首次使用时，复制对应的 `.template` 文件并填入真实 cookies：

```bash
cp config/bilibili_cookies.txt.template config/bilibili_cookies.txt
# 然后编辑 config/bilibili_cookies.txt，填入真实 cookies
```

这两个文件已在 `.gitignore` 中，不会被提交。

**cookies 格式**：工具需要 Netscape cookies.txt 格式，浏览器插件导出的 JSON 格式需先转换。
转换规则：`<domain> <hostOnly反转为TRUE/FALSE> <path> <secure> <expirationDate取整> <name> <value>`
session cookie（无 expirationDate）填 0。

---

## 注意事项

- 运行前检查对应 cookies 文件是否已填写真实内容（非空模板）
- 下载目录默认为当前工作目录，建议 cd 到目标目录后再运行
- you-get 依赖 Python，安装后若 shebang 指向旧版 Python 会报 bad interpreter，用 `pip3 install you-get` 重装修复

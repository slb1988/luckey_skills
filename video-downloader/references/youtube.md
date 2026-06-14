# YouTube / 油管视频下载

## 依赖

```bash
pip install yt-dlp
# 或
brew install yt-dlp
```

验证安装：`yt-dlp --version`（建议定期更新：`yt-dlp -U`）

---

## 支持的页面类型

| 类型 | URL 示例 |
|------|----------|
| 单个视频 | `youtube.com/watch?v=xxxxx` |
| 播放列表 | `youtube.com/playlist?list=PLxxxxx` |
| 频道全部视频 | `youtube.com/@ChannelName/videos` |
| 频道 + 直播回放 | `youtube.com/@ChannelName` |

---

## Cookies 认证

**方式一（推荐）：自动从浏览器读取**

```bash
yt-dlp --cookies-from-browser chrome <URL>
# 也支持 firefox / safari / edge / chromium
```

**方式二：使用 cookies 文件**

先将 cookies 导出到 `assets/youtube_cookies.txt`（参考文件内说明），然后：

```bash
yt-dlp --cookies assets/youtube_cookies.txt <URL>
```

---

## 常用下载命令

```bash
# 下载单个视频（最高画质）
yt-dlp --cookies-from-browser chrome "https://youtube.com/watch?v=VIDEO_ID"

# 下载播放列表
yt-dlp --cookies-from-browser chrome "https://youtube.com/playlist?list=PLAYLIST_ID"

# 下载频道所有视频
yt-dlp --cookies-from-browser chrome "https://youtube.com/@ChannelName/videos"

# 跳过已下载（断点续传）
yt-dlp --download-archive downloaded.txt --cookies-from-browser chrome <URL>

# 指定格式：最高画质视频 + 最高质量音频，合并为 mp4
yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]" \
  --merge-output-format mp4 \
  --cookies-from-browser chrome <URL>

# 仅下载音频（mp3）
yt-dlp -x --audio-format mp3 --cookies-from-browser chrome <URL>

# 自定义文件名格式
yt-dlp -o "%(upload_date)s_%(title)s.%(ext)s" --cookies-from-browser chrome <URL>
```

---

## 批量下载（URL 列表文件）

将多个 URL 写入文件，每行一个：

```bash
cat urls.txt
# https://youtube.com/watch?v=AAA
# https://youtube.com/watch?v=BBB
# https://youtube.com/playlist?list=CCC

yt-dlp --cookies-from-browser chrome -a urls.txt
```

---

## 常见问题

1. **403 / Bot 检测**：换用 `--cookies-from-browser` 而非 cookies 文件，或更新 yt-dlp：`yt-dlp -U`

2. **视频限制地区**：配合代理使用：`yt-dlp --proxy socks5://127.0.0.1:1080 <URL>`

3. **字幕下载**：`--write-subs --sub-langs zh-Hans,en` 同时下载中英文字幕

4. **查看可用格式**：`yt-dlp -F <URL>` 列出所有画质选项，再用 `-f <format_id>` 指定

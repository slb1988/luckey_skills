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

## ffmpeg — 视频音频合并必需

yt-dlp 下载最高画质时会分别拉取视频流和音频流，合并需要 ffmpeg。**没有 ffmpeg 则输出两个独立文件**（`.f400.mp4` 纯视频 + `.f140.m4a` 纯音频），而不是完整 mp4。

### 检测是否已安装

```bash
ffmpeg -version
```

### Windows 安装（winget）

```bash
winget install --id Gyan.FFmpeg --source winget
```

> 必须用精确 ID，否则 `winget install ffmpeg` 会返回多个候选包。

### PATH 刷新问题

winget 安装后当前 shell 不会自动更新 PATH。解决方案：

**方案 A**：重启终端后再运行 yt-dlp（推荐）

**方案 B**：当场找到完整路径直接调用：

```bash
FFMPEG=$(find /c/Users/admin/AppData/Local/Microsoft/WinGet/Packages -name "ffmpeg.exe" 2>/dev/null | head -1)
"$FFMPEG" -version
```

典型路径模式：
```
/c/Users/<user>/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-<version>-full_build/bin/ffmpeg.exe
```

### 手动合并（备用）

若 yt-dlp 已产出两个分离文件，用 `-c copy` 合并（无重编码，速度极快）：

```bash
ffmpeg -i video.f400.mp4 -i audio.f140.m4a -c copy output.mp4 -y
```

---

## 注意事项

- 运行前检查对应 cookies 文件是否已填写真实内容（非空模板）
- 下载目录默认为当前工作目录，建议 cd 到目标目录后再运行
- you-get 依赖 Python，安装后若 shebang 指向旧版 Python 会报 bad interpreter，用 `pip3 install you-get` 重装修复

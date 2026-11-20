---
name: music-downloader
title: 音乐下载器（默认中文儿歌 → NAS SongLoft 曲库）
description: 下载歌曲为 MP3 并落盘 NAS SongLoft 曲库，默认场景是主流中文儿童歌曲。当用户提到下载儿歌/儿童歌曲/歌曲 MP3、补歌、扩充歌单、往 NAS/歌库/小爱音箱曲库加歌、SongLoft 曲库、或说「下载 XX 这首歌」「来几首主流儿歌」时触发；即使用户只说歌名让"下下来"也应使用本 Skill。儿歌之外的其他歌曲下载同样走本流程，仅落盘子目录不同。视频下载（B站/YouTube 视频本体）走 video-downloader skill，不要用本 Skill。
tags: [music, mp3, 儿歌, 儿童歌曲, youtube, yt-dlp, nas, songloft, xiaomusic, 小爱音箱]
argument-hint: "[歌名或歌单描述]"
---

# Music Downloader

把歌曲下载为 MP3 放进 NAS SongLoft 曲库，小爱音箱/StoryIn/Loft 生态直接可播。默认下载主流中文儿歌。

## 铁律：落盘路径

**目标目录：NAS 内网映射 `/Volumes/Container/songloft/music/<分类>/`**，儿歌用 `中文儿歌`。

- 下载前**先检查目录存在**；不存在（NAS 未挂载）→ **报错中断**，禁止回退到本地路径（用户明确要求）
- 同名文件已存在 → 跳过，不覆盖（NAS 上可能已有更高质量版本）
- 不要写入 `~/Music/XiaoMusic/` 本地目录（2026-11 已废弃，全部迁至 NAS）

## 下载工作流

1. 检查 NAS 目录：`ls /Volumes/Container/songloft/music/中文儿歌/`，失败则报错停止
2. 确定歌单：用户指定歌名直接用；「主流儿歌」这类泛化需求从 [references/song-catalog.md](references/song-catalog.md) 选 NAS 上还没有的
3. 逐首下载（命令细节和参数 why 见 [references/youtube-mp3.md](references/youtube-mp3.md)）：

```bash
yt-dlp "ytsearch10:<歌名> 儿歌" -x --audio-format mp3 --audio-quality 2 \
  --no-playlist --extractor-args "youtube:player_client=android,web" \
  --match-filter "duration > 40 & duration < 300" --max-downloads 1 \
  -o "/Volumes/Container/songloft/music/中文儿歌/<歌名>.%(ext)s"
```

4. **逐首落盘核验**：`ffprobe` 查时长，合理区间 60–300 秒、文件 >500KB；合集（>5 分钟）或时长异常要换搜索词重下
5. 汇总报告：列出每首时长；提醒 SongLoft 每 15 分钟自动扫描入库，xiaomusic 网页 192.168.50.81:58090 刷新可见

## 关键经验（细节都在 references）

- YouTube 必须加 `--extractor-args "youtube:player_client=android,web"`，否则报 "No supported JavaScript runtime" / "video not available"
- 必须加时长过滤；不过滤容易下到十几分钟的大合集（真实踩坑：搜「小毛驴」下到 19 分钟合集）
- 搜索用 `ytsearch10` 留足候选，配合 `--max-downloads 1` 取第一个符合时长过滤的
- hifi-download skill 的 Qobuz/TIDAL 无损渠道未配凭据，且中文儿歌覆盖差，不要走那条路

## 参考文件

| 文件 | 内容 | 何时读 |
|------|------|--------|
| [references/youtube-mp3.md](references/youtube-mp3.md) | yt-dlp 完整命令、参数解释、踩坑清单 | 命令报错或要调整质量/格式时 |
| [references/nas-library.md](references/nas-library.md) | NAS 曲库结构、入库机制、播放入口 | 建分类目录、查入库状态、排障时 |
| [references/song-catalog.md](references/song-catalog.md) | 主流中文儿歌清单（含已在库 31 首基线） | 用户要「主流儿歌」泛化下载时 |

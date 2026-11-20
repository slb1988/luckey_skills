# YouTube → MP3 下载细节

## 标准命令

```bash
yt-dlp "ytsearch10:<歌名> <类型词>" \
  -x --audio-format mp3 --audio-quality 2 \
  --no-playlist \
  --extractor-args "youtube:player_client=android,web" \
  --match-filter "duration > 40 & duration < 300" \
  --max-downloads 1 \
  -o "<目标目录>/<歌名>.%(ext)s"
```

类型词：儿歌场景用「儿歌」，流行歌曲用「official audio」或歌手名。

## 每个参数为什么存在

| 参数 | 原因 |
|------|------|
| `ytsearch10:` | 搜前 10 条候选，给时长过滤留余量；用 `ytsearch1` 时第一条是合集就直接失败 |
| `--extractor-args "youtube:player_client=android,web"` | **必须**。本机无 deno，默认 client 报 "No supported JavaScript runtime"，大量视频 "This video is not available"；android/web client 绕过 |
| `--match-filter "duration > 40 & duration < 300"` | 排除大合集（儿歌搜索高频坑：10–40 分钟串烧）和过短的预告/片段 |
| `--max-downloads 1` | 取第一个符合过滤条件的即停。**不要**用 `--break-match-filter`——它本身要吃一个 FILTER 参数，会把后面的 `-o` 吞掉报错 |
| `--audio-quality 2` | VBR ~190kbps，儿歌足够；要更高用 0 |
| `--no-playlist` | 防止搜索命中 playlist 时整个列表都下下来 |

## 踩坑清单

1. **合集陷阱**：「小毛驴 儿歌」首条结果是 19 分钟合集。现象：下载后 ffprobe 时长远超正常。对策：时长过滤 + 落盘后逐首核验时长
2. **搜「完整版」反而更容易命中合集**；正常搜「歌名+儿歌」配时长过滤即可
3. **断代旧文件**：早期库内可能有 10–20 秒的试听片段（如旧版「两只老虎」175K），文件大小 <500KB 是可疑信号
4. 批量下载用 shell for 循环，逐首 `ffprobe -v error -show_entries format=duration -of csv=p=0` 核验后再报告

## 依赖

- `yt-dlp`（miniconda，2026-10 版本实测可用）
- `ffmpeg` + `ffprobe`（/opt/homebrew/bin）
- 无需 cookies、无需 JS runtime

## 不适用场景

- 无损/Hi-Res（FLAC）：走 hifi-download skill（需先配 Qobuz/TIDAL 凭据，且中文儿歌覆盖差）
- 视频本体下载：走 video-downloader skill

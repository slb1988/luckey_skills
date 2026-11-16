---
name: book-downloader
description: 搜索并下载电子书（技术/效率类为主）。后端：Z-Library EAPI（书库最大含中文）、libgen（免账号）、Anna's Archive fast_download API。触发词：找书/搜书/下载书籍/爬书, "download book", "find the PDF/EPUB of"。
---

# Book Downloader

统一入口脚本：`scripts/bookdl.py`（全部 JSON 输出到 stdout，错误 JSON 走 stderr 非 0 退出）。

## 后端选择（2026-11-15 Mac 实测）

| 后端 | 认证 | 适用 | 现状与限制 |
|------|------|------|-----------|
| `zlib` | 邮箱+密码 | **默认首选**，书库最大、中文书全 | EAPI 可达；免费账号每日有下载额度（`quota` 子命令查） |
| `libgen` | 无需账号 | 英文技术书；免配置兜底 | 搜索走 libgen.com.de（服务端渲染可 curl）；**后端集群经常临时 503/500，脚本已内置 3 轮重试**，失败稍后再试；中文书覆盖弱（中文关键词常 0 结果） |
| `annas` | 捐赠会员 key | 下载加速 | **仅下载**。搜索页有 JS 反爬不可用，但 `fast_download.json` 是纯 JSON API 无挑战；**md5 与 libgen 互通**——libgen 搜到的 md5 可直接交给 annas 下载 |

域名腐化是常态（libgen.la 已死、annas-archive.li 变 parked），脚本对三端都做了域名 failover + 可用域名缓存（`~/.config/book-downloader/config.json`）。Anna's 镜像用 fast_download API 探活以防 parked 域名假冒。

## 快速用法

```bash
B=~/.claude/skills/book-downloader/scripts/bookdl.py
python3 $B preflight                      # 环境自检（先用它确认哪个后端可用）
python3 $B search "书名 作者" [--source zlib|libgen] [--limit 5] [--lang chinese] [--ext pdf]
python3 $B download --source zlib --id <id> --hash <hash> [-o 目录]
python3 $B download --source libgen --md5 <md5> [--filename "书名"] [-o 目录]
python3 $B download --source annas --md5 <md5> [-o 目录]
python3 $B quota                          # zlib 今日剩余额度
```

凭据写入 `~/.config/book-downloader/.env`（脚本不存在时给出一行模板；绝不打印/回显密码）：
```
ZLIB_EMAIL=...
ZLIB_PASSWORD=...
ANNAS_SECRET_KEY=...   # 可选
```

## 工作流程纪律

1. **先 preflight**，按报告选可用后端；`search --source auto` 顺序 zlib → libgen。
2. 搜索结果以编号表格（n 字段）呈现，用户说"下载第 N 本"时用对应的 id/hash 或 md5，不要重复搜索。
3. **版本鉴别**：同一本书常有多个记录，区分正式版 vs Early Access/早期 release（如 DDIA 2026 正式版 vs 2017 [early release]）；默认取最新正式版，存疑时间用户。
4. **下载后核对**：用 pypdf 读 PDF 元数据 `/Title` `/Author` 与目标书目比对，不一致要报告。
5. **格式优先级**（用户未指定时）：pdf > epub > mobi > azw3 > djvu。
6. 用户指定收藏时归位到 `luckey/04_sources/books/`，并在该目录的 moc/书单笔记中登记（遵循 vault 现行规则）。

## 中文书 fallback

zlib 无凭据、libgen 中文 0 结果时：
- 中文**技术书**：查 GitHub 社区译本（实例：GuoYaxiang/craftinginterpreters_zh，按 book.json 章节顺序合并 md → HTML → Chrome headless 打印 PDF）。
- 中文大众书：提醒用户配 Z-Library 账号是唯一现实通道。

## 已知故障特征（勿误判为本机问题）

- libgen "Search servers are busy / Library mirrors did not respond" → 服务端繁忙，几分钟后重试。
- libgen 下载 "Upstream error: HTTP 500/503" → 存储集群宕机，只能等；换时段再试。
- Anna's 经 Clash 代理部分镜像 SSL 断连 → 属代理节点问题，脚本自动换镜像（.gl 已验证可用）。
- macOS Python SSL 证书错误 → `pip3 install certifi` + `SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")`；**禁止** `verify=False`。

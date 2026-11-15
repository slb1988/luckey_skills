---
name: book-downloader
title: Book Downloader（本机网络环境下的电子书下载）
description: 在本机受限网络下快速下载电子书（PDF/EPUB）。覆盖已验证的通道优先级：libgen.com.de 搜索接口、archive.org 开放下载回退、文件校验；以及 2026-11 实测的封锁事实（机场 SNI 黑名单、DNS 污染、shell 恒走代理）。当用户要求下载书籍、找书、要某本书的 PDF/EPUB，或提到 libgen、Library Genesis、Anna's Archive、annas-archive、Z-Library、zlibrary、archive.org 找书，或输入「下载 [pdf] 某书名」「找 epub」「download 某书名」时触发。网络排障只在本 skill 与 clash-verge skill 交叉处做最小验证，不做全量节点扫描。
tags: [book, download, pdf, epub, libgen, archive-org, annas-archive, z-library, ebook]
---

# Book Downloader

目标：用最少探测把书拿到手。本机的网络现实很特殊（恒走代理、DNS 污染、机场级 SNI 黑名单），按本 skill 的顺序走可以避免重复踩坑——2026-11-15 曾为找一本畅销书在死通道上浪费了大半小时，这些教训都固化在下面。

## 一句话流程

**libgen 搜索拿书目 → 先试 libgen 下载（5 秒内判生死）→ 不行立刻 archive.org → 校验文件。**

不要在一棵树上吊死：libgen 的文件后端有频繁故障史，单个通道最多给两次机会就换。

## 通道 1：libgen（书最全，但文件层可能故障）

搜索接口（服务端渲染，curl 直接可解析）：

```bash
curl -s "https://libgen.com.de/search.php?q=<关键词>" | grep -oE 'md5=[a-f0-9]{32}' | sort -u
```

- 用 `search.php?q=`；旧参数 `?req=` 只回 JS 空壳。
- 结果卡片含格式/大小（EPUB/PDF、MB 数），同书多条记录时优先体积大的（通常是 retail 版）。
- 下载判定：先 HEAD 一次 `download.php?md5=<md5>&action=get`——302 跳转说明文件层活着（跟进 Location 取文件）；503 就是文件后端故障，**直接放弃 libgen，转 archive.org**，不要重试循环。
- 注意 2026-11-15 起 `download.php` 的 302 指向 `libgen.la`，该站 origin 已空（回 nginx 默认页），即使 302 也要确认最终拿到的是二进制而不是 HTML。

## 通道 2：archive.org（开放副本，最可靠回退）

很多 2020 年代的畅销书在 archive.org 上有用户上传的开放副本（非借阅受限）。API 全程 curl 友好，国内直连可达：

```bash
# 1. 搜书目
curl -s "https://archive.org/advancedsearch.php?q=title:(<书名>)+AND+creator:(<作者>)&fl[]=identifier&fl[]=title&output=json"
# 2. 看文件列表（确认 access-restricted-item 不是 true，挑 .pdf/.epub）
curl -s "https://archive.org/metadata/<identifier>"
# 3. 下载（文件名要 URL-encode，大小与 metadata 一致即完整）
curl -sL "https://archive.org/download/<identifier>/<urlencoded文件名>" -o <本地名>
```

这条路线 2026-11-15 验证成功（《The 5 Types of Wealth》437 页 PDF + EPUB）。注意区分：metadata 里 `access-restricted-item: true` 的是借阅 DRM 版，不要下；没标记的是开放副本。

## 校验（每次必做，30 秒）

```bash
file -b <文件>                    # PDF document / EPUB document，不是 HTML
ls -la                            # 与 metadata 的 size 一致
unzip -l <epub> | head            # EPUB 专有：能看到 mimetype + content.opf
qlmanage -t -s 1200 <pdf> -o /tmp # PDF 专有：生成首页缩略图，Read 看图确认书目正确
```

下载到 `~/Downloads/`，文件名保留「书名 - 作者」原样。用户是 Obsidian 用户，若明确要求入库，再按 luckey 命名规则转小写 kebab-case 放 `luckey/04_sources/books/resources/`（先读 luckey/AGENTS.md）。

## 只有 EPUB 但用户要 PDF

本机有 calibre：`/Applications/calibre.app/Contents/MacOS/ebook-convert in.epub out.pdf`。转换质量对重排文本类书籍尚可，对图文混排较差——转换后务必按上面校验流程目视确认。

## 网络现实（每次会话只需记一遍）

- **shell 恒定注入 `http_proxy/https_proxy=127.0.0.1:7897`**（Clash Verge）：所有 curl 默认走机场。「直连测试」必须 `--noproxy '*'`。
- **DNS 被污染**：libgen/annas-archive 等域名本地解析到假地址 `198.10.x.x`。真直连要 DoH 拿真实 IP 再 `--resolve`：`curl -s -H "accept: application/dns-json" "https://cloudflare-dns.com/dns-query?name=<域名>&type=A"`。
- **机场级 SNI 黑名单（换节点无用，2026-11-15 全 20 节点实测）**：`annas-archive.org`（TLS 握手中断）、`library.lol`（CONNECT 后断连）。Anna's Archive 整体不可达，不要浪费时间；`r.jina.ai` 也解析不了它。
- 怀疑「站挂了还是墙了」：用 check-host.net 全球探测（API 直接 `curl -H "Accept: application/json" "https://check-host.net/check-http?host=<域名>"`），5 秒内出结论，避免盲目切节点。
- Clash Verge 的 API 用法（切节点等）见 **clash-verge** skill；本 skill 不重复。secret 从 Verge 的 config.yaml 读，不要硬编码。

## 已证死的通道（别再试）

| 通道 | 状态（2026-11-15） |
|------|------|
| libgen.la | origin 已空，全站 nginx 默认页 |
| libgen.li | 全站 503 |
| libgen.gs | 全球 DNS 已死 |
| libgen.is | 全球超时（check-host 确认） |
| libgen.ee | 静态镜像，搜索接口坏 |
| libgen.gl / libgen.mx / libgen.su | 停放 / 403 / 526 |
| libgenesis.net | 能过 CF 挑战但书库陈旧，搜不到 2025 新书 |
| z-library.sk | DiamWall JS 验证 + 下载需登录 |
| oceanofpdf / pdfdrive / idoc.pub / vdoc.pub | Cloudflare 403 / 不可达 / 域名停放 |
| Bing / mojeek / searx.be | 对本机 curl 反爬，返回垃圾结果或验证页 |

状态会过期：如果距上次验证超过一个月，对 libgen.com.de 做一次 5 秒 HEAD 探测重新确认，别盲信表格。

## 详细参考

- [references/channel-playbook.md](references/channel-playbook.md)——2026-11-15 完整排障记录：每个通道的确切报错、302/POST 行为细节、check-host 探测方法、Playwright 过 JS 挑战的最小脚本（当未来某个 JS 墙通道值得救时再用）。

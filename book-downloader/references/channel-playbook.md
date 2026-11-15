# Channel Playbook（2026-11-15 排障全记录）

本文件保留细节供按需查阅；日常下载按 SKILL.md 的主流程走即可。

## 目录

- [libgen 系各站的确切行为](#libgen-系各站的确切行为)
- [网络基础设施事实](#网络基础设施事实)
- [全球活性探测方法](#全球活性探测方法)
- [JS 挑战通道与 Playwright 后备方案](#js-挑战通道与-playwright-后备方案)
- [本次成功案例：The 5 Types of Wealth](#本次成功案例the-5-types-of-wealth)

## libgen 系各站的确切行为

### libgen.com.de（搜索主入口）

- 搜索：`GET /search.php?q=<词>` 服务端渲染，结果卡片含格式与大小；`book.php?md5=` 详情页；旧参数 `?req=` 只回 JS 空壳。
- 下载行为（2026-11-15）：
  - `GET /download.php?md5=<md5>` → **503**（nginx 错误页，重试 12+ 次、带 UA/cookie/Referer 均无效——文件后端故障，不是反爬）。
  - `GET /download.php?md5=<md5>&action=get` → **302** 到 `https://libgen.la/get.php?md5=...&key=<16位大写key>`（9MB 记录则跳 `libgen.la/ads.php`）。libgen.la 的 Cloudflare 后 origin 已空，回 nginx 默认页——死链。
  - `POST /download.php`（body: `md5=...&action=get`）→ **400 "Invalid MD5"**。POST 能穿透到 PHP（GET 反而 503），但 md5 校验不过，说明文件表与搜索表不同步。
- `get.php?md5=...&key=...` 直接打 com.de → 回首页（无效链接的兜底行为）。

### libgen.co.in（备用镜像）

- 库比 com.de 旧：搜不到 2025 年新书（"No results found"）。
- `GET /download.php?md5=` 返回中间页（表单 POST `md5`+`action=get`）；POST → **503 "Could not parse download key"**，带 cookie 会话也一样。文件层同样坏。

### libgen.li / libgen.is / libgen.gs / library.lol

- `libgen.li`：全站 503（首页即 503）。
- `libgen.is`：check-host 全球多点超时——站点自身问题，非本地封锁。
- `libgen.gs`：check-host 全球 DNS 解析失败——域名已死。
- `library.lol`：**全球 6 节点全 200 活着**，但机场所有节点（20 个实测）CONNECT 后断连。注意它只镜像 libgen.is 藏书，**不认 libgen.li 系的 md5**（拿 li 系 md5 去打会 404）。

### libgen.ee / libgen.gl / libgenesis.net

- `libgen.ee`：Apache 静态镜像，搜索表单 GET 到 `index_php.html` 但 query 被忽略——动态搜索实际坏掉。
- `libgen.gl`：nginx 默认页（域名被劫持/停放）。
- `libgenesis.net`：Cloudflare 挑战可用浏览器过（见下文 Playwright），过墙后是 Laravel 应用（搜索在 `/s/?q=`），但**书库陈旧**——"sahil bloom"、ISBN 均 0 结果。

## 网络基础设施事实

- **恒代理**：shell 环境变量 `http_proxy/https_proxy/all_proxy=127.0.0.1:7897` 一直存在，curl/git 默认全走机场。做「直连 vs 代理」对照实验时必须显式 `--noproxy '*'`。
- **DNS 污染**：libgen*/annas-archive*/library.lol 本地解析到 `198.10.x.x` 假地址。用 DoH 拿真实 IP（`cloudflare-dns.com/dns-query?name=<域>&type=A`，走代理可达）再 `curl --noproxy '*' --resolve <域>:443:<IP>` 可测试 GFW 是否只做了 DNS 污染还是 SNI 也封。实测 libgen.la 的 CF IP 直连 TCP/TLS 通（站死是 origin 问题）；library.lol 直连断（GFW SNI 封）。
- **机场 SNI 黑名单**：`annas-archive.org` 过任意节点都是 CONNECT 建立后 TLS 握手被 reset（`SSL_ERROR_SYSCALL`）；`library.lol` 是 CONNECT 后挂起超时。换节点（香港/台湾/日本/美国/新加坡/菲律宾/韩国/英国/德国/马来西亚共 20 个）全部一样——机场出口设备级过滤，换节点无意义。`annas-archive.se` 同样被断；`annas-archive.gs`/`annas-archive.li` 是域名停放页（假镜像，注意甄别：真 AA 不会跳 headlinelogic.com）。
- **r.jina.ai** 对 annas-archive.org 恒报 "could not be resolved"，指望不上。
- **搜索引擎反爬**（对本机 curl）：Bing 返回只匹配首个单词的垃圾结果；DDG lite 返回空结果页；mojeek、searx.be、priv.au、search.rhscz.eu 均有反爬页或 429。需要网页搜索时考虑带浏览器的方案。

## 全球活性探测方法

```bash
RID=$(curl -s -H "Accept: application/json" "https://check-host.net/check-http?host=<域名>&max_nodes=6" | python3 -c "import sys,json;print(json.load(sys.stdin)['request_id'])")
sleep 12
curl -s -H "Accept: application/json" "https://check-host.net/check-result/$RID"
```

全球节点 OK = 站活着、问题在本地链路；全球 FAIL = 站本身死了，别再折腾本地。这个区分能在 5 秒内砍掉一半排查方向。

## JS 挑战通道与 Playwright 后备方案

未来若出现「内容值得拿但挡 JS 墙」的通道（如 z-library 的 DiamWall、某 CF 站），本机已验证的方案：

- 已装 `playwright`（pip user 级，清华镜像装得快：`-i https://pypi.tuna.tsinghua.edu.cn/simple`）；**不需要** `playwright install` 下载浏览器——用 `channel="chrome"` 直接驱动已装的 Google Chrome。
- 关键参数：`launch_persistent_context(用户数据目录, channel="chrome", headless=False, args=["--disable-blink-features=AutomationControlled"], ignore_default_args=["--enable-automation"])`；页面跳转中读 content 会抛异常，要 try/except 重试。
- 局限：DiamWall 之后的 z-library **下载仍需账号登录**，本机没有凭据——此类通道对无登录资源的场景才有救。

## 本次成功案例：The 5 Types of Wealth

最终路径：archive.org identifier `the-5-types-of-wealth-sahil-bloom`，开放（非借阅受限）文件：

- `The 5 Types of Wealth - Sahil Bloom.pdf`（12,138,437 B，437 页扫描+OCR 文字层）
- `The 5 Types of Wealth - Sahil Bloom.epub`（1,479,474 B，重排版）

校验手法：`file -b` 看类型、`ls -la` 对 metadata size、`unzip -l` 验 EPUB 结构、`qlmanage -t -s 1200 <pdf> -o /tmp` 生成首页缩略图后用 Read 目视确认封面。`file` 报的页数（100）不可信，数 `/Type /Page` 对象（437）才准。扫描版 PDF 文字在不可见 OCR 层，直接 grep 文本流可能啥也提不出来——目视缩略图是最可靠的确认。

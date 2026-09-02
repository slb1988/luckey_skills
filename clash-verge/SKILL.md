---
name: clash-verge
description: Clash Verge Rev（mihomo 内核）代理客户端的使用、排障与规则定制参考。当用户提到 Clash、Clash Verge、mihomo、代理不通、代理端口、7897、翻墙、节点切换、ChatGPT/Codex/OpenAI 走代理、chatgpt 连不上、分流规则、订阅更新覆盖配置、Merge 合并配置时触发。即使用户只说"代理挂了"、"某某网站走代理打不开"、"帮我加个走代理的域名"、"换个节点"、"网速慢"、"网络卡"也应触发。
---

# Clash Verge Rev 运维参考

## 核心认知（排查前先建立这些心智模型）

1. **内核是 verge-mihomo**（Clash Meta 系），Verge 只是 GUI 壳。所有能力（规则、分组、API）都是 mihomo 的。
2. **订阅 yaml 会被更新覆盖**。直接改 `profiles/<id>.yaml` 的改动在订阅刷新后丢失；长期方案用 Verge 的「Merge（合并）」处理（`prepend-rules` / `prepend-proxy-groups`），每次更新自动重新注入。临时改动先备份 `.bak`。
3. **端口以 Verge 设置为准，不以 profile yaml 为准**。Verge 会覆盖 profile 里的 `port`/`mixed-port`；默认 mixed 端口 7897。看到 yaml 里写 7890 但实际监听 7897 是正常现象，不是配置错误。
4. **核心实际加载的是合并生成的运行时配置**（应用数据目录下的 `clash-verge.yaml`），排查时看它而不是看订阅 profile。
5. **控制 API 走本机 IPC，不一定有 TCP 端口**。以运行时配置里的 `external-controller` / `external-controller-pipe` / `external-controller-unix` / `secret` 字段为准。
6. **运行模式（Rule/Global）是运行时状态**。profile yaml 里的 `mode:` 只是初始值，GUI 切换只改运行时；排查时以 `GET /configs` 返回的 mode 为准，不要看 yaml 猜。

## 系统相关细节

路径、IPC 方式、排查命令因系统而异，按需阅读：

- Windows：[references/windows.md](references/windows.md)
- macOS：[references/mac.md](references/mac.md)

## 「通过代理访问 X 不通」的标准排障流程

不要先改配置，按顺序定位：

1. **端口在听吗** — 查 mixed 端口监听状态和 verge-mihomo 进程是否存在。
2. **对照测试** — 通过代理 curl 目标域名，同时 curl 对照组（google.com、baidu.com）：
   - 全不通 → 核心/端口/系统代理问题；
   - 只有特定域名不通 → 分流规则或节点出口问题，继续往下。
3. **看出口 IP**：`curl -x http://127.0.0.1:<mixed端口> http://ipinfo.io/json`，看 `country` 和 `org`（ASN）。**数据中心/hosting ASN 很容易被 OpenAI、流媒体等服务封锁**。
4. **查/换节点** — 用 mihomo API 查相关分组当前选中节点（`GET /proxies/<分组>` 看 `now`），`PUT /proxies/<分组>` 切候选节点后重测。批量测活用 `GET /proxies/<节点>/delay`。
5. **确认修复后提醒持久化** — 运行时 API 切节点只存在核心里；订阅刷新会覆盖自定义规则。该写 Merge 的写 Merge。

### OpenAI 封锁节点 IP 的标志性表现

CONNECT 隧道返回 200 之后 TLS 握手挂起、直到超时（curl 输出 `000`）。**这不是客户端问题，是节点出口 IP 被 OpenAI 封了**，换节点即可，不要折腾客户端配置。

对照组判读（curl 直连结果）：

| 现象 | 含义 |
|---|---|
| chatgpt.com 返回 403 | Cloudflare 人机验证，**正常**（浏览器能过） |
| api.openai.com 返回 401 | 缺 API key，**正常**（说明网络已连通） |
| 两者都 000 超时 | 节点 IP 被封，换节点 |
| cloudflare.com 也超时 | 节点到 Cloudflare 整体不通，换节点或换线路 |

## 「网速慢」先别动 Clash：分层定位 + 跨网拥塞

<memory category="troubleshooting">
用户抱怨网速慢时，先 `route get <目标IP>` 确认走 en0（直连）还是 utun（代理）——本机国内流量默认直连，慢不一定是 Clash 的锅。本机是电信宽带，晚高峰跨运营商互联口拥塞是实测过的常见根因，本地无法修复，确认后直接告诉用户等高峰过，不要折腾本地配置。
</memory>

本机健康基线（电信宽带，网关 192.168.50.1）：ping 网关 ~3ms、ping 阿里DNS 223.5.5.5 ~9ms。分层定位，哪段炸了定位到哪：

1. ping 网关 → 排除 WiFi/路由器
2. ping 223.5.5.5 → 排除宽带出口
3. ping 目标域名**解析出的每个 IP**（`dig +short <域名>`）——同域名不同运营商节点差异巨大（实测电信宽带上 baidu.com 的移动节点 89ms/67% 丢包 vs 另一节点 33ms/0% 丢包）
4. traceroute 找拥塞跳：**202.97.x.x = 电信骨干，221.183.x.x = 移动骨干**；延迟在跨入对方骨干那一跳飙升 = 跨运营商互联口拥塞（晚高峰 21-23 点高发，深夜自愈）

临时缓解只有清 DNS 缓存碰运气换解析节点：`sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder`（治标不治本）。

## ChatGPT / Codex / OpenAI 强制走代理的域名清单

加规则（直接改 profile 或 Merge 的 `prepend-rules`）时用 `DOMAIN-SUFFIX` 指向代理分组。完整清单按用途分组：

```
# 主站与 API（Codex CLI 登录/调用也走这些）
openai.com  chatgpt.com  chat.com  sora.com
# 静态资源与用户内容
oaistatic.com  oaiusercontent.com
# 旧版/移动端 API 边缘节点
openaiapi-site.azureedge.net
openaicom-api-bdcpf8c6d2e9atf6.z01.azurefd.net   # 这条用 DOMAIN 精确匹配
# 登录与人机验证（缺了会卡在登录/验证码）
arkoselabs.com  arkoselabs.io  challenges.cloudflare.com  cdn.auth0.com
# Statsig 特性开关（ChatGPT/Codex 客户端会请求）
featuregates.org  featureassets.org  prodregistryv2.org
# 帮助中心客服组件
intercom.io  intercomcdn.com
```

**建议给 OpenAI 建独立 select 分组，不要直接指主代理分组**：OpenAI 封香港 IP，主分组一旦被切到香港节点就全灭；独立分组可以固定到美国/日本节点，不受日常切换影响。

## Global 模式的两个铁律

用户常年 Global 模式时必须记住：

1. **Global 模式忽略所有 rules**——包括 profile 里自带的 `IP-CIDR,10.0.0.0/8,DIRECT`。所有流量进 GLOBAL 分组。想让某个网段「任何模式下都不走代理」，加规则没用，要用网络层的方案：
   - **TUN 流量**：配置 `tun.route-exclude-address`（如 `10.77.77.0/24`），该网段不进 TUN 网卡，与模式无关。写到全局 `Merge.yaml` 里持久化（对订阅更新和切 profile 都免疫）。
   - **显式走 mixed 端口的流量**（如 Codex CLI 的 HTTP_PROXY 环境变量）：Global 模式下核心层面无解，只能在应用侧设置 `NO_PROXY`（列具体 IP 最保险，CIDR 写法各语言库支持不一）。
2. **TUN 路由改动热重载不生效**：`PUT /configs` 重载后配置里能看到 route-exclude-address，但 Windows 路由表不重建，必须 `POST /restart` 重启核心（API 见下）。注意重启会断现有连接几秒。

补充排查技巧：TUN 的 auto-route 不是两条 /1 了事，而是按排除范围**二分出整棵 CIDR 路由树**（排除的网段在树上留「洞」），路由全挂 metric 0——**同前缀下 metric 0 会赢过本机已连接的物理路由**。所以「明明是直连内网段却被代理」先看路由表（Windows: `route print -4 | findstr <网段>`），看到这种二分树模式就是 TUN 劫的。

## mihomo 控制 API 速查

连接方式（管道/socket/TCP）见对应系统的 references。认证头：`Authorization: Bearer <secret>`（secret 在运行时配置里，Verge 常见默认值是 `set-your-secret`）。

- `GET /version` — 验证 API 连通
- `GET /proxies/<分组名>` — 响应里 `now` 字段是当前选中节点，`all` 是候选列表
- `PUT /proxies/<分组名>`，body `{"name":"<节点名>"}` — 切换节点
- `GET /proxies/<节点名>/delay?timeout=5000&url=https%3A%2F%2Fwww.gstatic.com%2Fgenerate_204` — 测活
- `PUT /configs?force=true`，body `{"path":""}` — 热重载当前配置（不含 TUN 路由重建）
- `POST /restart`，body `{"path":""}` — 重启核心进程（TUN 改动后必须）
- **中文分组名/节点名必须 URL 编码**

排查脚本模板放在 [scripts/](scripts/) 下，按系统选用，别每次重写。

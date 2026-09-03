# Brother DCP-L2628DW（家庭打印机）

## 基本信息

- **型号**: Brother DCP-L2628DW（A4 **黑白**激光多功能一体机，打印/复印/扫描，34ppm，自动双面）
- **位置**: 家庭 LAN（192.168.50.0/24，RT-AC5300）
- **当前 IP**: `192.168.50.40`（Wi-Fi 接入；建议路由器绑 DHCP 静态租约）
- **MAC**: 94:DD:F8:ED:94:C4（由 Bonjour UUID e3248000-80ce-11db-8000-94ddf8ed94c4 末 12 位得出）

## 网络协议（2026-09-03 实测确认）

- 端口全通：IPP/IPPS（631/443）、LPD（515）、RAW（9100）；mDNS/Bonjour、SNMP
- **IPP 属性实测**（`ipptool -tv ipp://192.168.50.40/ipp/print get-printer-attributes.test`）：
  - URI: `ipp://192.168.50.40/ipp/print`，IPPS: `ipps://192.168.50.40:443/ipp/print`，无认证
  - `document-format-supported` = `application/octet-stream, image/urf, image/pwg-raster`
    → **不收 application/pdf**！PDF 必须经 CUPS 过滤链转 PWG Raster（或客户端渲染），9100 直发 PDF 不可靠
  - 双面: `two-sided-long-edge / two-sided-short-edge`；纸张: A4/Letter/A5/A6/B5/B6/信封等；IP Everywhere 兼容
- 打印语言 PCL6 / BR-Script3

## ⭐ NAS CUPS 中继（2026-09-03 已部署，AI 打印主入口）

QNAP TS-453Dmini 上 Docker 容器 **`cups-server`**（镜像 `olbat/cupsd`，host 网络，`--restart unless-stopped`）：

| 项 | 值 |
|---|---|
| 配置持久化 | `/share/CACHEDEV1_DATA/Container/cups/config` → 容器 `/etc/cups` |
| 监听 | `0.0.0.0:631`（LAN `192.168.50.2:631` + WG `10.77.77.6:631` 都可达） |
| 队列名 | `brother` → `ipp://192.168.50.40/ipp/print`（driverless/IPP Everywhere 自动 PPD，默认 A4） |
| 客户端 URI | `ipp://192.168.50.2:631/printers/brother` 或 `ipp://10.77.77.6:631/printers/brother` |
| Web 管理 | `http://192.168.50.2:631/admin`（admin 账号，密码部署时设定，问用户） |

**AI 打印标准流程（主路径，走 @nas 中转）**：
1. 本机生成/拿到待打印文件
2. PDF/大文件 → oss-upload 传 OSS 拿公网链接；图片 ≤5MB 可直接作 a2a_send 附件
3. `a2a_send @nas`：`curl -sL '<url>' -o /tmp/x.pdf && docker exec cups-server lp -d brother -o page-ranges=1-3,7 /tmp/x.pdf`
4. @nas 回报 `lpstat -W all -o brother` 确认 completed

**备选直连路径**（本机在 WG 私网或家局域网，且有 CUPS 客户端）：
```bash
lp -h 10.77.77.6 -d brother -o page-ranges=1-3,7 -o sides=two-sided-long-edge file.pdf
lp -h 192.168.50.2 -d brother -o media=iso_a5_148x210mm photo.jpg
```
（2026-09-03 本机两条路径均已 lpstat 验证通过）

## macOS（本机已配好本地队列）

- **系统名称**: `Brother_DCP_L2628DW`，IPPS over Bonjour，自动双面可用
- 打印：`lp -d Brother_DCP_L2628DW /path/to/file`
- PDF 选页：`lp -d Brother_DCP_L2628DW -o page-ranges=1-3,7 file.pdf`
- 不在家时改走 NAS 中继：`lp -h 10.77.77.6 -d brother ...`

## Windows CLI 打印

推荐直接挂 NAS 中继队列（不用装 Brother 驱动）：

```powershell
# 添加打印机 → 按 URL → http://192.168.50.2:631/printers/brother（家局域网）
# 或 http://10.77.77.6:631/printers/brother（WG 私网，任何地点可用）
# 驱动选 Generic IPP Everywhere 或 Microsoft IPP Class Driver
```

PDF 选页/份数/双面用 SumatraPDF 便携版（也能直接打 jpg/png）：
```bash
SumatraPDF.exe -print-to "<打印机名>" -print-settings "1-3,7" -silent -exit-when-done file.pdf
```

- 图片备选：`mspaint /pt image.png "<打印机名>"`
- Windows 自带 `lpr.exe` 只能发 PCL/PS 原始流、不能选页，不推荐

## 运维备忘

容器/队列运维、@nas 派发模板、客户端接入统一见 [nas-cups-relay.md](nas-cups-relay.md)。

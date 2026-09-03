# Brother DCP-L2628DW（家庭打印机）

## 基本信息

- **型号**: Brother DCP-L2628DW（A4 **黑白**激光多功能一体机，打印/复印/扫描，34ppm，自动双面）
- **位置**: 家庭 LAN（192.168.2.0/23）
- **连接方式**: Wi-Fi / 有线 / USB
- **MAC**: 94:DD:F8:ED:94:C4（由 Bonjour UUID e3248000-80ce-11db-8000-94ddf8ed94c4 末 12 位得出）
- **当前 IP**: 未知（2026-09 调研时打印机离线，建议路由器绑 DHCP 静态租约后回填）
- **设备 URI**: `dnssd://Brother%20DCP-L2628DW._ipps._tcp.local./?uuid=e3248000-80ce-11db-8000-94ddf8ed94c4`

## 网络协议（Brother 同级机型标配，待打印机开机后实测确认）

- IPP/IPPS（631）、LPD（515）、RAW/JetDirect（9100）、WSD、mDNS/Bonjour、SNMP
- AirPrint / Mopria（= IPP Everywhere 兼容，可无驱动打印）
- 打印语言 PCL6 / BR-Script3；**无原生 PDF 直打保证**——9100 直发 PDF 不可靠，PDF 应由客户端渲染（SumatraPDF）或经 CUPS 过滤链转换

## macOS 配置（已完成）

- **系统名称**: `Brother_DCP_L2628DW`，IPPS over Bonjour，自动双面可用
- 打印：`lp -d Brother_DCP_L2628DW /path/to/file`
- PDF 选页：`lp -d Brother_DCP_L2628DW -o page-ranges=1-3,7 file.pdf`

## Windows CLI 打印（本机待落地）

本机（192.168.2.70）未安装该打印机，无 lp/lpr/SumatraPDF。推荐组合：

```powershell
# 1. 装打印机（拿到 IP 后；Microsoft IPP Class Driver 即可，或 Brother 官方驱动）
Add-PrinterPort -Name "IP_Brother" -PrinterHostAddress <打印机IP>
Add-Printer -Name "Brother" -DriverName "Microsoft IPP Class Driver" -PortName "IP_Brother"
```

```bash
# 2. SumatraPDF（便携版单 exe）：PDF 选页/份数/双面，也能直接打印 jpg/png
SumatraPDF.exe -print-to "Brother" -print-settings "1-3,7" -silent -exit-when-done file.pdf
SumatraPDF.exe -print-to "Brother" -silent image.png
```

- 图片备选：`mspaint /pt image.png "Brother"`
- Windows 自带 `lpr.exe`（需启用 LPR 端口监视器）只能发 PCL/PS 原始流、不能选页，不推荐
- 重度 CLI 需求可装 WSL2 Ubuntu + CUPS，与 macOS 命令一致

## Linux / 服务器

```bash
lpadmin -p brother -E -v ipp://<打印机IP>/ipp/print -m everywhere
lp -d brother -o page-ranges=1-3 file.pdf
```

## 远程打印（纳入 WireGuard 私网）

- **路由器方案不可行**：家里 RT-AC5300 是 Merlin-KoolShare，内核 2.6.36，无 WireGuard（梅林 388+ 才有）；Entware 装 wireguard-go 太折腾，端口转发暴露公网不安全（且家宽可能 CGNAT）
- **推荐：QNAP NAS（10.77.77.6，已在 WG，与打印机同 LAN）跑 CUPS 容器做中继**（Container Station + olbat/cupsd 类镜像），监听 WG 接口并仅放行 10.77.77.0/24；远程节点用 `lp -d brother -h 10.77.77.6 -o page-ranges=... file.pdf` 或添加 `ipp://10.77.77.6:631/printers/brother`
- 已验证：本机 → 10.77.77.6 WG 链路通（16ms）

## 待办

- [ ] 打印机开机后确认 IP，路由器绑静态 DHCP，回填本文档
- [ ] 实测 IPP `document-format-supported`（确认是否收 application/pdf，还是只收 image/urf）
- [ ] Windows 侧装驱动 + SumatraPDF，封装 prt 脚本
- [ ] NAS 部署 CUPS 中继

---
name: esp32-adblocker
description: 家里 ESP32-S3 DNS 广告屏蔽器（192.168.50.168）的档案：部署状态、配置、刷机/验证方法、本地补丁。当用户提到 ESP32 广告屏蔽、AdBlocker、192.168.50.168、DNS 屏蔽广告、屏蔽器、广告拦截设备 时触发。即使用户只说"屏蔽器还正常吗"、"广告拦截看下"也应触发。
---

# ESP32 AdBlocker（家庭 DNS 广告屏蔽器）

## 设备档案

| 项 | 值 |
|---|---|
| 管理页 / DNS 地址 | **192.168.50.168**（http://192.168.50.168，MAC f8:5b:1b:93:e2:20） |
| 硬件 | ESP32-S3 N16R8（16MB flash / 8MB 八线 PSRAM），USB 供电放置于路由器旁 |
| 上游 DNS | 114.114.114.114 / 223.5.5.5（ESP32 只发 A 记录查询，AAAA 返回空） |
| 屏蔽列表 | StevenBlack hosts（GitHub 直连，每天 04:00 CST 自动更新，备选 anti-AD easylist） |
| 路由器下发 | 梅林 nvram `dhcp_dns1_x=192.168.50.168`（曾 SSH 直写+commit；UI 上改不生效的坑见下） |

源码与完整使用说明：`/Users/sun/Documents/GitHub/ESP32_AdBlocker/`（**USAGE_CN.md** 是权威文档：刷机命令、恢复出厂、注意事项都在那里）。

## 运维要点

- **断电重启后约 2~3 分钟 DNS 才可用**（先下载完列表才起 DNS 服务），正常现象
- **列表存 RAM**：每次断电都重新下载；GitHub 拉不动时管理页 Reload 换镜像源
- **单点故障**：设备断电 = 全家断网。应急：梅林 LAN→DHCP 的 DNS Server 1 删掉即可恢复
- Mac 上 curl 它的管理页必须 `--noproxy '*'`（Clash 7897 会拦截 192.168.50.x 报 502）
- 验证拦截：`dig @192.168.50.168 doubleclick.net +short` 应返回 0.0.0.0

## 本地改动与坑（相对上游 v3.7）

- `utils.cpp` +2 行补丁：pingTimeout 时 WiFi 已连接也清 crash-loop 标志。**上游 bug**：本路由器不应答 ESP32 的 ping → 标志永留 → 非受控重启后 appSetup 被跳过 → DNS 不启动。已刷入设备，重刷固件时必须保留
- 设备已设 `usePing=0`（否则每 ~90s 误判网关挂掉重启 WiFi）
- **生产固件不能开 CDCOnBoot=cdc**：无人读串口时日志缓冲写满阻塞主任务，下载列表到 98.4% 必现 task watchdog 重启
- WiFi 密码只存 NVS（Preferences 命名空间 `ESP32_AdBlocker`），不在 configs.txt；全新配置需 NVS 预置
- 梅林 UI 改 DHCP DNS 可能写不进 nvram（表现为重启后被清空）；可靠方式：`router_ssh.sh 'nvram set dhcp_dns1_x=192.168.50.168; nvram commit; service restart_dnsmasq'`
- iPhone 手动 DNS 按 SSID 分别保存；luckey 与 luckey_5G-1/5G-2 要分别设

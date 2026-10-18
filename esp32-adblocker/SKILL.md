---
name: esp32-adblocker
description: ESP32-S3 刷机部署 ESP32_AdBlocker（DNS 广告沉洞）全流程。当用户提到 ESP32 广告屏蔽、DNS 屏蔽广告、AdBlocker、DNS sinkhole、ESP32-S3 刷机/重刷固件、屏蔽手机广告、路由器广告过滤、Pi-Hole 替代品时触发。即使用户只说「重新刷一下广告屏蔽器」「ESP32 又连不上了」「AdBlocker 不屏蔽了」也应触发。覆盖本机 Mac 工具链、编译参数、局域网翻墙下载列表、已知坑位。
---

# esp32-adblocker — ESP32-S3 DNS 广告屏蔽器部署

项目：`/Users/sun/Documents/GitHub/ESP32_AdBlocker`（s60sc/ESP32_AdBlocker v3.7，Arduino sketch）。
作用：DNS 沉洞，广告域名返回 0.0.0.0，其余转发上游 DNS。使用说明（面向家人）：[references/USAGE_CN.md](references/USAGE_CN.md)（从项目仓库迁入本 skill）。

## 设备档案（本机这块板子）

- ESP32-S3，16MB Flash（QIO）+ 8MB **八线** PSRAM（编译必须 `PSRAM=opi`），MAC f8:5b:1b:93:e2:20
- 串口 `/dev/cu.usbmodem1101`，走 USB-Serial-JTAG：esptool 可自动复位进下载模式，**无需按 BOOT 键**
- 家中部署：WiFi `luckey`（仅 2.4GHz），固定 IP `192.168.50.168`，管理页 http://192.168.50.168
- 上游 DNS：114.114.114.114 / 223.5.5.5；列表 StevenBlack hosts 每天 04:00 CST 自动更新
- 设备已设 `usePing=0`：本路由器不应答 ESP32 的 ping，开着会每 ~90s 误判网关失效重启一次 WiFi
- 路由器侧：梅林 DHCP 曾向全家下发 DNS=192.168.50.168；2026-10-18 起改为下发 192.168.50.2（QNAP NAS，nvram `dhcp_dns1_x`，dns2 留空防旁路），ESP32 不再是全家默认 DNS；DNS Director 与 IPv6 均已确认关闭，无旁路

## 编译与刷写

```bash
cd /Users/sun/Documents/GitHub/ESP32_AdBlocker
# 工具链（一次性）：brew install arduino-cli esptool
# arduino-cli config set board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
# arduino-cli core install esp32:esp32   # >= 3.1.1，实测 3.3.12

arduino-cli compile --build-path ./build -e \
  -b "esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=default,FlashSize=16M,PartitionScheme=default_8MB,PSRAM=opi" .

# 全量刷写（分区表 default_8MB：app0 0x10000，spiffs/LittleFS 0x670000）
esptool --chip esp32s3 -p /dev/cu.usbmodem1101 -b 460800 write-flash \
  0x0 build/ESP32_AdBlocker.ino.bootloader.bin \
  0x8000 build/ESP32_AdBlocker.ino.partitions.bin \
  0xe000 build/boot_app0.bin \
  0x10000 build/ESP32_AdBlocker.ino.bin \
  0x670000 build/littlefs.bin
```

- 只更新固件：刷 `0x10000` 一个文件即可，配置（LittleFS + NVS）保留。
- 不要用 `*.ino.merged.bin` 与数据镜像同一把刷：merged 已填充到整片 16MB，与 littlefs.bin 重叠报错。
- LittleFS 镜像：`~/Library/Arduino15/packages/esp32/tools/mklittlefs/*/mklittlefs -c build/littlefs_staging -b 4096 -p 256 -s 1572864 build/littlefs.bin`，staging 里放 `data/AdBlocker.htm`、`data/common.js`、`data/configs.txt`。

## 局域网 / 翻墙关键点（本项目最大的坑区）

ESP32 自己不走任何代理。它要下载屏蔽列表（默认 raw.githubusercontent.com），国内直连不可靠：

1. **首选：路由器层翻墙覆盖**（华硕梅林 fancyss 把 ESP32 的流量纳入代理），设备即可直连 GitHub。本次最终方案。
2. **验证可达性要在 ESP32 上验证**，不能用 Mac 代替：Mac 上 `curl --noproxy` 看似直连成功，实际可能被 Clash TUN 模式拦截代发，给出假阳性证据。
3. **Mac 访问任何 LAN 地址（含设备管理页）一律 `curl --noproxy '*'`**：本机 http_proxy=127.0.0.1:7897（Clash），不加会走代理报 502。dig 不受影响。
4. **降级方案：Mac 临时 HTTP 服务**喂列表文件给 ESP32（仅临时，日常更新仍要靠路由器翻墙）：
   - `python3 -m http.server 8123` 必须 double-fork + setsid 脱离进程组——pi/终端会杀掉整个进程组，单 nohup 不够
   - 服务目录别放 `/tmp`（会被清理），文件句柄随 cwd 删除而失效
   - ESP32 连 Mac 报 `connection refused` 而 Mac 自连正常 → 检查 macOS「本地网络」隐私权限/防火墙（系统设置 → 隐私与安全性 → 本地网络）
5. **Mac 不适合连 ESP32 的热点做配置**：macOS 发现热点无互联网会自动 join 回家里 WiFi（无提示）。首次配网用 iPhone。
6. `networksetup -getairportnetwork` 在终端无定位权限时会谎报「未连接」，用 `ipconfig getifaddr en0` + ping 路由器确认真实状态。

## ESP32_AdBlocker 应用层要点

- 配置存两处：非密码项在 LittleFS `/data/configs.txt`（格式 `key~value~组~类型~标签`，必须含 `cfgVer~8`/`appId`/`hostName`/`AP_SSID` 行，否则 /data 被清空重建）；**密码只存 NVS**（Preferences 命名空间 `ESP32_AdBlocker`，键 `ST_SSID`/`ST_Pass`/`AP_Pass`/`Auth_Pass`）。
- 预置配置技巧：loadPrefs 先于 reloadConfigs 执行且会用 NVS 空值覆盖 configs.txt——**只刷 configs.txt 无法预置 WiFi 密码**。做法：先刷一个几行的引导 sketch（`Preferences.putString` 写入 ST_SSID/ST_Pass）跑一次建立 NVS，再刷回正式固件。
- 字段陷阱：网页上 **「Wifi SSID name」（ST_SSID=家里路由）和「AP SSID name」（AP_SSID=设备自身热点名）别填反**。填反设备会广播一个和家里同名的假热点。
- HTTP 控制口（配网/排障都能用，无需网页）：`/control?save=1`、`/control?reset=1`、`/control?displayLog=1`（RAM 日志）、`/control?zLoad=<url编码的新列表URL>`（换源，会重启）、`/status`（JSON 状态）。
- DNS 只听 UDP 53，`nc` 测 TCP 53 不通是正常的，用 `dig @IP 域名` 验证。
- 屏蔽列表只存 PSRAM（useSnap=0），**每次重启重新下载**（约 2~3 分钟），期间 DNS 正常转发但不拦截。

## 已踩过的坑（症状 → 根因）

| 症状 | 根因 | 处置 |
|---|---|---|
| 断电/异常重启后 DNS 完全不启动，网页显示 Crash loop detected | 路由不应答 ESP32 的 ping → crashLoop 标志永不清除 → startWebServer 返回 false → setup() 跳过 appSetup | **本仓库 utils.cpp 有 +2 行补丁**（pingTimeout 里 WiFi 已连接即清标志），重刷固件时保留 |
| 首页显示 Startup Failure 但 /status、/control 仍可用 | startupFailure 非空时固件只起最小 fallback web server（webServer.cpp indexHandler 分支），App/DNS 没跑；消息原文即日志里的 WARN | 远程三板斧：`curl --noproxy '*' IP/status`、`/control?displayLog=1` 看 panic 记录、`dig @IP 域名` 确认 DNS 死活；恢复用 `/control?reset=1`（doRestart 会清 crashLoop） |
| 打了 crashLoop 补丁仍偶发 Startup Failure | 补丁要等一个 ping 周期（wifiTimeoutSecs=30s）才清标志；两次崩溃间隔 <30s（如开机即崩）仍触发保护 | 属保护机制正常履职，查日志里真正的 panic 原因；Backtrace 用 `~/Library/Arduino15/packages/esp32/tools/esp-x32/*/bin/xtensa-esp32s3-elf-addr2line -e build/*.ino.elf -f -C -p <地址>` 解码（build 目录 ELF 须与在跑固件同一次编译） |
| 04:00 定时更新屏蔽列表时 panic（statusCheckTask stack overflow HWM 0） | 定时下载跑在 statusCheckTask（STATUS_STACK_SIZE 仅 4KB）上，HTTPS+TCP+WiFi TX 深调用链装不下；开机时的同一下载走 loopTask（8KB）所以正常 | appGlobals.h 把 STATUS_STACK_SIZE 调到 8KB 重刷；另一个已知 boot 期 panic 是 getExtIP 的 DNS 解析与 SNTP 并发触发 lwIP sys_untimeout assert |
| 下载列表到 98.4% 必 task watchdog 重启 | 编译开了 `CDCOnBoot=cdc` 且无人读串口 → USB 日志缓冲写满阻塞主任务 | 生产编译必须 `CDCOnBoot=default`；看日志用网页 Show Log |
| pyserial/screen 打开串口后板子「死了」（AP 消失、串口静默） | 打开串口的 DTR/RTS 线序把芯片触发进下载模式 | 正常现象；跑一次 `esptool flash-id`（结尾自动硬复位）或按 RST 恢复 |
| 换了列表 URL 后设备重启 | zLoad 换源即触发 doRestart，属设计行为 | 无需处理 |
| /status 里 blockCnt/allowCnt 一直 0 | 计数器只在主页刷新时更新，不是实时值 | 以 dig 返回 0.0.0.0 为准 |
| 梅林 UI 设 LAN→DHCP→DNS Server 重启后被清空 | UI 写的值没落进 nvram（nvram 里 dhcp_dns1_x 仍为空） | SSH 直写：`nvram set dhcp_dns1_x=192.168.50.168; nvram commit; service restart_dnsmasq`（用 asus-merlin-vpn 的 router_ssh.sh），重启持久 |
| iPhone 手动设了 DNS 但查询不到设备 | iOS 手动 DNS 按 SSID 分别保存，luckey 与 luckey_5G-1/5G-2 是不同的 | 每个 WiFi 名下分别设，或干脆靠路由器 DHCP 统一下发 |

## 部署后验收清单

```bash
dig @192.168.50.168 doubleclick.net +short   # 0.0.0.0 = 拦截正常
dig @192.168.50.168 baidu.com +short         # 真实 IP = 转发正常
curl -s --noproxy '*' http://192.168.50.168/status   # loadProg: Complete
```

手机接入（iPhone 改 DNS / 路由器 DHCP 统一发 DNS）步骤见 [references/USAGE_CN.md](references/USAGE_CN.md) 第一、二节。

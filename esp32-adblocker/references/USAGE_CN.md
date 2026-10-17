# ESP32 AdBlocker 使用说明

> 设备：ESP32-S3 开发板（16MB Flash / 8MB 八线 PSRAM，MAC f8:5b:1b:93:e2:20）
> 固件：ESP32_AdBlocker v3.7（s60sc/ESP32_AdBlocker），esp32-arduino core 3.3.12 编译
> 作用：DNS 沉洞（类似 Pi-Hole）——广告域名解析返回 0.0.0.0，正常域名转发给上游 DNS
>
> **当前状态（2026-10-17 部署完成）**：已接入家里 WiFi `luckey`，固定 IP **192.168.50.168**，管理页 http://192.168.50.168
> 上游 DNS：114.114.114.114 / 223.5.5.5；屏蔽列表 StevenBlack（54236 条域名），每天凌晨 4 点自动更新

## 一、手机接入（屏蔽手机广告）

### iPhone
设置 → 无线局域网 → 点当前 WiFi 右边的 ⓘ → **配置 DNS** → 手动 → 删掉原来的，添加 `192.168.50.168` → 存储。
同时建议：同一页面关闭「限制 IP 地址跟踪」；iCloud「专用代理」(Private Relay) 会绕过 DNS，想全屏蔽需关闭。

### Android
设置 → WLAN → 长按当前网络 → 修改网络 → 高级选项 → IP 设置改「静态」，DNS 1 填 `192.168.50.168`。
**必须关闭「私人 DNS」（Private DNS）**：设置 → 网络 → 私人 DNS → 关闭，否则走 DoT 完全绕过屏蔽。

### 全家生效（推荐）：路由器统一改 DNS
华硕梅林后台 → 内部网络(LAN) → DHCP 服务器 → **DNS Server 1 填 `192.168.50.168`**，DNS Server 2 留空（填备用会漏广告），应用后手机重连 WiFi 即可，无需逐台设置。

⚠️ ESP32 是单点——它断电时，按它做 DNS 的设备会断网。恢复：路由器/手机 DNS 改回自动。

### 验证生效
```bash
dig @192.168.50.168 doubleclick.net +short   # 返回 0.0.0.0 = 已屏蔽
dig @192.168.50.168 baidu.com +short         # 返回真实 IP = 正常解析
```
（Mac 上 curl 访问管理页要加 `--noproxy '*'`，否则被 Clash 7897 代理拦截报 502；dig 不受影响）

## 二、日常使用（管理页 http://192.168.50.168）

- **Allowed / Blocked domains**：放行/拦截计数（重启清零）
- **Enter new URL for blocklist or domain** 输入框 + 按钮：
  - 填列表 URL → **Reload**：更换并重下屏蔽列表（会重启设备）；留空 → 重下当前列表
  - 填域名 → **AddDomain** 手动加屏蔽 / **DelDomain** 解除屏蔽（误杀时用）/ **CheckDomain** 查是否在列表
- **StopLoad**：停止下载；**Clear**：清空自定义条目；**Enable AdBlocker**：总开关
- **Show Log**：运行日志（排障先看这里）；Verbose 可看每条域名的放行/拦截
- **OTA Upload**：以后免拆机升级固件/网页文件
- **Edit Config → Network / Settings**：改网络参数、上游 DNS、时区（已设 CST-8）等，Save 后生效
- 自定义加/删的域名存在设备 `custom.txt`，断电不丢

## 三、屏蔽列表

- 当前：StevenBlack 合并列表（54236 条，占 1.0MB / 6.7MB PSRAM 缓冲）
- 首次/更换下载约 2~3 分钟，下载期间 DNS 照常工作
- 备选源（在主页输入框填 URL 点 Reload）：
  - `https://cdn.jsdelivr.net/gh/StevenBlack/hosts@master/hosts`（同列表 jsDelivr 镜像）
  - `https://anti-ad.net/easylist.txt`（anti-AD，对国内手机广告针对性更强，Adblock 格式）
- 域名容量上限 25 万条（8MB PSRAM）

## 四、注意事项

1. **浏览器关「安全 DNS」**：Chrome/Edge → 设置 → 隐私和安全 → 使用安全 DNS → 关闭，否则走 DoH 绕过。
2. **IPv6**：本应用只有 IPv4 DNS。路由器若开了 IPv6，关闭其 IPv6 DNS 下发，否则部分流量绕过。
3. **断电恢复**：设备有看门狗自愈补丁（见下「本地改动」），断电重启后全自动恢复，无需人工干预。
4. LED 状态灯默认关闭。想开：Edit Config → Settings → Led status pin（WS2812 彩灯常见 GPIO 48，以板子手册为准，并把 WS2812 or Simple 改为 WS2812）。绿常亮=正常，蓝闪=下载列表，黄闪=AP 模式，红闪=故障。

## 五、恢复出厂 / 重新配置

设备连不上路由器时会自动开热点（允许在 Edit Config → Network 关闭）：
热点名 **ESP32_AdBlocker_20E2931B5BF8**（密码同家里 WiFi 密码），连上后开 http://192.168.4.1 → Edit Config → Network 修改。

⚠️ 填表陷阱：**「Wifi SSID name」是家里路由的 WiFi 名；「AP SSID name」是设备自身热点的名字**，别填反（填反会出现设备广播一个叫 luckey 的假热点）。

## 六、刷机备忘（本机 Mac）

工具链：`brew install arduino-cli` + esp32 core 3.3.12（PSRAM=opi 对应 8MB 八线 PSRAM）

```bash
cd /Users/sun/Documents/GitHub/ESP32_AdBlocker
arduino-cli compile --build-path ./build -e \
  -b "esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=default,FlashSize=16M,PartitionScheme=default_8MB,PSRAM=opi" .
# 全量刷写（esptool 经 USB-Serial-JTAG 自动进下载模式，无需按 BOOT 键）
esptool --chip esp32s3 -p /dev/cu.usbmodem1101 -b 460800 write-flash \
  0x0 build/ESP32_AdBlocker.ino.bootloader.bin \
  0x8000 build/ESP32_AdBlocker.ino.partitions.bin \
  0xe000 build/boot_app0.bin \
  0x10000 build/ESP32_AdBlocker.ino.bin \
  0x670000 build/littlefs.bin
# 只更新固件（保留配置）：只刷 0x10000 一个文件即可
```

- `build/littlefs.bin` 由 mklittlefs 生成（`build/littlefs_staging/data/`：网页文件 + 预置的 configs.txt）
- **CDCOnBoot 必须保持关闭（default）**：开日志到 USB 后，无人读串口时日志缓冲写满会阻塞主任务，下载列表到 98.4% 必现 task watchdog 重启（本机实测）。要看日志用网页 Show Log。
- **WiFi 密码只存 NVS 不落 configs.txt**：预置配置时除 LittleFS 的 configs.txt 外，还需先刷一个写 `Preferences`（命名空间 `ESP32_AdBlocker`，键 `ST_SSID`/`ST_Pass`）的引导固件建立 NVS，再刷回正式固件（一次性引导 sketch 模式）。
- 用 pyserial 直接打开串口会把芯片触发进下载模式（串口静默、AP 消失），跑一次 `esptool flash-id`（结尾自动硬复位）或按 RST 恢复。

## 七、本地改动（相对上游 v3.7）

**utils.cpp（+2 行，建议保留）**：pingTimeout 里 WiFi 已连接时也清 crash-loop 标志。
上游逻辑只有 ping 成功才清标志；本路由不应答 ESP32 的 ping → 标志永留 → 非受控重启后 web server 自检失败 → appSetup 被跳过 → **DNS 服务不启动**。补丁让设备断电重启后能自愈。不改的话，断电后需开管理页手动 Restart 一次才会启动 DNS。

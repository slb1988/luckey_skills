# ADB 连接与端口定位

## 证据优先级

**真实 shell 执行 > 实际监听 > 运行进程 > 系统属性 / 设置开关 / UI 标签。**

该定制固件可以同时出现：

| 信号 | 采样值 |
|---|---|
| `init.svc.adbd` | `running` |
| `service.adb.tcp.port` / `persist.adb.tcp.port` | `5555` |
| `persist.adb.tls_server.enable` | `1` |
| `service.adb.tls.port` | `44809`（动态值） |
| `ss -lnt` | 有 44809、9898 和另一个未归属监听；**没有 5555** |
| `settings get global adb_enabled` / `adb_wifi_enabled` | 都是 `0` |
| `sys.usb.config` / `sys.usb.state` | `mtp` |
| `dumpsys adb` | `connected_to_adb=false` |
| Mac 实际连接 + `shell id` | 成功，`uid=2000(shell)` |

所以：5555 拒绝连接的直接原因是**该端口未监听**，不是密码不正确，也不是全机 ADB 未运行。成功使用的是 TLS 属性对应的实际端口。属性与监听为何在本固件中不同步的内部实现尚未证实，不编造“防火墙拦截”或“已关闭无线调试”的结论。

## 1. 检查 Mac 工具与目标

```bash
command -v adb
adb version
adb devices -l
ping -c 3 "$DEVICE_IP"
nc -vz -G 3 -w 3 "$DEVICE_IP" 5555
adb mdns services
```

`-G` 是 macOS nc 的连接超时选项，不直接搬到所有平台。mDNS 为空不证明没有网络 ADB。采样中 ADB 32.0.0 已足够连接，无需先升级或重装工具。常见工具位置为 Android SDK `platform-tools/adb` 或 Unity 随附 SDK；先找现有安装，不写死本机 Unity 版本路径。

## 2. 从学习机内部发现实际端口

在已连接的设备 shell / 应用管家“执行 adb 命令”中运行，**不加 `adb shell` 前缀**：

```sh
id
getprop init.svc.adbd
getprop service.adb.tcp.port
getprop service.adb.tls.port
ss -lnt
```

如果只有 Web，使用 [web-command-bridge.md](web-command-bridge.md) 取回这几项。不要为了找端口进行全网扫描，也不要把某次随机端口存为永久默认。

`ss` 不可用时可用 `netstat -lnt`，但本机 toybox 输出曾混入非 LISTEN 行，必须再按 `LISTEN` 过滤。`ss -p` 看不到进程名时不要猜端口归属。

## 3. Mac 显式连接并验证

把查到的端口赋给 `ADB_PORT`：

```bash
S="${DEVICE_IP}:${ADB_PORT}"
adb connect "$S"
adb -s "$S" get-state
adb -s "$S" shell 'id; getprop ro.product.model; getprop sys.boot_completed'
```

成功标准：目标为 `device`、型号符合、shell 有真实输出；`sys.boot_completed=1` 表示系统完成启动，不代表所有学习应用功能都通过测试。

本 Mac 实测未输入口令/配对码即可连接；这**不能证明所有主机免认证**，可能存在已有信任或定制行为。不要读取或复制设备/其他电脑的私钥。

## 4. 分类型处理失败

| 结果 | 含义与下一步 |
|---|---|
| `Connection refused` | 目标可达但该端口无服务或明确拒绝；内部查监听，不重试口令 |
| 超时 | 检查 IP 漂移、同一局域网、隔离、防火墙、休眠；先单点探测，不重置网络 |
| `unauthorized` / 认证失败 | 让用户在设备上确认授权；若系统要求无线配对，走其显示的配对端口和当次配对码 |
| `offline` | 仅断开这个目标再连接；不默认 `adb kill-server`，避免影响其他设备 |
| Web 有输出、外部不通 | 核对回环/全部接口监听、端口、Mac 到该端口的连通性 |
| ADB 有效、设置开关却为 0 | 定制系统的控制面与实际 daemon 不一致；以真实运行证据为准 |

标准 Android 无线调试的**配对端口和连接端口不同**。仅当设备明确要求时运行 `adb pair "${DEVICE_IP}:${PAIR_PORT}"`，交互输入当前配对码。不要拿未知应用口令冒充配对码。

## 5. 厂商配置线索与变更边界

只读查看到 `/vendor/etc/init/hw/init.rk30board.rc` 中：

- `persist.internet_adb_enable=1` 的触发器设置 `service.adb.tcp.port=5555` 并 `restart adbd`。
- 值为 0 的触发器设置端口为 0 并重启 adbd。
- 本台该属性读取为空；存在触发器不代表当前触发器实际执行过。

不要直接写这个持久属性来“修复”：它会重启现有 ADB 并可能扩大网络暴露。当前端口能满足任务时不改 5555。

`/apex/com.android.adbd/bin/adbd` 存在，而某份 init 配置提到的 `/system/bin/adbd` 不存在；读取 `/proc/<adbd-pid>/exe` 被拒绝。没有证据证明运行 daemon 的二进制归属，不靠这组线索断言系统损坏，也不替换二进制。

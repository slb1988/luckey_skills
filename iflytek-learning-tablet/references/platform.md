# 平台与系统基线

## 适用范围

采样标识：2026-10-04，本台内部型号 `su30pro` / 固件 `iFLY_V1.05.9`。这是设备上报与只读实测，不是全系列产品规格或出厂安全承诺。零售商品型号未核实。

| 层次 | 实测 | 含义 / 复核入口 |
|---|---|---|
| 厂商 | `iFLYTEK` | `ro.product.manufacturer` / `brand` |
| 型号 | `rk3588s_su30pro_native`；device/product `su30pro` | 不由内部代号推断零售名称 |
| 平台 | `ro.board.platform=rk3588`，`ro.hardware=rk30board`，SoC 厂商 Rockchip | 型号含 rk3588s，但平台属性本身是 rk3588 |
| CPU | 8 个逻辑 CPU，aarch64 | 不执行性能跑分 |
| CPU 调频策略 | policy0 最大 1.8GHz，policy4/6 最大 2.4GHz，均 schedutil | 策略上限，不代表即时频率或持续性能 |
| ABI | `arm64-v8a,armeabi-v7a,armeabi` | 原生库优先匹配 arm64；个别系统应用仍是 32 位 |
| 内存 | `MemTotal=12179988 kB`，约 11.6GiB；swap 约 5.8GiB | 内核可见容量；不能把 swap 算作物理 RAM |
| GPU | ARM Mali-G610，OpenGL ES 3.2 | `dumpsys SurfaceFlinger` 的 GLES 行 |
| Android | release `12`，SDK `32` | SDK 32 对应 Android 12L/API 32；不要只按 release 12 推成 API 31 |
| 固件 | `iFLY_V1.05.9`，`user/release-keys` | `ro.build.display.id`、type、tags |
| 构建 | `SQ3A.220605.009.B1`，fingerprint 含 `eng.root.20260904.020807` | 构建字符串里的 root 不是“已 root”证据 |
| 内核 | Linux 5.10.66、aarch64 | 内核构建时间 2026-09-04；不代表安全补丁同样新 |
| 安全补丁上报 | `2022-06-05` | 固件版本新不等于 Android 安全补丁新，详见安全模块 |
| 用户数据 | `/data` 为 f2fs，约 453GiB，底层观测到 NVMe 分区 | `df` 的显示挂载点可能是同一文件系统的 bind mount |
| 只读系统 | `/system`、`/vendor` 对应 dm 设备；vendor 为 ro ext4 | 接近 100% 使用率可为镜像布局正常结果 |
| 显示 | 2016×3024，320dpi，支持约 60/120Hz | 采样时实际约 60Hz；横屏截图尺寸可能反转 |

## 分层理解

1. **Rockchip / Linux / HAL**：CPU 调频、NVMe、GPU、音频、相机、触控/笔、Wi-Fi。
2. **Android 12L 框架**：PackageManager、ActivityManager、SurfaceFlinger、WebView、存储、电源及 ADB 服务。
3. **讯飞系统定制**：TyeLauncher、IflySettings、IflySystemUI、HwcService，以及账号/数据中心、管理、OTA、学习应用。
4. **应用管家**：普通安装应用，持有部分授予权限，提供独立 HTTP 服务和内部 ADB 客户端。它不是系统 adbd 本身。
5. **Mac 工具**：外部 ADB 或 HTTP 命令桥。两条链路生命周期和权限并不相同。

包名与责任边界见 [apps-services.md](apps-services.md)，不要把所有故障归给 Android 或学习桌面。

## 最小复采

以下运行在设备 shell；电脑前置 `adb -s "$S" shell`：

```sh
getprop ro.product.model
getprop ro.board.platform
getprop ro.product.cpu.abilist
getprop ro.build.display.id
getprop ro.build.version.release
getprop ro.build.version.sdk
getprop ro.build.version.security_patch
uname -a
grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo
wm size
wm density
df -h /data /system /vendor
```

不要为了盘点跑无筛选 `getprop`、完整 bugreport 或导出所有设置：它们可能带设备序列号、网络和个人信息。缺失属性只表示该属性无值，不等于对应硬件/功能不存在。

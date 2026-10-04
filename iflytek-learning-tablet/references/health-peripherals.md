# 运行状态、屏幕与外设

## 解释原则

这是只读系统盘点，不是硬件压力测试。每次报告区分“系统识别到”“采样状态正常”和“端到端功能实测成功”。

### 存储与内存

```bash
adb -s "$S" shell 'uptime; df -h /data /sdcard /system /vendor'
adb -s "$S" shell 'grep -E "^(MemTotal|MemAvailable|MemFree|Cached|SwapTotal|SwapFree):" /proc/meminfo'
```

采样示例：用户数据容量约 453GiB、使用约 101GiB、剩余约 352GiB；MemAvailable 约 7.2GiB，而 MemFree 只有约 219MiB。缓存可回收，不凭 MemFree 小就清内存。内存/磁盘数值是快照，下次重新采样。

只读系统镜像可能显示 100%，先看 `/data`。多个 `df` 行可能是同一个块设备/挂载别名，不重复相加容量。不跑全盘 `du`、全盘删缓存或读写测速作为默认检查。

### 电源与温度

```bash
adb -s "$S" shell dumpsys battery
adb -s "$S" shell dumpsys thermalservice
adb -s "$S" shell 'dumpsys power | grep -E "(mWakefulness=|mIsPowered=|mBatteryLevel=|mWakeLockSummary=)"'
```

- 电池温度单位常为 0.1°C：采样 `temperature=265` = 26.5°C。
- 采样电池 46%、status 3（放电）、health 2（GOOD），只代表瞬时状态，不是寿命/容量测试。
- `thermalservice` 虽显示 Thermal Status 0，但 **HAL Ready: false**、没有温度列表；不能因此断言 CPU/GPU 温度正常或不存在热降频。
- 不执行 `dumpsys battery set`，不关热控，不把一条 uptime/load 当完整性能诊断。

### 显示、触控与笔

```bash
adb -s "$S" shell 'wm size; wm density'
adb -s "$S" shell 'dumpsys display | grep -E "(DisplayDeviceInfo|mActiveModeId=|mDesiredDisplayModeSpecs=)"'
adb -s "$S" shell 'grep -E "^(N: Name|P: Phys|H: Handlers)" /proc/bus/input/devices'
adb -s "$S" shell 'dumpsys SurfaceFlinger | grep "GLES:"'
```

本台识别到：

- 内屏 2016×3024 / 320dpi，60Hz 与 120Hz 两个模式；采样 active mode 为 60Hz。支持 120Hz 不等于每个应用正在 120Hz 运行。
- `NVTCapacitiveTouchScreen`、`NVTCapacitivePen`、`pen insert event`，以及电源、Hall 等输入设备。
- Mali-G610 / OpenGL ES 3.2。

这些不证明笔压、全屏触点和高刷新模式都已实测。诊断时不直接执行 `wm size/density` 设置或强制刷新率。

截图仅在用户允许且不会暴露个人内容时：

```bash
adb -s "$S" exec-out screencap -p > screenshot.png
```

先确认输出确为 PNG，当前旋转下尺寸可能是 3024×2016；坐标依据当次图像原始尺寸，不能照搬旧截图。该固件 `uiautomator dump` 曾未输出 XML，不把它当可靠的唯一 UI 通道。

### 相机、音频、传感器与无线硬件

```bash
adb -s "$S" shell 'lshal 2>/dev/null | grep -E "android.hardware.(camera|audio|sensors|thermal|graphics.composer|bluetooth|wifi)"'
adb -s "$S" shell 'dumpsys media.camera | grep -E "Number of (camera devices|normal camera devices|public camera devices)"'
```

注册表观察到：audio 7.0、camera provider 2.4、sensors 1.0、graphics composer 2.1、Bluetooth 1.0，以及 Wi-Fi 相关接口。接口注册不等于功能测试通过，lshal 兼容接口多行也不代表多套物理硬件。

相机服务同时上报 `Number of camera devices: 2` 与 normal/public(API1) 数量 4，口径不一致。保留原值，不直接宣称“有 4 个物理摄像头”。

不默认拍照、录像、录音、播放测试声或开启传感器长时间采样；硬件端到端验证需用户允许。

## 常见误判

| 看到的现象 | 不能直接推出 |
|---|---|
| shell 命令退出 0 | 命令串中每一步都成功；需看 stderr 和各阶段结果 |
| `ss` / HAL 列表存在 | 所有业务功能正常 |
| 内存 free 小 | 内存耗尽 |
| `/vendor` 100% | 需要清理系统分区 |
| 热状态 0、HAL 未就绪 | 所有芯片温度安全 |
| 当前 60Hz | 屏幕不支持 120Hz |
| UI 自动化工具无输出 | ADB 整体不可用 |

# 屏幕亮度

macOS 15 (Apple Silicon) 实测验证。有**纯 CLI 路径**，不需要碰 GUI。

## 操作路径

用随附脚本（python3 标准库 ctypes，无第三方依赖，无需 sudo，无授权弹窗）：

```bash
python3 scripts/brightness.py            # 读当前值，输出 0.803 这样的浮点
python3 scripts/brightness.py set 0.6    # 设绝对值（0.05-1.0，自动钳制）
python3 scripts/brightness.py up 0.1     # 步进（默认步长 0.1）
python3 scripts/brightness.py down 0.1
```

set/up/down 自带 read-back 输出，返回值即实测值。

## 原理与边界

1. **机制**：CoreGraphics `CGMainDisplayID()` 取主屏 id → 私有框架 `DisplayServices.framework` 的 `DisplayServicesGetBrightness` / `DisplayServicesSetBrightness`（返回 0 = 成功）。这就是控制中心亮度条背后的同一接口，立即生效。
2. **下限钳到 0.05**：设 0 会让屏幕全黑像死机，物理亮度键仍可救但没必要吓用户。
3. **只控主屏内置显示器**。外接显示器亮度走 DDC/CI 协议，此路径不覆盖（未验证）。
4. **与环境光自动调节的关系**：系统设置里若开着「自动调节亮度」，设完可能被系统随后覆盖；用户抱怨"设了没用"时先查这一项（系统设置 → 显示器）。
5. 验证口径就是 read-back（`DisplayServicesGetBrightness` 重读），与显示在同一输出里；无需 system_profiler（它不报告亮度）。

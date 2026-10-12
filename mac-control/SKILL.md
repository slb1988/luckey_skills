---
name: mac-control
description: 控制本机 Mac 的系统级开关与参数（蓝牙开关、屏幕亮度等），每种功能有实测验证过的操作路径与独立 reference。当用户提到关蓝牙、开蓝牙、蓝牙状态、bluetooth、屏幕亮度、亮度调高调低、屏幕太亮/太暗、brightness，或要求用命令行/脚本控制 Mac 系统设置时触发。即使用户只说"把蓝牙关了"、"亮度调到一半"也应触发。执行任何系统控制后必须用系统接口实测最终状态，不得凭操作返回值宣称成功。
---

# mac-control — Mac 系统控制

按功能拆分到 references，操作时**先读对应 reference 再动手**，不要凭记忆拼命令。

## 功能路由

| 功能 | Reference | 已验证路径 |
|---|---|---|
| 蓝牙开关 / 状态 | [references/bluetooth.md](references/bluetooth.md) | AppleScript UI scripting（一条 osascript 命令） |
| 屏幕亮度 | [references/brightness.md](references/brightness.md) | 纯 CLI：python3 + ctypes DisplayServices 私有框架 |

## 共享纪律（所有功能通用）

1. **实测最终状态才算数。** GUI 合成点击/AX 动作可以返回"成功"但控件值根本没变；每个操作结束后用独立的系统读取口径验证（蓝牙用 `system_profiler SPBluetoothDataType`，亮度用 DisplayServices read-back），脚本自身已内置验证。
2. **幂等优先。** 先读当前状态，已是目标状态就不动，避免无意义地拨动开关/打断已连接设备。
3. **同一控件不并行。** 系统设置 GUI 是单一共享状态，多 agent 同时操作同一开关会互相拨回去；串行执行。
4. **破坏性确认框要处理。** macOS 部分开关（如关蓝牙）会弹强制确认框，脚本必须代点确认，否则操作悬空。
5. **权限前提。** AppleScript UI scripting 要求调用方终端有「辅助功能」权限；orca computer-use 助手单独授权。权限缺失的报错特征是 System Events 报"不能获得"元素或 osascript 直接报辅助功能未授权。

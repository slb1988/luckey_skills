# 蓝牙开关

macOS 15 实测验证（MacBook Pro, BCM_4387）。

## 操作路径

用随附脚本，幂等，关闭时自动处理确认弹窗：

```bash
osascript scripts/bluetooth.scpt off   # 或 on
```

返回 `already off/on`（未动）或 `now=0/1`（已切换）。执行后脚本内已回读开关值；如需独立复核：

```bash
system_profiler SPBluetoothDataType | grep -E "State:|Connected"
```

`State: On/Off` 是唯一可信口径；`Connected:` 段列出当前已连接设备。

## 关键事实（为什么脚本长这样）

1. **关蓝牙有强制确认框**「确定要关闭蓝牙吗？你将无法通过蓝牙键盘、鼠标或触控板控制此电脑。」不点「关闭」不生效。确认框是 `sheet 1 of window "蓝牙"`，里面两个按钮**没有可访问名称**（name 为 missing value），按位置取：`button 1`=取消、`button 2`=关闭。弹窗出现有延迟，脚本用 5 秒轮询等待。开蓝牙无弹窗。
2. **开关的元素路径**（macOS 15.6.1）：
   `checkbox 1 of group 1 of scroll area 1 of group 1 of group 2 of splitter group 1 of group 1 of window "蓝牙"`
   系统升级后若路径漂移，用 System Events 逐层 dump `UI elements of window "蓝牙"` 重建，别瞎猜索引。
3. **关蓝牙会立即断开所有已连接设备**（耳机/键鼠）。用户若正用蓝牙音频，操作前值得在回复里提一句。
4. **执行环境**：脚本会唤起系统设置窗口到前台并停留；要求调用 osascript 的终端已有「辅助功能」权限（能 `osascript -e 'tell application "System Events" to get name of every process'` 不报错即具备）。

## 备用路径：orca computer-use

AppleScript 权限不可用时，用 computer-use skill 驱动同一界面：元素树里开关是「转换」(AXCheckBox)，确认框是独立窗口（约 260x218，标题为空），点「关闭」按钮。注意其 **accessibility 点击可以 ok:true 但控件值不变**——以其返回的快照不算数，必须以 `system_profiler` 实测收尾。

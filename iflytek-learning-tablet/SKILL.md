---
name: iflytek-learning-tablet
title: 讯飞学习机系统排障与家长端管理
description: 科大讯飞学习机的 Mac/电脑 ADB 连接、应用管家 Web 命令桥、系统排障及讯飞AI学家长端自动化。用户提到讯飞学习机、iFLYTEK、su30pro、rk3588s_su30pro_native、外部 adb 连不上、5555 拒绝连接、9898/cmd.html、应用管家执行命令、系统分析，或希望 AI 点击家长 App、分析使用习惯、限制动画/应用时长时使用。覆盖端口发现、权限、系统组件和家长端只读检查→确认限制→验证生效；不替代 kid-learning-journey 后台开发，不默认解锁、root、刷机或解除家长管理。
tags: [iflytek, android, adb, learning-tablet, diagnostics, parent-control]
---

# 讯飞学习机

## 工作边界

面向用户授权的学习机，优先只读诊断。当前经验来自内部型号 `su30pro`、固件 `iFLY_V1.05.9`，不能泛化为所有讯飞机型或出厂默认行为。

- IP、端口、PID、可用空间、应用版本都是可变状态，先复查再执行。
- 所有 ADB 操作带 `-s "$S"`；`S` 是已核实的 `当前IP:当前端口`，不自动选第一台设备。
- 不收集账号、学习内容、照片、Wi-Fi 密码、ADB 私钥或整机 bugreport。临时诊断输出存本地忽略目录，不把原始截图/序列号放进共享知识。
- 重启、`adb tcpip`、`setprop`、修改 settings、授权/禁用/卸载应用、打开摄像头/麦克风、清理数据、root/刷机属于另一次明确授权的变更，不是默认检查步骤。
- 网页操作会进入设备命令终端；需要切换前台页面时先说明，不自动关闭安全策略或常驻服务。
- 家长端任务只查看经授权的应用用时与现有限制；具体应用/时段调整经家长确认后再保存，不把设备维护用时全部算作孩子学习或娱乐。

## 模块导航

| 需求 | 按需读取 |
|---|---|
| AI 操作讯飞AI学家长端、学习习惯、动画与应用限时、低年级专注管理 | [parent-app-focus-management.md](references/parent-app-focus-management.md) |
| 硬件、Android/API、固件、分区和平台识别 | [platform.md](references/platform.md) |
| ADB 拒绝连接、实际端口、授权、USB 与无线调试 | [adb-connection.md](references/adb-connection.md) |
| `cmd.html`、从 Mac 发命令、取回输出、HTTP 200 却无执行 | [web-command-bridge.md](references/web-command-bridge.md) |
| 桌面、系统设置、管家、MDM、网络管理、OTA、WebView | [apps-services.md](references/apps-services.md) |
| 卡顿、容量、电池、温度、屏幕、触控/笔、音视频硬件 | [health-peripherals.md](references/health-peripherals.md) |
| 调试暴露面、SELinux、启动锁、系统更新和维护边界 | [security-maintenance.md](references/security-maintenance.md) |

不要为单一连接故障加载并执行所有模块；用户要求系统盘点时才分模块批量采集。家长端 UI 任务直接走对应参考，不执行下面的 ADB 诊断流程。

## 最短执行流程（设备连接与排障）

1. **确认现场**：当前 IP、应用管家是否运行、问题是否只影响电脑直连。先 `adb devices -l`、目标端口连通性检查，不扫描整个网段。
2. **发现端口**：优先已有 USB/ADB 会话或学习机命令终端；读取 `getprop service.adb.tls.port` 与 `ss -lnt`。只有 Web 可用时，使用 Web 桥接参考和脚本。不要从口令猜端口。
3. **端到端验证**：`adb connect "$S"` → `adb -s "$S" get-state` → `adb -s "$S" shell id`。以 shell 成功为准，不以 `connected` 文案或属性值单独宣布完成。
4. **定位对应模块**：一次收集独立证据；命令报错记为权限/工具限制，不用修改系统来掩盖。
5. **结束**：给结论、决定性证据、可复制的下一步；清理仅本次创建的临时文件。未进行负载、摄像头、麦克风或重启测试时明确说明。

## 快速命令

先把环境变量设为当前设备信息，`S="${DEVICE_IP}:${ADB_PORT}"`。

```bash
adb connect "$S"
adb -s "$S" get-state
adb -s "$S" shell 'id; getprop ro.product.model; getprop sys.boot_completed'
```

ADB 不通但 Web 可用，且设备的“执行命令”页处于可接收状态时：

```bash
python3 scripts/web_shell.py --base-url "http://${DEVICE_IP}:9898" \
  'getprop service.adb.tls.port; ss -lnt'
```

脚本路径相对本 Skill 目录；从其他工作目录使用绝对路径。默认执行的是设备上的 ADB shell，不要再次添加 `adb shell` 前缀。

## 判据示例

- `service.adb.tcp.port=5555`，但 `ss` 没有 5555，而 `service.adb.tls.port=44809` 与实际监听吻合：连接**本次查到的**端口。44809 只是采样值。
- `/cmd` 返回 `OK`，未生成结果文件：只证明请求收到。先核实管家的“执行命令”页、内部 ADB 状态和存储权限，不能反复重发可能产生副作用的命令。
- `MemFree` 很小但 `MemAvailable` 充足，不判内存耗尽；只读 `/system` 接近 100% 也不等于用户数据分区满。

## 回报格式

- **结论**：已恢复 / 已定位 / 未确认，具体是哪一层。
- **证据**：当前设备身份、实际端口/监听、`id` 或对应模块的关键值。
- **边界**：系统上报值、推测、未验证项分开；不把“能连 ADB”写成“所有硬件正常”。
- **下一步**：最小操作及是否需要用户授权。若保存原始证据，报告本地路径但不默认上传。

## 维护与验证

更新固件或管家版本后，重新验证端口发现、Web 接口、终端生命周期和权限。长期机制写 references；临时网络地址、口令和个人使用数据不写共享 Skill。

```bash
python3 ../skill-creator/scripts/quick_validate.py .
python3 -m unittest discover -s tests -v
```

`evals/evals.json` 保存行为评测用例；单元测试/真实命令回归不等同于模型 with-skill / baseline A/B 评测。

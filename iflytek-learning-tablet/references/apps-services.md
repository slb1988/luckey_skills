# 应用、系统服务与责任定位

## 组成与核实边界

采样固件 `iFLY_V1.05.9`：PackageManager 列出 216 个系统包、22 个第三方包；计数会变化。`pm list packages -s` 包括更新到 `/data/app` 的系统应用，因此 APK 在 data 分区不代表它是普通第三方应用。

下表“职责”是按安装目录、包名、解析到的组件及 Binder 名称建立的定位入口，不等于已逐一验证其业务行为。不能仅因名称含 MDM/netguard 就断言它阻断了某条命令。

| 层次 / 场景 | 包或组件 | 证据与定位用法 |
|---|---|---|
| 默认学习桌面 | `com.toycloud.launcher/.ui.AiStudyLauncherActivity` | HOME intent 实际解析结果；来自 `/system/app/TyeLauncher`，UID 1000 |
| 备用 Launcher | `com.android.launcher3` | `/system_ext/priv-app/IflyLauncher3QuickStep`；安装不代表当前默认 |
| 设置 / 系统 UI | `com.android.settings` / `com.android.systemui` | IflySettings / IflySystemUI；Android 包名下仍是厂商定制实现 |
| 厂商硬件服务 | `com.iflytek.hwc.service` | 特权持久应用、UID 1000；Binder 有 `hwc_service` / `hwc_internal_service`，接口 `com.iflytek.hwc.service.IHwcService` |
| 设备管理入口 | `com.iflytek.ebg.aistudy.mdm` | 系统应用、UID 1000；家长/设备管理相关故障先定向看证据，不默认停用 |
| 网络管理入口 | `com.iflytek.ebg.aistudy.netguard` | 已更新系统应用、UID 1000；不据此推断 firewall 规则 |
| OTA | `com.iflytek.study.ota` | 已更新系统应用、UID 1000；检查更新版本，不擅自触发升级 |
| 数据中心 | `com.iflytek.datacenter` | Binder `service_iflytek_data_share_center`，32 位 primary ABI；不导出个人学习数据库 |
| 用户 / 家长入口 | `com.iflytek.usercenter`、`com.iflytek.cbg.aistudy.contact.parents` | 仅做包定位，不读取账号或家长管理内容 |
| 设备诊断 / 日志 | `com.iflytek.hardware.validation`、`com.hwc.rklog`、`com.iflytek.cbg.aistudy.logservice` | 安装存在，不代表可以安全执行所有工厂测试 |
| 护眼 / 锁屏 | `com.iflytek.eyecareassistant`、`com.iflytek.lockscreen` | 弹层、锁屏行为的候选模块；先复现，不因名字删除 |
| 浏览器 | `com.toycloud.app.greenbrowser`、`mark.via` | App 版本和内核版本分开查 |
| WebView | `com.android.webview` | 当前选中 94.0.4606.71；不是根据浏览器版本推算 |
| 应用管家 | `com.yunpan.appmanage` | 1.7.7 / 1777、UID 10088、targetSdk 28；普通第三方应用 |

应用管家已授予 `WRITE_SECURE_SETTINGS`、`DUMP`、`QUERY_ALL_PACKAGES`、`SYSTEM_ALERT_WINDOW` 等权限，且存在 `:acc` 进程中的 `StartService`。这些权限与服务不能推导成 root，也不能保证命令终端后台常驻。

定向 `dumpsys device_policy` 筛选没有命中 Owner/admin 项，`enabled_accessibility_services=null`。这只说明这些检查没有看到对应配置，**不能证明不存在厂商家长限制或私有策略**。

## 常用只读定位

电脑侧显式带 `-s "$S"`：

```bash
adb -s "$S" shell cmd package resolve-activity --brief \
  -a android.intent.action.MAIN -c android.intent.category.HOME
adb -s "$S" shell pm list packages -3
adb -s "$S" shell pm list packages -d
adb -s "$S" shell pm path com.yunpan.appmanage
adb -s "$S" shell 'dumpsys package com.yunpan.appmanage | grep -E "(versionCode=|versionName=|userId=|pkgFlags=|primaryCpuAbi=)"'
adb -s "$S" shell dumpsys webviewupdate
adb -s "$S" shell 'service list | grep -E "(hwc_|rkbox|nearlink|iflytek_data)"'
```

本台 disabled 列表出现 NFC 与 LatinIME；不视为需要修复，中文输入法及硬件用途可能由厂商定制。

## 症状到模块

- **网页空白/JS 特性失效**：先核对当前 WebView provider/版本与页面错误，再看网络、证书和浏览器；不直接清空全应用数据。
- **桌面不显示已安装 App**：分别检查 PackageManager 安装状态、是否有 LAUNCHER Activity、TyeLauncher 的显示/管理策略；“已安装”与“桌面允许显示”不同。
- **安装失败**：记录实际 `INSTALL_FAILED_*`，核对 ABI、minSdk、包签名/同包升级；获取安装授权后再操作，不用自动卸载作为重试。
- **相同命令在不同入口权限不同**：分别执行 `id`，普通应用 shell、ADB shell、系统 UID、root 不混用。
- **怀疑管理模块拦截**：先形成一条可复现失败与最小日志；未经用户授权不关闭 MDM、网络管理、护眼或家长控制。

## 定向日志而非整机转储

先查目标 PID，限制时间/条数，仅采集复现窗口：

```bash
PID=$(adb -s "$S" shell pidof com.yunpan.appmanage | tr -d '\r')
# 确认只有一个 PID 后再执行，别把多个 PID 当成单个参数。
adb -s "$S" logcat --pid="$PID" -d -t 200
```

日志可能带网址、账号或学习内容，分享前脱敏。无明确故障不采集全量日志；多进程应用分别选择所需进程，不强行 `force-stop` 来简化观察。

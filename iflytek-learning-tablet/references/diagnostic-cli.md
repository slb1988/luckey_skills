# 一键连接与只读故障快照

入口：[tablet_diag.py](../scripts/tablet_diag.py)，Python **3.9+ 标准库**及已有 `adb`，不安装服务、数据库或定时任务。连接发现复用 [web_shell.py](../scripts/web_shell.py)。验证基线为 `rk3588s_su30pro_native` / `iFLY_V1.05.9`；其他固件可能缺字段或拒绝命令，必须按每次采集的型号、版本与错误解释，不能套用旧结论。

## 从仓库根目录运行

先设置 `DEVICE_IP` 为当前授权设备 IP；不从历史快照沿用旧 IP/端口。

```bash
TOOL=.agent/skills/iflytek-learning-tablet/scripts/tablet_diag.py
python3 "$TOOL" connect "$DEVICE_IP"
python3 "$TOOL" collect "$DEVICE_IP" --label tablet-a

# 将 collect 打印的 JSON 路径分别赋给 OLD、NEW；OLD 在前
python3 "$TOOL" compare "$OLD" "$NEW"
python3 "$TOOL" compare "$OLD" "$NEW" --json
```

- `connect` 输出 JSON；成功必须有 `online=true`、`state=device`、非空型号及 `shell_uid=2000`。
- `collect` 包含连接，不必先单独 connect。`--label tablet-a` 是用户维护的长期设备别名：同设备沿用，换设备换标签；不填姓名或序列号。不自动把 IP 当物理身份。
- 找不到现有 ADB 时传 `--adb /path/to/platform-tools/adb`，或把 SDK 的 `platform-tools` 加入 PATH；工具不自动安装/升级。
- `--expect-model rk3588s_su30pro_native` 可防型号误连；型号不符不会采集。
- `--no-web` 仅复用有效 ADB 会话，用于不希望自举时；不会重置或断开已有连接。
- `--output-dir /local/path` 可指定历史目录。默认从脚本位置定位项目根 `.local/iflytek-learning-tablet/snapshots/`（不是调用者 cwd）；独立安装时回退 `~/.local/iflytek-learning-tablet/snapshots/`。

## 连接判据与失败提示

1. 只查看输入 IP 的现有网络 ADB 会话，不自动选择第一台设备，不检查其他设备 shell。
2. 有有效会话则依次核验 `get-state`、`ro.product.model`、`id`；实际 shell 成功即证明设备在线，不依赖 ping。
3. 否则通过当前 IP 的管家 Web 桥提交**一次**只读查询：UID、TLS/TCP 属性和 `ss -lnt`。仅选属性与非回环 LISTEN 同时匹配的端口，TLS 优先；不试固定 5555，不试未知监听，不扫描网段。
4. `adb connect` 后重新核验状态、型号与 UID；单独的 HTTP 200/OK 或 connected 文案都不代表成功。

Web 入口失败时按提示核对同一局域网、设备当前 IP、管家的“执行命令”页面及其内部 ADB 授权状态。工具不会切换前台、配对、写设置、重启 ADB 或重试不明确的 Web 命令。Web 桥唯一临时结果文件的创建和删除是仅有的设备侧写入，清理不确定时保留原脚本警告与精确路径；没有 shell 证明时不生成冒充成功的快照。

## 快照内容与解释

每次运行保留 `<label>/<UTC时间戳>/snapshot.json` 与 `summary.md`，不覆盖历史。新建输出目录内自动放忽略规则，快照目录权限 0700、文件 0600；这些仍是本地诊断资料，不默认上传或入库。

JSON `schema_version=1`：

- `device`：用户标签、型号、当前网络 endpoint（不是设备序列号）、shell UID、连接来源与警告。
- `started_at` / `finished_at` / `duration_seconds`：Mac UTC 采样窗口；`probes` 还记录每条命令采样时间与耗时。最多 4 个独立只读查询并发，**不是原子采样**。
- `metrics`：白名单系统属性（Android/API、固件、安全补丁、平台）、内核版本、uptime、逻辑 CPU 数、load、内存与 swap、`/data` 容量、电池、thermal HAL 状态、CPU/内存/IO 的 PSI some avg10/60/300。
- `probes`：命令、真实 `returncode`（超时为 null）、错误、状态与缺字段；`errors` / `missing_metrics` 为汇总。字段缺失为 null，不补零；不保留整段成功命令输出。
- `status`：complete 或 partial 是**采集完整性**，不是设备健康评级；错误和 HAL 缺失都不能被“命令退出 0”掩盖。

单位：`*_kib` 为 KiB；摘要转换成 GiB；uptime 为秒；电池温度为 °C；load 是运行队列指标而非 CPU 百分比；PSI avg 是窗口内停顿百分比（some），不是 CPU 使用率。电池状态保留 Android 原始枚举（如 status=2 充电、3 放电；health=2 GOOD），不据此估计寿命。

默认不收集账号、学习内容、序列号、截图、进程/应用使用清单、全量属性、网络凭据、整机日志或 bugreport；没有日志开关。CPU/GPU 测温、摄像头、触控、音视频与负载测试不在本工具覆盖内。HAL Ready=false 时额外记录热指标不可用，不能据 Thermal Status=0 宣称温度正常，也不能据 HAL false 判定硬件坏了。

## 手动复采与对比

用户按需要手动运行 `collect`，尽量保持充电、前台应用、空闲时长和操作负载相近，然后 `compare OLD NEW`；工具不创建 cron/launchd/Orca automation，也不自动清理历史。

对比突出已变的指标与数值差（NEW−OLD），附两次错误/缺失，版本变化和 uptime 下降单独提示。标签或型号不同会提示跨设备、禁止给资源差值；相同标签/型号只是**同设备候选**，不读取硬件标识，因此无法识别同型号设备被误用同一标签。固件变化时可看原值与差值，但不能把差异直接归因为性能退化。

不要用一条 load、MemFree 或 PSI 的变化直接宣告故障；结合 MemAvailable、可用 `/data` 空间及可复现症状。只读 `/system`、`/vendor` 不参与容量告警，不把镜像占满当用户数据盘满。对比路径全部离线读取，不需要设备仍在线。

## 退出码

| 代码 | 意义 |
|---|---|
| 0 | 连接验证通过 / 快照 complete / 同设备候选对比成功（即使快照本身 partial） |
| 1 | 连接或身份未验证、文件读写/解析失败；详见 stderr，不宣布成功 |
| 2 | CLI 参数错误 |
| 3 | collect 已保存 partial 快照；或 compare 标签/型号不同并省略差值 |

不要用 `collect ... && compare ...` 把 partial 快照排除在历史之外；看到 3 仍保留 JSON 与摘要。固件变化只给解释警告，不自动触发维修、清理内存或改变系统配置。

## 最小验证

```bash
python3 -m unittest discover -s .agent/skills/iflytek-learning-tablet/tests -v
python3 .agent/skills/skill-creator/scripts/quick_validate.py .agent/skills/iflytek-learning-tablet
```

单元测试覆盖属性/监听端口选择、错误身份、Web 超时不重发、connected 不等于成功、部分采集与隐私白名单、跨设备/固件与缺指标对比。真机验证只连接并采集两份快照，观察真实缺失项；不得为了测试错误语义去关闭权限、断网或修改设备。

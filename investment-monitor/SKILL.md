---
name: investment-monitor
description: 每日指数估值自动监控与低估提醒。每个工作日定时拉取蛋卷估值（沪深300/中证500/中证红利/创业板/科创50/恒生/恒生科技/标普500/纳指100）+ QDII ETF 场内溢价，按 PE 百分位分区，状态变化（新进入/离开低估、进入高估、溢价跨阈值）时飞书 DM 通知。当用户提到估值监控、每日估值、低估提醒、估值告警、QDII 溢价提醒、调整监控指数/阈值/通知时间、查看监控状态或快照时触发。即使用户只说"监控还跑着吗"、"加个指数到监控里"、"今天有提醒吗"也应触发。需要交互式深度估值分析（估值地图/建仓建议/写报告）时用 investment-analyzer，本 skill 只管无人值守的每日检测与提醒。
---

# 每日估值监控 (investment-monitor)

无人值守的估值哨兵：**工作日 18:00** 自动跑一遍，发现低估机会或高估风险时飞书 DM 推送，无变化则静默。深度分析（估值地图、建仓建议、月度报告）交给 `investment-analyzer` skill，本 skill 不重复。

## 架构

```
Windows 任务计划 (工作日 18:00)
  → run_investment_monitor.ps1   (C:\Users\admin\.violoop\workspace\, 设 FEISHU_APP_SECRET, 密钥不入库)
  → daily_valuation_check.py     (本 skill scripts/, 实际运行 .violoop 部署副本)
      ├─ 蛋卷估值 API → PE/PB 百分位分区
      ├─ akshare 东财 → QDII ETF 溢价 (可选, 失败不阻塞)
      ├─ 与 data/monitor_state.json 对比 → 状态变化事件
      ├─ 飞书 bot DM 通知 (仅变化时; --force-notify 强制)
      └─ data/valuation_YYYY-MM-DD.md 每日快照
```

## 部署与文件位置

| 角色 | 路径 |
|---|---|
| 源码（编辑这里） | `.claude/skills/investment-monitor/`（skills submodule，用 git-tool 提交） |
| 运行副本 | `C:\Users\admin\.violoop\skills\investment-monitor\`（git pull 同步） |
| 数据/状态 | 运行副本下的 `data/`（`monitor_state.json` + 每日快照，不入库） |
| 密钥 wrapper | `C:\Users\admin\.violoop\workspace\run_investment_monitor.ps1` |

部署流程：`.claude/skills` 改 → `git-tool commit skills` 推送 → `git -C C:\Users\admin\.violoop\skills pull`。

## 常用运维

```powershell
cd C:\Users\admin\.violoop\skills\investment-monitor\scripts

# 手动跑一次（正常变化检测 + 通知）
python daily_valuation_check.py

# 强制发送今日全览到飞书（验证通知链路）
python daily_valuation_check.py --force-notify

# 只落盘不通知
python daily_valuation_check.py --no-notify
```

查看最新快照：`data\valuation_<今天>.md`；查看监控状态：`data\monitor_state.json`。

## 调整监控项

全部配置在 `scripts/daily_valuation_check.py` 顶部，改完走部署流程生效：

- `WATCHLIST`：指数清单（值必须是蛋卷 API 里的确切指数名，exact match）
- `QDII_ETFS` / `PREMIUM_ALERT`(5%) / `PREMIUM_OK`(2%)：溢价监控与阈值
- 分区标准：`<10%` 极度低估 / `10-30%` 低估 / `30-60%` 合理 / `60-80%` 偏贵 / `>80%` 高估——与 `investment-analyzer/references/估值判断标准.md` 保持一致，两边要同步改

## 定时任务

任务名 `InvestmentMonitor-DailyValuation`，工作日 18:00。重建命令：

```powershell
schtasks /create /f /tn "InvestmentMonitor-DailyValuation" `
  /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\admin\.violoop\workspace\run_investment_monitor.ps1" `
  /sc weekly /d MON,TUE,WED,THU,FRI /st 18:00
```

查运行记录：`schtasks /query /tn "InvestmentMonitor-DailyValuation" /v /fo list | findstr "结果 时间"`。

## 故障排查

| 现象 | 排查 |
|---|---|
| 没收到通知 | 先确认当天是否真的无状态变化（看快照文件）；再用 `--force-notify` 验证飞书链路 |
| 飞书发送失败 | `FEISHU_APP_SECRET` 是否在 wrapper ps1 里设了；open_id 走 `192.168.2.13:5000` 内网 API，连不上时检查网络/VPN |
| 指数缺失告警 | 蛋卷改名或下线了该指数，浏览器开 `https://danjuanapp.com/djapi/index_eva/dj` 核对名称后改 `WATCHLIST` |
| QDII 溢价一直失败 | akshare 接口抽风常见，升级：`pip install --upgrade akshare`；不影响估值监控主流程 |
| 首日运行没通知 | 正常。首日只建基线（state 为空时不产生"变化"事件），第二天起才有对比 |

## 已知局限

- 蛋卷估值不覆盖中证A500、道琼斯（API 全量仅 60+ 指数），要监控需换数据源
- 蛋卷百分位是自家口径（约 10 年窗口），与理杏仁/且慢会有差异——趋势可信，绝对值别跨平台比
- 美股指数数据滞后一天（蛋卷用前一交易日美股收盘），A股/港股为当日
- akshare 的 IOPV 是盘中估值，18:00 跑时接近收盘值，仅作溢价参考

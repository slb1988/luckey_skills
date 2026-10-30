---
name: kimi-stat
title: Kimi 额度批量巡查
description: 批量查询 keys.txt 里全部 Kimi for Coding key 的 5 小时与 7 天窗口用量，生成 HTML 报告并用默认浏览器自动打开。用户说 kimi 额度、kimi 用量、kimi-stat、查 kimi key、额度报告、kimi 还剩多少时触发。
tags: [Kimi, Quota, Report, Personal-Tool]
---

# Kimi 额度批量巡查

> Tier 3 — 个人私有 workflow skill（`sunlaibing`）

一条命令跑完「批量探测 → 生成报告 → 打开浏览器」全流程，脚本与 key 清单在 `.claude\scripts\`。

## 执行流程

```bash
cd ".claude/scripts" && py kimi_quota.py -f keys.txt --html --open
```

- `--html`：在 scripts 目录生成 `kimi_quota_report_YYYYMMDD-HHMMSS.html`（文件名自动追加时间戳）
- `--open`：生成后自动用默认浏览器打开（`os.startfile`）
- 控制台同步打印每个 key 的用量进度条，末尾输出 `HTML 报告: <绝对路径>` 一行

跑完按下方口径把控制台结果速读汇总给用户。

## 汇总口径

**先报对比与预测**（控制台尾部摘要 / HTML 头部「对比与预测」面板，两者同源）：

1. **新增耗尽**：较基线新撞 100% 的 key，点名
2. **撑不到重置**：按净消耗速率线性外推 ETA < 重置时间的 key，按 ETA 从早到晚逐个点名（含速率 pp/天）
3. **可撑到重置 / 回落持平**：只报数量
4. 再按 7 天窗口用量分档（下表）

| 档位 | 判定 | 汇报动作 |
|------|------|----------|
| 已耗尽 | = 100% | 报数量与重置日期（通常集中在一两天） |
| 偏高 | ≥ 80% | 逐个点名，提醒省着用 |
| 正常 | < 80% | 只报数量，点名用量最低的几个（优先用它们） |

5 小时窗口一般 < 10%；有 ≥ 50% 的单独点名。

## 对比与预测机制

- **历史快照独立存放** `.claude/scripts/kimi_quota_history.jsonl`（与 HTML 报告分离，一次探测一行 JSON：`{ts, keys{mask:{nickname,h5,d7,d7_reset}}}`），方便直接差分；每次探测自动追加
- **基线选择**：最近一次 ≥2h 前的快照（短间隔噪声太大，不用于外推），基线时间显示在控制台摘要和 HTML 头部面板
- **预测方法**：7 天窗口按两次探测间净消耗速率（pp/天）线性外推耗尽 ETA，与 reset_time 比较得出「撑不到重置 / 可撑到重置」；Δ≤0 判「回落/持平」（滚动窗口吐出旧用量）；间隔 <30 分钟只显示 Δ 不预测。7 天是滚动窗口，外推仅供参考
- HTML 报告头部固定放「对比与预测」面板，每张卡片 7 天进度条下带一行对比明细

## 可选参数

| 参数 | 作用 |
|------|------|
| `--html <路径>` | 自定义报告输出位置（仍自动追加时间戳） |
| `--include-pi` | 顺带查询 pi auth.json 里的 kimi-coding key |
| `--no-save` | 本次结果不写入历史快照（临时查个别 key 时建议带上，避免污染基线） |
| `--baseline-gap <小时>` | 对比基线最小间隔，默认 2.0 |
| `--import-html <报告...>` | 把旧 HTML 报告解析导入历史快照后退出（history 丢失/换机重建用，按生成时间幂等去重） |
| 位置参数 `sk-kimi-...` | 只查指定 key，绕过 keys.txt |
| `kimi_quota.bat %*` | 人工双击用；自动化一律直接调 py（bat 末尾有 `pause`） |

## 注意事项

- keys.txt 与报告含 masked key，报告 HTML 不外发
- 8 线程并发探测，50+ key 约 10 秒返回；个别 key 失败会在报告中标 ✗，属网络波动，重跑一次即可
- 换电脑或路径变动时，先确认 `.claude\scripts\kimi_quota.py` 与 `keys.txt` 存在；历史快照 `kimi_quota_history.jsonl` 丢失时用 `--import-html` 从存量 HTML 报告重建

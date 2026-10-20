---
name: dawarich-commute
description: 从 Dawarich 位置追踪服务（NAS 10.77.77.6:3000）分析每日通勤情况：上下班出发/到达时间、通勤用时、路程公里数，家/公司锚点取 web 端 Places。当用户提到通勤、每日通勤、上下班时间、通勤用时、几点出门/几点到家、dawarich、轨迹分析、今天/这周通勤时触发。即使用户只说"看看今天通勤"、"这周上下班花了多久"、"昨天几点到家的"也应触发。
---

# Dawarich 每日通勤

从 Dawarich（自托管位置追踪，部署在 NAS `http://10.77.77.6:3000`）的轨迹点计算每日通勤：早/晚通勤的出发与到达时间、用时、路程，周末/未通勤日降级为外出识别。

## 使用

脚本：[`scripts/dawarich_commute.py`](scripts/dawarich_commute.py)（Python 3 标准库，无第三方依赖）

```bash
python .claude/skills/dawarich-commute/scripts/dawarich_commute.py --selfcheck   # 验证 key 与连通性
python .claude/skills/dawarich-commute/scripts/dawarich_commute.py               # 今天
python .claude/skills/dawarich-commute/scripts/dawarich_commute.py 2026-10-19    # 指定日期
python .claude/skills/dawarich-commute/scripts/dawarich_commute.py --days 7      # 最近 7 天逐日
python .claude/skills/dawarich-commute/scripts/dawarich_commute.py --json        # 结构化输出（接日报等下游）
python .claude/skills/dawarich-commute/scripts/dawarich_commute.py --probe       # 导出 stats/timeline/visits 原始响应
python .claude/skills/dawarich-commute/scripts/dawarich_commute.py --dump        # 导出轨迹点原始 JSON
```

排障时先看 `--selfcheck`；服务不通先怀疑 WireGuard 隧道（10.77.77.x 网段多处同时失败 = WG 断）。

## 配置

读取顺序：进程环境变量 → skill 目录 `.env` → 仓库根 `.env`（项目惯例放仓库根，模板见 [.env.example](.env.example)）。

| Key | 说明 |
|---|---|
| `DAWARICH_API_KEY` | 必填。Dawarich web → Settings → API key |
| `DAWARICH_BASE_URL` | 默认 `http://10.77.77.6:3000` |
| `DAWARICH_RADIUS_M` | 可选。锚点半径，默认 300 米 |

**家/公司锚点不在本地存坐标**：取自 web 端 Places（名称 `home`/`家` → 家，`公司`/`work` → 公司），
搬家/换公司直接改 web 端。Places 缺失时才自动检测（跨范围夜间/白天中位数），命令行 `--home/--work` 可临时覆盖。

## 输出口径（解读时给用户讲清）

- 早通勤 = 最后一个在家点 → 第一个在公司点；晚通勤 = 最后一个在公司点 → 第一个到家点
- `≈（中间最长 N 分钟无轨迹）`：iOS 显著变化模式在室内不产生轨迹点，稀疏日期的用时/路程是下限估计，路程比真实值偏低（实测 ~25%）
- 「出门早于轨迹起点」「离开公司时间落在轨迹空洞里」= partial 段，从最近可观测点起算，时间不编造
- 周末/未去公司：降级输出「外出 HH:MM 离家 → HH:MM 回家」或「全天在家范围内」

## References

- [`references/api.md`](references/api.md) — Dawarich API 契约：认证、points 分页、Places/Visits/Timeline 端点、swagger 位置、iOS 数据特征
- [`references/algorithm.md`](references/algorithm.md) — 锚点检测、通勤段识别、稀疏数据处理、WGS-84/GCJ-02 坐标系差异（地图核对偏 ~490m 的原因）

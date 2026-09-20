# 定时自动执行（Orca Automation）

daily-report 除手动触发外，还由 Orca automation 定时自动执行。

## Automation 配置

- **名称/id**：`daily-report 工作日报` / `fbe8b4d8`（建于 2025-09-20）
- **调度**：工作日 23:58（RRULE `BYDAY=MO-FR`，Asia/Shanghai）；错过宽限 5 分钟，基本不补跑——避免跨午夜补跑写出错误日期的日记
- **执行体**：pi agent，ObsidianVault 主 worktree（`workspaceMode: existing`，不另建 worktree）
- **手动操作**：`orca automations run fbe8b4d8`（手动触发一次）、`orca automations runs fbe8b4d8`（运行历史）

## 双层「无工作则跳过」机制

1. **precheck 门禁**（[../scripts/workday_precheck.py](../scripts/workday_precheck.py)）：automation 先跑此脚本，exit 0 才启动 agent，exit 1 记一条 skipped run——不烧 LLM token。命中任一即 exit 0：
   - 三台 P4 服务器当天有本人 submitted CL（任一服务器；连接失败不视为证据）
   - ActivityWatch 当天 `not-afk` 累计活跃 ≥ 2 小时（有工作但没提交的日子）
2. **prompt 兜底**：agent 启动后若三路数据源（飞书/AW/P4）皆空，不建日记文件。

## ⚠️ 同步约束

precheck 脚本**复制了** SKILL.md Step 3 的 P4 服务器/用户/charset 表和 Step 2 的 AW bucket 命名约定（`aw-watcher-afk_<hostname>`）。修改 SKILL.md 中这些口径时必须同步更新脚本，否则门禁与正式采集口径不一致（该生成的日子被跳过，或反之）。

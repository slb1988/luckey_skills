# 定时自动执行（Windows 计划任务）

daily-report 除手动触发外，由 Windows 计划任务定时自动执行。

> **2026-10-10 起从 Orca automation 迁出**。原 Orca automation（`daily-report 工作日报` / `fbe8b4d8`，已停用保留历史）以交互式 TUI 拉起 pi：无人值守时段（23:59/04:00，锁屏/待机） pi TUI 进程在结束阶段 exit 1，Orca 一律记为 `dispatch_failed`（「Automation process exited with code 1」）——**全是假失败，日报实际已生成**；白天有人值守时手动/定时触发均正常 completed。Orca 的 pi provider 不支持 `--extra-agent-args`（无法加 `-p` 转无头），故迁到计划任务 + headless `pi -p`，退出码即真实成败。同机在跑的 `PL Daily Report`、`RagFlow 全量同步` 两个 pi automation 存在同样问题，尚未迁移。

## 当前机制

- **计划任务**：`DailyReport-ObsidianVault`（工作日 23:59，不补跑），Action 为
  `wscript.exe run_hidden.vbs → powershell -File run_scheduled.ps1`（无窗口包装，沿用 SkillIndexPatrol 同款）。
- **runner**：[../scripts/run_scheduled.ps1](../scripts/run_scheduled.ps1)——
  1. 跑 precheck 门禁，无工作证据则记 `skipped` 退出 0（不烧 token）
  2. `pi -p`（stdin 读 [../scripts/scheduled_prompt.txt](../scripts/scheduled_prompt.txt)，规避多行/引号转义）跑日报全流程
  3. 日志写 `skills/daily-report/logs/run_<timestamp>.log`（含 precheck 结果、pi 全程输出、退出码），保留 60 天
- **手动验证**：`Start-ScheduledTask DailyReport-ObsidianVault`，然后看 logs 目录最新文件；真跑一周无误后可删 Orca 侧停用条目。

## 「无工作则跳过」门禁

precheck（[../scripts/workday_precheck.py](../scripts/workday_precheck.py)）exit 0 才启动 pi。命中任一即 exit 0：

- 三台 P4 服务器当天有本人 submitted CL（任一服务器；连接失败不视为证据）
- ActivityWatch 当天 `not-afk` 累计活跃 ≥ 2 小时（有工作但没提交的日子）

prompt 兜底：agent 启动后若三路数据源（飞书/AW/P4）皆空，不建日记文件。

## ⚠️ 同步约束

precheck 脚本**复制了** SKILL.md Step 3 的 P4 服务器/用户/charset 表和 Step 2 的 AW bucket 命名约定（`aw-watcher-afk_<hostname>`）。修改 SKILL.md 中这些口径时必须同步更新脚本，否则门禁与正式采集口径不一致（该生成的日子被跳过，或反之）。prompt 改了要同步 `scheduled_prompt.txt`。

## 已知数据缺口：AW window watcher 静默死亡

aw-watcher-window 曾 2026-09-23 起崩溃后不再出数（aw-qt 不会拉起死掉的 watcher），直到 2026-10-10 重启机器才恢复，期间 17 天日报无 App 使用时长表。watcher 是否存活可看 `aw-watcher-window_<hostname>` bucket 当日事件数；如需根治可加 watchdog 计划任务（检查进程存在性，缺失则重启 aw-qt）。

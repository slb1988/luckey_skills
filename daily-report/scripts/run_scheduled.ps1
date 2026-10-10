# daily-report 定时任务入口（工作日 23:59，Windows 计划任务以 run_hidden.vbs 无窗口包装调用）
# 从 Orca automation 迁出：Orca 以交互式 TUI 拉起 pi，无人值守时段（锁屏/待机）pi 进程 exit 1
# 导致所有调度 run 误标 dispatch_failed；headless pi -p 无 TUI，退出码真实反映成败。
#
# 退出码：precheck 无工作证据 → 0（日志记 skipped，不算失败）；pi 失败 → 透传非 0。
$ErrorActionPreference = 'Continue'
$root = 'D:\Github\ObsidianVault'
$skillDir = Join-Path $root '.claude\skills\daily-report'
$logDir = Join-Path $skillDir 'logs'
$null = New-Item -ItemType Directory -Force -Path $logDir
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$log = Join-Path $logDir "run_$stamp.log"

# 清理 60 天前的旧日志
Get-ChildItem $logDir -Filter 'run_*.log' | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-60) } | Remove-Item -Force

"=== $stamp daily-report scheduled run ===" | Out-File $log -Encoding utf8

# 1) precheck 门禁（与 SKILL.md Step 2/3 口径同步，见其头部注释）
"--- precheck ---" | Out-File $log -Append -Encoding utf8
& python (Join-Path $skillDir 'scripts\workday_precheck.py') *>&1 | Out-File $log -Append -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    "precheck exit $LASTEXITCODE -> skipped" | Out-File $log -Append -Encoding utf8
    exit 0
}

# 2) headless 跑 pi（stdin 传 prompt，规避命令行多行/引号转义；UTF8 输出编码防中文乱码）
"--- pi -p ---" | Out-File $log -Append -Encoding utf8
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $root
$prompt = Get-Content (Join-Path $skillDir 'scripts\scheduled_prompt.txt') -Raw -Encoding UTF8
$prompt | & pi -p *>&1 | Out-File $log -Append -Encoding utf8
$code = $LASTEXITCODE
"pi exit code: $code" | Out-File $log -Append -Encoding utf8
exit $code

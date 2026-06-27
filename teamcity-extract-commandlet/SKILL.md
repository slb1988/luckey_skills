---
name: teamcity-extract-commandlet
description: 从 TeamCity 构建日志中提取 UE commandlet 命令行（如 WP_BuildMinimap / WorldPartitionMiniMapBuilder 等 WorldPartition 构建任务）。当用户发来一个 TeamCity 构建链接（http://192.168.2.13:8111/buildConfiguration/...）并想"复现这个构建""找到对应命令行""这个任务跑的什么命令""提取 commandlet 参数""转成 Visual Studio 调试参数"时触发。即使用户只说"这个 build 跑的啥""帮我看下这个 WP_Build"也应触发。输出原始命令 + 可直接粘贴到 VS 项目属性 Debugging → Command Arguments 的本地化参数。
---

# TeamCity → UE Commandlet 命令行提取

把一个 TeamCity 构建链接，变成「可在本地 Visual Studio 复现的调试命令行」。

## 何时用
用户给出形如 `http://192.168.2.13:8111/buildConfiguration/<CFG>/<BUILDID>?buildTab=log...`
的链接，想知道该构建实际执行的 UE commandlet（`-run=...Commandlet -builder=...`），
并希望在本地机器（如 WinBuilder3）复现 / 调试。

## 前置条件
- Secret `TC_AGENT_MONITOR_TOKEN` 已存在（TeamCity API Bearer token，exec_command 自动注入为环境变量）。
- 本机可访问 TeamCity `http://192.168.2.13:8111`（webfetch 会因登录页失败，必须走 REST API + token）。

## 核心流程（一条命令搞定）

运行脚本，传入 URL（或 -BuildId）。要本地化 uproject 路径就加 -LocalRoot：

```powershell
& 'C:\Users\admin\.violoop\skills\teamcity-extract-commandlet\scripts\extract_commandlet.ps1' `
  -Url "<粘贴TeamCity链接>" `
  -LocalRoot "C:\WinBuilder3_MainDev_Sandbox"
```

输出包含：
- `BuildId / Config / Number / Agent` — 构建上下文（用于核对分支/agent）
- `RawCommand` — 日志里那行原始命令（含构建机的绝对路径，如 E:\WinBuilder1_Rel-0.2\...）
- `VsArgs` — **可直接复制**到 Visual Studio：项目右键 → 属性 → Configuration Properties → Debugging → Command Arguments。
  uproject 路径已替换为 `-LocalRoot\Main\<Project>.uproject`，其余参数原样保留。

不传 `-LocalRoot` 时 `VsArgs` 保留日志原始 uproject 路径。

## 提取原理
- 用 REST `app/rest/builds/id:<BuildId>` 取元数据（Config/Number/Agent）。
- `downloadBuildLog.html?buildId=<BuildId>` 下载完整日志到 `%TEMP%\tc_<id>.log`。
- 正则匹配 `UnrealEditor(-Cmd)?.exe ... -run=\w+Commandlet ...` 那行（TeamCity 会 `[echo]` 出完整命令）。
- VS Command Arguments = exe 之后的全部参数（即 `<uproject> <map> -run=... -builder=...`）。

## 输出给用户的格式
1. 先报构建上下文一行：`Build <number> @ <agent>，config <cfg>`。
2. ⚠ **分支核对**：若 Agent/路径所属 stream（如 Rel-0.2）与用户目标本地分支（如 MainDev）不一致，必须提醒"分支不一致"，让用户确认是否继续（这是用户的硬性规则）。
3. 给出 `RawCommand`（代码块）。
4. 给出 `VsArgs`（代码块，标注"粘贴到 VS Debugging → Command Arguments"）。

## 已知坑
- `webfetch` 取 TeamCity 页面只会拿到登录页 → 必须用 token 走 REST API。
- `Invoke-WebRequest` 在 PowerShell 下会刷一堆"正在写入请求流"进度噪音，是正常的，看末尾结构化输出即可。
- 不同构建的 commandlet 不一定是 MiniMap：脚本按通用 `*Commandlet` 匹配，WorldPartitionHLOD / Navigation 等同样适用。

## 不要做的事
- 不要试图从本机 `p4 -c <远程client> sync`：远程 client 的 root 在远程机磁盘上，本地 sync 会写错机器并污染该 client 的 have-list。同步必须在目标机（如 WinBuilder3）本地执行。
- RDM 内嵌会话当前无法被本工具注入键鼠焦点（输入会落到本机），所以「在 WinBuilder3 上同步 + 改 VS 参数」需用户手动或会话置于全屏聚焦态后再试。本 skill 只负责"提取命令行"这一可靠环节。

# 查询、清单与执行要点

在正确的工作区执行 VCS 命令；路径来自本轮 workspace_resolve。以下是模板，不是可直接执行的固定环境配置。

## P4 源/目标核实

```text
p4 -C none where Engine/Plugins/Angelscript/...
p4 -C none changes -s submitted -m 1 <实际插件depot路径>/...
p4 -C none changes -s submitted -u sunlaibing -m 1 <实际插件depot路径>/...
p4 -C none opened <实际插件depot路径>/...
p4 -C none sync -n <实际插件depot路径>/...
p4 -C none fstat -T depotFile,headRev,haveRev,headChange,headAction <实际插件depot路径>/...
```

这里 `-C none` 来自 2026-11-04 MainDev 实测，未来以当前服务器要求为准；Unicode 服务器可能要求 `utf8`，不能跨环境硬套，也不要改变全局 charset。client stream 名称不一定就是文件 depot 路径，以 `where` 为准。

设上次完整成功同步的 CL 为 `BASE_CL`，本次固定截止为 `END_CL`；起点为 `BASE_CL + 1`。查询该范围 submitted changes，再从各 CL 的 describe 中筛选插件路径并去重：

```text
p4 -C none changes -s submitted <depot/...>@<BASE_CL+1>,<END_CL>
p4 -C none describe -s <CL>
p4 -C none files <depot/...>@<END_CL>
```

本地文件必须匹配所选快照。若 have 落后、源有 opened/本地差异，或 depot 在收集过程中更新，不要边追 head 边复制；固定版本后重新收集必要部分，或先确认源快照。`sync -n` 不检查未打开文件的离线修改，必要时用只读 `p4 diff -se/-sd` 或内容对照核实。

配套 GAS 文件逐个查询，不把其所在目录的所有变动自动并入主范围。`p4 changes` 以全体作者查完整性，`-u sunlaibing` 用于定位个人变更；文件历史出现后续修订时迁移选定版本，不拼接多个旧版全文件。

## Git 查询

```text
git rev-parse HEAD
git status --short --untracked-files=all -- Engine/Plugins/Angelscript Engine/Plugins/AngelscriptGAS
git diff --name-status -z --no-renames <BASE>..<TIP> -- Engine/Plugins/Angelscript
git diff --name-status -z -- Engine/Plugins/Angelscript
git diff --cached --name-status -z -- Engine/Plugins/Angelscript
git ls-files --others --exclude-standard -- Engine/Plugins/Angelscript
git check-ignore -v -- <清单中在status缺失的文件>
```

使用 `-z` 输出收集文件名，避免空格、Unicode 路径被截断。`--no-renames` 将 rename 表示为明确的 delete/add，两边的路径都纳入清单与冲突检查。

不要只看 `git diff --stat`：它既不列普通 untracked 文件，也不列被忽略文件。对清单中每个应交付的新文件检查 `git ls-files` / `status` / `check-ignore`。

最窄目录的忽略例外示意（只在实际忽略规则允许的层级使用）：

```gitignore
!*.mmd
!*.svg
```

如果父目录本身被排除，需要在能够生效的父级恢复该目录；验证结果，不只写例外。不要取消整个引擎的产物忽略规则。

## 逐文件清单

清单至少包含以下信息；格式可用 JSON/TSV，不强制创建大型报告：

```json
{
  "direction": "maindev -> unrealengine-angelscript",
  "source_snapshot": {"vcs": "p4", "submitted_cl": "本次固定截止CL"},
  "entries": [
    {
      "path": "Engine/Plugins/Angelscript/Source/AngelscriptCode/Public/AngelscriptCodeModule.h",
      "action": "modify",
      "source_revision": "depotFile#rev",
      "source_sha256": "复制前计算",
      "target_before_sha256": "复制前计算",
      "reason": "指定范围的已提交增量"
    }
  ]
}
```

只接受根目录内的相对路径，拒绝绝对路径和 `..` 逃逸。确认冲突已解决且源/目标未漂移，再按清单在一个执行批次复制全部 add/modify；不要递归复制一个新目录而把其中缓存一起带上。delete 用目标 VCS 正确操作，preserve/exclude 不动。哈希对照在复制后进行；若要合并，记录实际结果而非强求覆盖成源字节。

Git→P4 使用独立 numbered pending CL：

```text
p4 -C none change
p4 -C none -x <现存文件精确清单> edit -c <本次CL>
# 一批复制之后，新增文件按精确清单 add，删除项按清单 delete。
p4 -C none -x <新增文件精确清单> add -c <本次CL>
p4 -C none -x <删除文件精确清单> delete -c <本次CL>
p4 -C none opened -c <本次CL>
```

按实际 checkout/add/delete 时机调整，不允许未纳入清单的用户文件混入。既有目标文件属于其他 pending CL 时停止处理该文件并确认，不自动 reopen 到本次 CL。

## 构建与退出码

在目标目录用适合当前 shell 的入口。例如 Windows PowerShell：

```powershell
& .\Engine\Build\BatchFiles\Build.bat UnrealEditor Win64 Development -WaitMutex -NoHotReload *> $LogPath
$BuildExitCode = $LASTEXITCODE
# 再读取日志，报告 $BuildExitCode 和真实 Result；不要用格式化/截断命令的退出码代替。
```

Bash 不接受 Windows cmd 的 `cd /d`；Git Bash 用实际可访问路径 `cd /d/...`，或调用 PowerShell。不要把 `cmd /c` 的 MSYS 参数转换问题误判成编译失败。

复制更新 mtime，防止 UHT 继续使用行号布局已过时的 generated header。若编译失败，先读第一条根因及其上下文，不要仅盯着末尾成批的 `GENERATED_BODY` 语法错误。修复直接相关问题后重建目标；相邻范围扩大需证据。

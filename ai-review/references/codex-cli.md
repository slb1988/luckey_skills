# Codex CLI 评审入口

仅在已经选定 Codex 作为评审入口时使用。用户说“评审 Codex 的结果”不表示 reviewer 也是 Codex；评审者选择与权限以 [AI Review](../SKILL.md) 为准。

## 本地直跑

先确认当前环境存在 Codex CLI、登录状态可用，并查看版本匹配的帮助；不写死可执行文件的绝对路径，也不假设任何机器都已登录。

```bash
codex exec review --help
```

在正确的 Git 仓库根目录按范围选择一种调用：

```bash
# staged + unstaged + untracked；相关范围先由 coordinator 确认
codex exec review --uncommitted

# 相对指定分支的改动
codex exec review --base <branch>
```

- `--uncommitted` 与自定义 PROMPT 互斥，不把两者拼在一次调用里。其他参数组合也以当前 CLI 帮助为准。
- 需要自定义重点、限定文件或评审 P4 CL 时，使用当前工具支持的通用 prompt 入口并显式传入范围、基线和实际证据；不能只删掉 `--uncommitted` 就假定仍审同一批未提交改动。
- 若当前版本支持 stdin prompt（如 `codex exec review -`），先核实其范围语义；不把 Git 专用 review 的默认行为套用到 P4。
- reviewer 的实际模型从 CLI 配置/运行结果确认；指定模型时使用该版本支持的选项。不能把 Kimi 的任意模型别名塞给 Codex 并假定可用。
- 保留评审结论与必要运行证据，但不在报告中输出认证信息。失败、空输出或中断明确标记未完成，不能当作零发现。

独立窗口或跨 workspace 执行时，使用主 skill 的 Orca 路径；通用流程不依赖本入口。

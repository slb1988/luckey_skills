# 环境凭证与 Git 安全边界

| 保护层 | 判定依据 | 不覆盖什么 |
|---|---|---|
| Agent 读取 Guard | 工具参数中的受保护路径；`keys` / `pipe` / `git-check` 三种固定操作 | 不是操作系统沙箱，也不改变 Git 索引 |
| Git 忽略规则 | 每个仓库独立的 `.gitignore` / `info/exclude` | 不会让已跟踪文件自动退出索引 |
| 提交前元数据检查 | 真实环境文件的跟踪、暂存和忽略状态 | 不扫描历史，不自动拦截后续的手动 push |

## 固定入口

安装了读取 Guard 时，Git 操作先使用：

```bash
python ~/.agent-hooks/env-read-guard/guard.py git-check --repo <目标库> --recursive
```

只返回 JSON 路径和布尔状态，不读取文件内容；当前工作目录已是目标仓库时可省略 `--repo`。`--recursive` 按 gitlink 逐库检查，父库的忽略规则不代替 submodule 自己的规则。未初始化子模块会明确报未检查。

- 返回 `0` 才继续提交；`1` 是风险或未完整检查，`2` 是查询失败。
- `ignored=true` 且 `tracked=true` 仍必须停止：忽略规则不能阻止已跟踪内容提交。
- 取消跟踪应保留本地文件，仅从索引移除；暂存删除可以通过，不会修改历史。已有历史如含真实凭证，应轮换；不得自行强推重写历史。
- `.env.example` / `.env.sample` / `.env.template` 是文件名例外，不是内容安全证明；它们只能含占位符。
- 普通代码与未追踪 scratch 文件仍要单独检查硬编码密钥，只报告路径和结论，不回显疑似密钥。调试工具使用环境变量，不把带真实凭证的临时文件入库。

`git-tool-commit.sh` 不会自动安装或调用 Guard。Guard 未安装时，先安装或使用受控的等价 Git 元数据检查，不能跳过检查后直接全量暂存。安装源码位于 ObsidianVault 的 `.claude/hooks/env_read_guard/`，功能文档是 `.claude/AutomationDocs/Hook/ENV_READ_GUARD.md`。

## 忽略规则

自有仓库使用可共享的规则：

```gitignore
.env
.env.*
!.env.example
!.env.sample
!.env.template
```

第三方只读 submodule 可使用自身 Git 目录中的 `info/exclude`；它仅对本地克隆生效，不会随父库提交传播。

基础文件名探针和当前实际路径检查不能证明所有未来目录的规则；暂存前与提交前应分别核验，避免中间索引变化。只做 Git 操作时不使用 `keys` / `pipe`，也不把被拦的 Shell 命令改写成路径拼接或临时脚本。

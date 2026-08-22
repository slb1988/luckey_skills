# Memory Hub 排障与调试参考

> 从 SKILL.md 移出的排障/调试条目。部署、启动、备份类运维见 [deploy.md](deploy.md)；dashboard 开发/部署见 [dashboard.md](dashboard.md)。

## 检索

### 编辑器内 `memory_search` 0 命中：用 CLI 复现检索链路

编辑器内 `memory_search` 0 命中时，绕过扩展用 CLI 复现：pi/claude 的记忆扩展只是薄封装，实际检索全部在 `scripts/memory_hook.py search`（扩展源码里 grep 不到 project/检索逻辑属正常）。`/usr/bin/python3 scripts/memory_hook.py search "<query>" --project <id> --limit 20 --json` 与编辑器内走同一链路，且 `--project` 可探测当前 cwd 派生 scope 之外的项目（如 agent-history、maindev），`--json` 可看原始返回结构排除展示层问题。

### Graphiti 语义检索的噪音底线（返回非空 ≠ 命中）

Graphiti 语义检索噪音底线高：乱查（大小写无关）也会返回"近似"结果——**返回非空 ≠ 命中，目标不在 top-N ≠ 不存在**。判定"没有这条记忆"前先调大 `--limit`（默认 10）并换关键词重试，再按 project scope 排查。live hook 同样按写入时 cwd 文件夹名派生 project：Windows 端写的记忆散落在 maindev/unity2018/agent-history 等，Mac 端 ObsidianVault 会话默认只能看到 obsidianvault project——跨机器"重启后搜不到"几乎都是 scope 隔离而非故障。

## Hook 与 Pi 扩展

### v4 AFK 防抖的 capture 丢失窗口

v4 AFK 防抖有已确认的丢失窗口（2026-08-21 实测定性）：agent_end 后扩展只写 `capture_schedule`，若进程在防抖计时器到期前被杀——直接关终端**不会触发** `session_shutdown` 兜底——最后一段内容永不 capture。识别特征：pi-trace 末尾是孤立的 `capture_schedule` 且无后续 `capture`。另一观测盲区：capture 链路在 hook 脚本侧完全没有 trace（`trace_event` 只包 search），出现「capture exit 0 但 spool 无 job、objects 无快照、Hub 404」时无法事后定位根因，只能靠 spool × objects × Hub API 三方交叉排除。

### 「hook 是否生效」必须分两层验证

回答「hook 有没有成功安装/生效」必须分两层验证：`install_hooks.py check` 全绿只证明**安装副本与模板一致**
（静态层，且历史上存在过误报 ok 的案例）；运行层证据看 pi-trace.jsonl **最后一条 `session_start`**——其
`ext_version` 与模板版本一致、且时间戳属于当前会话，才证明扩展真的被 pi 加载并正在 firing。check 绿但本会话
trace 无 `session_start` = 扩展未被加载（查扩展路径/加载冲突），两层都过才能回「已生效」。

### 审计本地 session 是否漏传 Hub（三方交叉比对）

审计「本地 session 是否漏传 Hub」的交叉比对法（2026-08-21 全流程验证）：① spool.sqlite3 当日 job 中 `status='completed' AND remote_version IS NULL` = 被 LLM 过滤（skipped_meaningless）——被过滤 job 的 session 早期版本通常已在 Hub，丢的只是最后一次 capture 的尾部增量；② pi-trace 有 capture exit 0 但 spool 无 job = 早退（extraction 子 session 首消息签名 / transcript 从未落盘的「幽灵 session」走 `is_file()` 早退 / 未查明原因）；③ 拿本地 session 文件与 Hub latest 版本核对内容覆盖度。LLM 过滤器只按快照**尾部一对 user/assistant** 判定：以决策讨论/功能确认问答结尾的 session 易被误判低价值（单日实测 2 例误伤），评估过滤质量时重点抽查这类结尾。

### install 后同一 shell 里 check 显示 identity missing 是预期

在刚执行完 install 的**同一 shell** 里跑 `install_hooks.py check --agents auto`，`identity.source` 显示 `missing` 是预期——user-id 环境变量已写入 `~/.profile`/`~/.zprofile` 但当前进程未加载；新开终端或重启 agent 后即正常。不要据此重装或重复 configure。

### Windows 上 hook 全静默 exit 127（模板 python 路径硬编码）

agent-integration.md 的 install/configure 示例命令是 macOS 写法（`/usr/bin/python3`、`/Users/sun/...`）。
Windows 上曾发现扩展配置里原样保留了 `/usr/bin/python3` 这个 Unix 路径导致 hook 无法执行——Pi 扩展模板 v2
把 python 路径硬编码为 `/usr/bin/python3`，Windows 端 spawn 全部 exit 127 静默失败（pi-trace.jsonl 里
recall/capture 全红），且 check 因「副本与模板一致」误报 ok。**v3 起模板改为 `__PYTHON_JSON__` 占位符，
由 install_hooks.py 注入本机解释器路径**（优先 /usr/bin/python3，否则 sys.executable）；老机器 check 报
outdated 后重跑 install 即修复。排查「关窗提示有进程未结束」是否 hook 残留时，按命令行列 python.exe 分辨：
本机常驻 python 通常是 UnrealMCP 和 pytest，与 memory-hook 无关；memory_hook.py 是逐事件短进程，正常不常驻。

### Spool 积压 job 持续 `SCOPE_FORBIDDEN` 不自愈

Spool job 在 capture 时固化 `user_id`（这是设计，防止补传到错误用户）。副作用：身份配置变更（如 install 写入新的 `MEMORY_HUB_CLIENT_USER_ID`）之前积压的 queued job 仍带旧身份，flush 时持续报 `SCOPE_FORBIDDEN` 且不会自愈（实测一次积压 11 个）。看到 spool 反复 403 时直接清理这些旧 job，不要当作服务端权限配置问题排查。

## 测试

### Windows 本机 pytest 稳定 13 个失败（平台性问题）

`scripts/tests/` 在 Windows 本机跑 pytest 稳定有 13 个用例失败（10 passed），失败点全在 tearDown 的 `shutil.rmtree`——spool.sqlite3 文件锁 PermissionError，属 Windows 平台既有环境问题（stash 验证未改动代码同样 13 败），不是 regression。评估改动是否破坏测试时对比改动前后的失败集合；要干净结果去 Linux/macOS 跑。

### macOS 跑 tests 的姿势坑与平台性失败

跑 `scripts/tests/` 的两个姿势坑（macOS 实测）：① `tests/conftest.py`（把 `scripts/` 加入 sys.path）**只在 pytest 下加载**，用 `python -m unittest` 必须 cd 到 `scripts/` 再跑，否则 import 失败；② macOS 上 `test_memory_hook` 同样稳定有 4 个平台性失败（如 `project_id_for_cwd` 的 Windows 路径断言，改动前干净检出复现），与 Windows 的 13 败同理——任何平台都不追求全绿，只对比失败集合差集。

## 批量上传

### Codex 新格式 session（首行 session_meta）解析

Codex 新格式 session 文件首行是 `session_meta` 记录，cwd 与 session uuid 只存在于该行的 payload 内、无法从文件路径推出。旧版 `upload_sessions.py` 不识别该格式时 cwd 全部丢失——实测 238 个 codex session 会全部落入兜底 project 且 session id 退化为文件名；已修补 `scan_session_file` 支持（dry-run 238/238 解析成功）。批量归档不熟悉的来源前，先 `--dry-run` 核对 cwd 解析率和 session id 形态（应为 `{source}:{project}:{uuid}` 三段式）再实际上传。

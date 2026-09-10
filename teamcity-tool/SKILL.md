---
name: teamcity-tool
description: >
  TeamCity server operations: lifecycle, config, LDAP/auth, health, logs, REST API,
  agent matching and build chains. Use for TeamCity/TC server, teamcity-server,
  "restart TeamCity", "check TeamCity logs", "TeamCity config", "LDAP TeamCity",
  "build agent", "teamcity data directory", "build chain", "build queue",
  "no compatible agents", "No agent", "override.dep", "reverse.dep",
  "snapshot dependency", unresolved parameters, or TeamCity UI/login/build/agent issues.
  Covers PL_BuildProjectWindows/PL_BuildUgsBinaries (UAT cook, MinIO),
  DirectoryMap cleaner/192h checkout expiry, PLN_FlowAiReview
  (Sync/Unshelve/BuildUE_Windows; historical BuildUE_Linux; Pi_Agent_Review),
  parameter ownership/resolution, same-agent routing, queue bottlenecks,
  and PLN_TaskAiReview failure notifications (TeamCityLogParserInformer/feishu).
compatibility: linux, bash, ps, grep, find, curl
---

# TeamCity Administration Skill

This skill knows how to operate and troubleshoot TeamCity installations across multiple machines. It uses a host fingerprint system to identify which machine it's running on and loads the appropriate configuration reference.

## Step 0 — Identify the machine

Before doing anything else, determine which host you're on:

```bash
hostname
```

Then read `references/host-fingerprint.md` and match the output to the correct section. This prevents operating on the wrong machine when this skill is deployed to multiple servers.

If the hostname is not found in the fingerprint file, treat it as an unknown machine and discover TeamCity:
```bash
find / -name "teamcity-server.sh" 2>/dev/null
find / -name "teamcity-startup.properties" 2>/dev/null
```

Then read the startup properties to find the data directory (`teamcity.data.path`). Use what you discover — don't assume `/data/TeamCity` is the install or data path.

## Reference files

After identifying the machine, read the corresponding reference file:

| Machine | Reference file |
|---|---|
| `auto-server` | `references/auto-server.md` |

Always read the reference file before acting — it contains the actual paths, ports, and credentials for that specific machine. Do not hardcode paths from the fingerprint table; the reference file is the source of truth.

| Topic | Reference file |
|---|---|
| LDAP setup / auth | `references/ldap-config.md` |
| REST API (queries, parameters, queue) | `references/rest-api.md` |
| Build chain 参数所有权、override/reverse 解析、隐式 Agent 要求、工作区、安全重排与验证（chain 问题先读） | `references/build-chain-parameters.md` |
| Kotlin DSL、VCS/checkout 与链配置补充 | `references/build-chain-lessons.md` |
| Agent 名称正则、白名单与 Pool | `references/agent-pinning.md` |
| Non-obvious traps and gotchas | `references/gotchas.md` |
| 打包管线 (PL_BuildProjectWindows / PL_BuildUgsBinaries / UAT cook) | `references/package-pipeline.md` |
| Checkout 目录自动清理事故 (DirectoryMap cleaner, 192h expiry) | `references/checkout-dir-auto-clean.md` |
| 构建失败排障与重编归因（UE 构建 UBT mutex、Linux/Windows 链全量重编、增量缓存健康判定） | `references/troubleshooting.md` |
| FlowAiReview 管线耗时画像与瓶颈、编译失败归因（sync HEAD 语义 / adaptive unity 盲区 / workspace reset 机制）、后端 busy 门（设计根因 TC 无链级互斥/取单公平性）与降级放行缺陷、unshelve 独占锁、unshelve 吞他人提交（have 回退 + `resolve -am` 空跑/假成功，须 `resolve -N` 复查）、队列停摆诊断 | `references/flow-aireview-pipeline.md` |
| TaskAiReview 失败通知链路（TeamCityLogParserInformer 归因/路由语义、latestCL vs unshelve CL 身份陷阱） | `references/task-aireview-notification.md` |
| AiReview 工具链本地模拟测试（Collect/Runner/Publish 分工、Runner cwd 硬性前置、copyfile SameFileError 根因） | `references/aireview-local-test.md` |

Read the relevant reference before acting on that topic.

## Common workflows

### Service management

Always use `runAll.sh` (from the installation `bin/` directory) to start/stop, as it handles both server and agent:

```bash
# Stop
cd <install-dir> && bash bin/runAll.sh stop

# Start (background)
cd <install-dir> && nohup bash bin/runAll.sh start > /tmp/teamcity-startup.log 2>&1 &
```

Verify with `ps aux | grep -E "teamcity|TeamCity" | grep -v grep`. Expect at least the restarter, server JVM, and agent JVM processes.

### Config inspection

All runtime config lives under `<data-dir>/config/`. The data directory is NOT necessarily the same as the install directory — always check `teamcity-startup.properties` for `teamcity.data.path`.

Key files:
- `main-config.xml` — server identity (UUID, root URL)
- `database.properties` — database connection
- `ldap-config.properties` — LDAP integration
- `auth-config.xml` — authentication module registration
- `_auth/` directory — individual auth module XMLs

### LDAP activation

If `ldap-config.properties` does not exist in `<data-dir>/config/`, LDAP login is inactive even though the `ldap` plugin loads. See `references/ldap-config.md` for the full guide.

Quick start:
```bash
cp <data-dir>/config/ldap-config.properties.dist <data-dir>/config/ldap-config.properties
```

TeamCity picks up changes to this file automatically — restart is only needed if the file didn't exist before.

### Log inspection

Primary log location: `<data-dir>/logs/teamcity-server.log`
Secondary (may be symlinked): `<install-dir>/logs/teamcity-server.log`

Search patterns:
```bash
grep -i "ldap\|error\|exception\|warning" <log-file> | tail -50
grep -i "plugin" <log-file> | grep -i "load\|init\|fail"
```

### Agent management

Agent config: `<data-dir-adjacent>/buildAgent/conf/buildAgent.properties`
Check `serverUrl` is correct and agent is connected.

Agent-level environment variables: any `env.X=value` line in `buildAgent.properties`
is exported as env var `X` to all build processes on that agent. The agent watches the
file and hot-reloads it; after reload it pushes updated parameters to the server
(`Updating agent parameters on the server` in teamcity-agent.log). A manual restart is
the deterministic path for picking up changes: `bin/agent.sh stop` (graceful, exits
when idle) then `nohup bin/agent.sh start`.

### Build chains

先读 [Build chain 参数与验证](references/build-chain-parameters.md)，再修改配置：

1. 从具体 Flow build ID 递归展开依赖，区分单节点兼容性、同机组交集和 Agent 空闲状态。
2. 为每个参数确定唯一业务入口与解析上下文；Flow 下发分支/CL，目标 Agent 解析本机路径。
3. 先用 echo-only 链断言实际值，再验证真实 Sync/Unshelve；不拿生产 CL 反复试参数。
4. 回报实际 Agent、stream/CL/Root、配置 revision 和各阶段状态；匹配成功不等于全链成功。

Composite Flow 不占 Agent；其 Agent 栏为空不是故障结论。显式 requirements 之外，
还要查看 runner/参数引用的隐式要求。已入队快照与当前配置、业务侧 build ID 关联分别核实。

<memory category="common-patterns">
To allow exactly several named agents, use one `teamcity.agent.name` `matches` requirement with anchored alternation, e.g. `^(?:WinBuilder1|WinBuilder4)$`. Separate TeamCity requirements are ANDed, so two `equals` requirements cannot express this OR. Replace any existing name requirement rather than stacking another; for versioned settings, make the equivalent Kotlin DSL change (`requirements { matches(...) }`) so a UI-only edit is not overwritten.
</memory>

<memory category="common-patterns">
PLN 的 Win64 AI Review 使用专属 `TaskBuildUEWindows` 与 `TaskAiReview` 收窄 Windows/WinBuilder 路由，
不需要历史 Linux 交叉编译方案的 `env.LINUX_MULTIARCH_ROOT`。共享 Sync/Unshelve 保持通用；
CodeGraph 的 Linux 编译链独立保留。同机组靠 snapshot 边取兼容性交集，不给共享节点追加专属能力门。
</memory>

<memory category="code-locations">
PLN_TaskAiReview 的内容步 "Collect Review Context" 调的是 **MainDev depot** 的 `Tools/AiReview/AiReviewContextCollect.py`（本机 `D:\MainDev`），不在 DevOps 仓——ws:autoserver-deveops 的 AI review 故障可能要改 MainDev 文件。`STREAM_MISMATCH` 报错出自其 `collect_diff()`。**2026-09 起混合 stream CL 不再硬失败**：目标 stream 外文件不进 diff、只在 diff 头部记 SKIPPED 节（列前 20 条；实测 CL 130205 目标 MainDev 时 Wwise 的 a.cpp 被跳过），整 CL 都在目标 stream 外才 exit 3。上游 Task_Unshelve（DevOps `P4UnshelveStage.py`）对混合 CL 正常——见 STREAM_MISMATCH 先查 collect 步，别查 unshelve。
</memory>

<memory category="troubleshooting">
PLN_TaskAiReview 观测性两个结构性事实（build 18399 实证，2026-09）：
① 编译日志采集是**静默降级**——Collect 步 `--tc-dep-suffix` 必须与链上实际编译节点同名（现 `TaskBuildUEWindows`，链定义见 build-chain-parameters.md）；不匹配不报错，`Saved/ai_review/build_log_tail.txt` 只剩 ~94B 说明 stub，AI 在无编译日志下评审。已发根因：脚本默认值滞留 `TaskBuildUELinux`、文档声称已对齐而代码没有。评审输出缺编译证据时先查该文件大小，别怀疑模型。
② Pi_Agent_Review 步 pi stdout 全量重定向进 `pi_out.txt`，TC 日志天然只剩一行 exit code——透明化只能靠运行中心跳（pi_out/session 字节增长）+ 结束后回放 `Saved/ai_review/sessions/*.jsonl`（含工具调用序列与 thinking）；该目录跨构建累积，必须按 mtime ≥ 启动时刻过滤本轮会话。模型输出写进 TC 日志前一律 `##teamcity` 转义，防伪造 service message。
</memory>

<memory category="troubleshooting">
AI 评审看不到 warning 的采集侧根因（2026-10 查明）：MainDev `Tools/AiReview/AiReviewContextCollect.py` 的 `LOG_ERROR_RE` 只匹配 `error|fatal|failed`，**不含 warning**——`build_log_tail.txt` 结构性漏掉全部警告（informer PREVIEW 里仅 `Summary: 0 Errors, N Warnings` 这行碰巧命中 error 关键字，正文全漏）。只在构建里加 warning 分析没用，AI 侧必须走独立报告文件通道；不要把 warning 扩进 `LOG_ERROR_RE`——tail 有 50KB cap，warning 量大反而挤占 error。
</memory>

<memory category="code-locations">
评审链缺 AS 检查的对照实证（build 18686 vs 18708）：`PL_BuildUgsBinaries` Step 11 `AngelScript Compile Check` = `UnrealEditor-Cmd.exe <uproject> -run=AngelscriptTest -as-force-preprocess-editor-code -NullRHI -nosplash -unattended`（非零退出炸构建），Step 17 `Log Analysis Report`（execute_always）调 informer `--log-level All --warning-categories angelscript,cpp_game`；`PLN_TaskBuildUEWindows` 只 3 步、informer 仅 `--job-result=FAILURE` 时跑。TaskAiReview 对 TaskBuildUEWindows 的 snapshot 依赖是 on-failure=`RUN_ADD_PROBLEM`（已 REST 核实）——编译步炸构建**不阻断**评审，评审照跑且 AS error 经日志匹配进 `build_log_tail.txt` 被 AI 看到。
</memory>

<memory category="troubleshooting">
TaskAiReview 的"停用"实为占位放行（2026-09 核实）：`paused=false`、6 步全 enabled，但 `Pi_Agent_Review` 的 18 行脚本不启动 Pi，固定写 `verdict=approve, risk_score=0`（摘要自称 temporarily disabled）；前一版还带 300 秒超时放行。绿色构建（如 #18820）只证明占位链跑通，**不证明 AI 评审过**——验收以 `Saved/ai_review/sessions/*.jsonl` 出现真实会话为准，不看构建颜色。恢复真实评审必须同时删掉占位脚本与超时放行，不能裸回退到带超时放行的旧 CL。
</memory>

<memory category="code-locations">
TaskAiReview 旁路/开关设计依赖的 Publish 契约（2026-10 读码核实）：Publish 步脚本 `Tools/AiReview/AiReviewResultPublish.py`（MainDev）只校验 `pi_out.txt` 里 JSON 的 verdict ∈ {approve, reject, needs_discussion}，并强制覆盖 cl/stream/url 元数据——占位 verdict=approve 的 pi_out.txt 与真实评审输出走完全相同的已验证解析发布路径。因此加 review/bypass 模式开关只需在 Pi_Agent_Review 步内分支（bypass 写占位 pi_out.txt 后 exit 0），Publish/Collect/Cleanup 零改动；开关做成 select 参数时，TC UI 改参数值（patches 模式）或 Run Custom Build 覆盖即时生效，回滚不需要紧急 P4 提交。
</memory>

<memory category="troubleshooting">
构建机跑真实 Pi_Agent_Review 的两个逐机环境前置（WinBuilder3 当时两者都缺）：① 本机配置 A2A token；② 经 VPN 直连 Memory Hub `http://10.77.77.6:9287`（VPN-only，无域名/中转/公网兜底）。扩展单测通过 ≠ TC headless agent 内可用——单测不覆盖 token 注入与 VPN 连通，灰度必须逐机实测；兼容机共三台 WinBuilder1/3/4，只验一台不能宣称全可用。
</memory>

<memory category="common-patterns">
TC Windows runner 上凡打印非 ASCII 的 python 步骤必须配 `env.PYTHONUTF8=1`：runner 已 `chcp 65001`，但 python stdout 走管道时退回系统 locale（cp936），二者错位即中文乱码（TaskAiReview summary 乱码根因）。kts 参数区加一行即对所有 python 内联步生效。
</memory>

<memory category="troubleshooting">
Log Analysis Report 步静默放行的 P4 优先级根因（build 18869 查明，2026-09）：DevOps bootstrap 用 **env** `P4PORT=192.168.2.13:1666`（unicode 服务器）+ 命令行 `-C utf8` sync informer，但步骤 cwd 是 checkout 根（如 `F:\WinBuilder1_MainDev`），**其中躺着游戏工作区的 `.p4config`（`P4PORT=192.168.2.236:1666`，非 unicode）——P4 优先级：命令行 > P4CONFIG 文件 > 环境变量**，于是 p4 连到 .236 带 `-C utf8` 被拒（"Unicode clients require a unicode enabled server"），全部 p4 命令失败 → `devops_root` 落兜底空目录 → informer 缺失 → `skip report` → 整步按设计 exit 0 放行。后果链：`Saved/ai_review/build_log_analysis.txt` 不生成 → TaskAiReview 的 AI 无 warning 证据判过（AS Compile Check 只拦 error，warning 唯一捕获通道就是该报告）。识别：meta sidecar `report_present:false` + 报告文件缺失/stale。正确修法是 `p4 -p <port>` 提到命令行（优先级最高），同款 bootstrap 块有 3 处（TaskBuildUEWindows.kts 的 Report+Notification 步、TaskAiReview.kts 通知引导段）。
</memory>

<memory category="troubleshooting">
「构建结束不掉」通常是 TC 两阶段停止机制的延迟，不是僵尸进程（build 18808 实证，2026-09）：第一次点 Stop 只发优雅取消请求，UE commandlet 不响应中断时构建卡在「statusText=Canceled 但 state=running」可达数分钟；第二次点 Stop 才触发 agent 侧强制杀进程。处置顺序：REST 查 `state`/`running`/`statusText` → 登 agent 机查残留进程（UnrealEditor/UnrealBuildTool/ShaderCompileWorker）→ 两者都干净就不要重启 server/agent 服务，再点一次 Stop 或等其落地即可。
</memory>

## Troubleshooting build failures

构建失败排障条目（UE 构建 UBT mutex 冲突等）见 [references/troubleshooting.md](references/troubleshooting.md)。

## Important principles

- **Data dir ≠ install dir.** This is the most common pitfall. Always read `teamcity-startup.properties` to find the real config location.
- **The .dist files are templates.** They get overwritten on restart. Always copy to the non-dist version to make changes permanent.
- **Check hostname first.** When this skill is used on multiple machines, the first thing to verify is which machine you're on.
- **Use nohup for starts.** TeamCity server takes time to initialize. Don't block the terminal.

---
name: teamcity-tool
description: >
  TeamCity server administration toolkit — manage service lifecycle, inspect/edit config,
  LDAP/auth setup, health checks, troubleshooting, and REST API operations.
  Use when the user mentions TeamCity, TC server, teamcity-server,
  "restart TeamCity", "check TeamCity logs", "TeamCity config", "LDAP TeamCity",
  "build agent", "teamcity data directory", "build chain", "build queue",
  "no compatible agents", "reverse.dep", "snapshot dependency", or any TeamCity
  admin/ops/API task, or reports problems with the TeamCity web UI, login, builds,
  or agent assignment on this host. Covers the PL packaging pipeline
  (PL_BuildProjectWindows / PL_BuildUgsBinaries, UAT cook, MinIO upload), agent
  checkout-directory auto-clean incidents (DirectoryMap cleaner, 192h expiry),
  the PLN_FlowAiReview AI-review pipeline (Sync/Unshelve/BuildUE_Linux/Pi_Agent_Review)
  performance profile and queue bottlenecks, and the PLN_TaskAiReview failure-notification
  chain (TeamCityLogParserInformer attribution / feishu routing).
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
| Build chain & parameter passing lessons | `references/build-chain-lessons.md` |
| Agent pinning and `reverse.dep.*` behavior | `references/agent-pinning.md` |
| Non-obvious traps and gotchas | `references/gotchas.md` |
| 打包管线 (PL_BuildProjectWindows / PL_BuildUgsBinaries / UAT cook) | `references/package-pipeline.md` |
| Checkout 目录自动清理事故 (DirectoryMap cleaner, 192h expiry) | `references/checkout-dir-auto-clean.md` |
| 构建失败排障（UE 构建 UBT mutex 冲突等） | `references/troubleshooting.md` |
| FlowAiReview 管线耗时画像与瓶颈、编译失败归因（sync HEAD 语义 / adaptive unity 盲区 / workspace reset 机制）、后端 busy 门与降级放行缺陷、unshelve 独占锁、队列停摆诊断 | `references/flow-aireview-pipeline.md` |
| TaskAiReview 失败通知链路（TeamCityLogParserInformer 归因/路由语义、latestCL vs unshelve CL 身份陷阱） | `references/task-aireview-notification.md` |

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

<memory category="troubleshooting">
TeamCity 的 Agent 兼容性还取决于构建参数引用能否解析，并非只看 Agent 名称要求。
`PLN_FlowAiReview` 的 `Task_Sync_CyanCook_Depot` 收到 `P4Stream=%env.p4_stream%` 而缺少 `env.p4_stream` 时，符合名称要求的 Agent 仍会被 Sync 判为不兼容，阻塞整链；放宽名称正则无效。
Flow→Sync 的分支透传必须保证 `P4Stream` 在 Sync 自身上下文中解析为实际 stream（如 `MainDev`）；诊断以排队 Sync 的实际参数为准。
</memory>

<memory category="common-patterns">
To allow exactly several named agents, use one `teamcity.agent.name` `matches` requirement with anchored alternation, e.g. `^(?:WinBuilder1|WinBuilder4)$`. Separate TeamCity requirements are ANDed, so two `equals` requirements cannot express this OR. Replace any existing name requirement rather than stacking another; for versioned settings, make the equivalent Kotlin DSL change (`requirements { matches(...) }`) so a UI-only edit is not overwritten.
</memory>

## Troubleshooting build failures

构建失败排障条目（UE 构建 UBT mutex 冲突等）见 [references/troubleshooting.md](references/troubleshooting.md)。

## Important principles

- **Data dir ≠ install dir.** This is the most common pitfall. Always read `teamcity-startup.properties` to find the real config location.
- **The .dist files are templates.** They get overwritten on restart. Always copy to the non-dist version to make changes permanent.
- **Check hostname first.** When this skill is used on multiple machines, the first thing to verify is which machine you're on.
- **Use nohup for starts.** TeamCity server takes time to initialize. Don't block the terminal.

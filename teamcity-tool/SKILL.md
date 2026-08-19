---
name: teamcity-tool
description: >
  TeamCity server administration toolkit — manage service lifecycle, inspect/edit configuration,
  set up LDAP/authentication, verify runtime health, troubleshoot issues, and operate the REST API.
  Use when the user mentions TeamCity, teamcity, TC server, teamcity-server,
  "restart TeamCity", "check TeamCity logs", "TeamCity config", "LDAP TeamCity",
  "TeamCity agent", "build agent", "teamcity data directory", "build chain", "build queue",
  "no compatible agents", "reverse.dep", "snapshot dependency", or any TeamCity
  admin/ops/API task. Also trigger when the user reports problems with the TeamCity
  web UI, login, builds, or agent assignment on this host. Covers the PL packaging
  pipeline (PL_BuildProjectWindows / PL_BuildUgsBinaries, UAT cook, MinIO upload)
  and agent checkout-directory auto-clean incidents (DirectoryMap cleaner, 192h expiry).
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

## Troubleshooting build failures

<memory category="troubleshooting">
UE 构建报 `A conflicting instance of Global\UnrealBuildTool_Mutex_<hash> is already running`（UBT 退出码 ConflictingInstance）时：mutex hash 对应**引擎根目录**，含义是同机有另一个 UBT 实例在对同一引擎目录工作，冲突方不一定是 TeamCity 任务。排查顺序：(1) 每台构建机只有一个 agent，用 REST API 查该 agent 在撞锁时间窗内的所有 build（见 rest-api.md）排除 TC 内部冲突；(2) 若 TC 侧无并发 build，元凶在 TC 之外——最常见是有人在这台机器上开着 UnrealEditor+Live Coding 或 UGS 客户端自动编译，P4 sync 落地文件变更会触发它（特征：撞锁总发生在 sync 完成后几秒内）；(3) 上机看 `<EngineRoot>\Engine\Programs\UnrealBuildTool\Log.txt` 拿冲突方的完整命令行和启动时间，或用 Sysinternals `handle64.exe -a UnrealBuildTool_Mutex`（管理员）循环抓持锁进程。缓解：UBT 撞锁几乎秒失败（~0.3s）但持锁方常只占几秒，在 build 脚本里对 ConflictingInstance 加 sleep 30s 重试 3~5 次即可自愈。
</memory>

## Important principles

- **Data dir ≠ install dir.** This is the most common pitfall. Always read `teamcity-startup.properties` to find the real config location.
- **The .dist files are templates.** They get overwritten on restart. Always copy to the non-dist version to make changes permanent.
- **Check hostname first.** When this skill is used on multiple machines, the first thing to verify is which machine you're on.
- **Use nohup for starts.** TeamCity server takes time to initialize. Don't block the terminal.

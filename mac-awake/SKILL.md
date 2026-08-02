---
name: mac-awake
description: Keep a Mac awake only while AI work is actually running. Use when installing, configuring, updating, checking, or troubleshooting task-aware sleep and automatic-lock prevention for Claude Code, the Codex/ChatGPT desktop app or CLI, and Orca-managed agents, automations, or orchestrations.
---

# Mac Awake

Use `scripts/mac_awake.py` as the single implementation. It combines Claude hook heartbeats, Codex rollout state, live Codex background processes, and Orca runtime state. Do not substitute “application is open” or Orca `workspaceStatus: in-progress` for active execution.

## Workflow

1. Run the deterministic self-test:

   ```bash
   python3 scripts/mac_awake.py self-test
   ```

2. Inspect current state without changing the system:

   ```bash
   python3 scripts/mac_awake.py status
   python3 scripts/mac_awake.py status --json
   ```

3. Preview installation paths and mutations:

   ```bash
   python3 scripts/mac_awake.py install --dry-run
   ```

4. When the user requested installation, install the copied runtime, LaunchAgent, and idempotently merged Claude hooks:

   ```bash
   python3 scripts/mac_awake.py install
   ```

5. Configure the optional closed-lid assertion only with the user's approval. Use `whoami` to replace `USERNAME`, then edit with `sudo visudo -f /etc/sudoers.d/mac-awake`:

   ```text
   USERNAME ALL=(root) NOPASSWD: /usr/bin/pmset -a disablesleep 1, /usr/bin/pmset -a disablesleep 0
   ```

   Without this rule, `caffeinate` still prevents idle display sleep, automatic lock, and ordinary system sleep while the lid remains open. `pmset disablesleep` adds closed-lid protection. Never weaken this to a wildcard command.

6. Re-run `status`, then inspect `~/Library/Logs/mac-awake.log`. Verify `keep_awake=true` during a task and `false` after completion.

## Behavioral rules

- Preserve manual lock: prevent only idle-triggered display sleep, lock, and system sleep.
- Treat Claude markers as fresh for 30 minutes; remove them immediately on `Stop` and `SessionEnd`.
- Treat a Codex rollout as active only when its latest lifecycle event is `task_started`; cap stale incomplete state at six hours and separately validate live background PIDs.
- Treat Orca agents in `working`, `blocked`, or `waiting` as active. Also count live automation and orchestration runs. Prefer `orca worktree ps --json`; use Orca's local status cache only as a bounded fallback.
- Release sleep assertions when all tasks finish, the watchdog exits, or macOS reports thermal throttling.
- Re-run `install` after editing the skill so the installed runtime copy is refreshed.

## Diagnostics and removal

Use foreground mode only for short diagnosis; stop it with Ctrl-C:

```bash
python3 scripts/mac_awake.py daemon --foreground --poll 5
```

Remove only files and Claude hook entries owned by this skill:

```bash
python3 scripts/mac_awake.py uninstall
sudo /usr/bin/pmset -a disablesleep 0
sudo rm /etc/sudoers.d/mac-awake
```

If Orca detection reports unavailable, run `orca status --json` outside a restricted sandbox. A sandbox may deny access to Orca's Unix socket even while the desktop app is healthy.

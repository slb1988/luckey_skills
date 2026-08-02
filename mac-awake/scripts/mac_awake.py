#!/usr/bin/env python3
"""Task-aware macOS sleep and idle-lock watchdog for Claude, Codex, and Orca."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import plistlib
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


LABEL = "com.mac-awake"
HOME = Path.home()
SUPPORT_DIR = HOME / "Library" / "Application Support" / "mac-awake"
INSTALL_SCRIPT = SUPPORT_DIR / "mac_awake.py"
STATE_DIR = SUPPORT_DIR / "state"
CLAUDE_STATE_DIR = STATE_DIR / "claude"
LOCK_FILE = STATE_DIR / "daemon.lock"
LOG_FILE = HOME / "Library" / "Logs" / "mac-awake.log"
ERROR_LOG_FILE = HOME / "Library" / "Logs" / "mac-awake.err.log"
PLIST_FILE = HOME / "Library" / "LaunchAgents" / f"{LABEL}.plist"
CLAUDE_SETTINGS = HOME / ".claude" / "settings.json"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(HOME / ".codex"))).expanduser()
ORCA_SUPPORT = HOME / "Library" / "Application Support" / "orca"

DEFAULT_POLL_SECONDS = 20
DEFAULT_CLAUDE_STALE_SECONDS = 30 * 60
DEFAULT_CODEX_STALE_SECONDS = 6 * 60 * 60
DEFAULT_ORCA_STALE_SECONDS = 30 * 60
LOG_RETENTION_SECONDS = 24 * 60 * 60
ACTIVE_AGENT_STATES = {"working", "blocked", "waiting"}
CODEX_START_EVENT = "task_started"
CODEX_END_EVENTS = {"task_complete", "turn_aborted"}


def now_ms() -> int:
    return int(time.time() * 1000)


def safe_json_load(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def sanitize_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    return cleaned[:160] or "default"


def atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.chmod(temp_path, mode)
    os.replace(temp_path, path)


def rotate_log_if_needed() -> None:
    try:
        if LOG_FILE.stat().st_size > 2 * 1024 * 1024:
            backup = LOG_FILE.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            LOG_FILE.replace(backup)
    except OSError:
        pass


def cleanup_expired_logs(
    current_time: float | None = None,
    structured_paths: tuple[Path, ...] | None = None,
    unstructured_paths: tuple[Path, ...] | None = None,
) -> None:
    """Remove log entries/files older than 24 hours before each daemon refresh."""
    now = time.time() if current_time is None else current_time
    cutoff = now - LOG_RETENTION_SECONDS
    structured = structured_paths or (LOG_FILE, LOG_FILE.with_suffix(".log.1"))
    unstructured = unstructured_paths or (ERROR_LOG_FILE,)

    for path in structured:
        try:
            if not path.exists():
                continue
            retained: list[str] = []
            changed = False
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        timestamp = time.mktime(
                            time.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
                        )
                    except (OverflowError, ValueError):
                        changed = True
                        continue
                    if timestamp >= cutoff:
                        retained.append(line)
                    else:
                        changed = True

            if not changed:
                continue

            if not retained:
                path.unlink(missing_ok=True)
                continue

            mode = path.stat().st_mode & 0o777
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent, delete=False
            ) as handle:
                handle.writelines(retained)
                temp_path = Path(handle.name)
            os.chmod(temp_path, mode)
            os.replace(temp_path, path)
        except OSError:
            continue

    # LaunchAgent stderr is not timestamped. Remove the whole file only when
    # it has received no new output for more than the retention window.
    for path in unstructured:
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def log(message: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        rotate_log_if_needed()
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
    except OSError:
        pass


@dataclass
class SourceState:
    active: int = 0
    detail: str = "idle"
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"active": self.active, "detail": self.detail}
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class RolloutCacheEntry:
    size: int = 0
    state: str | None = None


@dataclass
class TaskMonitor:
    claude_state_dir: Path = CLAUDE_STATE_DIR
    codex_home: Path = CODEX_HOME
    orca_support: Path = ORCA_SUPPORT
    claude_stale_seconds: int = DEFAULT_CLAUDE_STALE_SECONDS
    codex_stale_seconds: int = DEFAULT_CODEX_STALE_SECONDS
    orca_stale_seconds: int = DEFAULT_ORCA_STALE_SECONDS
    rollout_cache: dict[str, RolloutCacheEntry] = field(default_factory=dict)

    def claude_state(self) -> SourceState:
        active = 0
        cutoff = time.time() - self.claude_stale_seconds
        try:
            if not self.claude_state_dir.exists():
                return SourceState(0, "0 fresh session marker(s)")
            for marker in self.claude_state_dir.iterdir():
                if not marker.is_file():
                    continue
                try:
                    if marker.stat().st_mtime >= cutoff:
                        active += 1
                    else:
                        marker.unlink()
                except OSError:
                    continue
            return SourceState(active, f"{active} fresh session marker(s)")
        except OSError as exc:
            return SourceState(error=f"state directory unavailable: {exc}")

    def _codex_databases(self) -> Iterable[Path]:
        seen: set[tuple[int, int]] = set()
        for path in (
            self.codex_home / "state_5.sqlite",
            self.codex_home / "sqlite" / "state_5.sqlite",
        ):
            try:
                stat = path.stat()
                key = (stat.st_dev, stat.st_ino)
            except OSError:
                continue
            if key not in seen:
                seen.add(key)
                yield path

    def _rollout_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        for database in self._codex_databases():
            try:
                connection = sqlite3.connect(
                    f"file:{database}?mode=ro", uri=True, timeout=0.2
                )
                rows = connection.execute(
                    "SELECT rollout_path FROM threads "
                    "WHERE archived = 0 ORDER BY updated_at DESC LIMIT 64"
                ).fetchall()
                connection.close()
                candidates.extend(Path(row[0]).expanduser() for row in rows if row[0])
                break
            except (sqlite3.Error, OSError):
                continue

        if not candidates:
            session_root = self.codex_home / "sessions"
            cutoff = time.time() - self.codex_stale_seconds
            try:
                for path in session_root.rglob("*.jsonl"):
                    try:
                        if path.stat().st_mtime >= cutoff:
                            candidates.append(path)
                    except OSError:
                        continue
            except OSError:
                pass

        unique: dict[str, Path] = {}
        for path in candidates:
            unique[str(path)] = path
        return list(unique.values())

    def _rollout_state(self, path: Path) -> str | None:
        key = str(path)
        cached = self.rollout_cache.get(key, RolloutCacheEntry())
        try:
            size = path.stat().st_size
            if size < cached.size:
                cached = RolloutCacheEntry()
            if size == cached.size:
                self.rollout_cache[key] = cached
                return cached.state
            with path.open("rb") as handle:
                handle.seek(cached.size)
                committed_size = cached.size
                while True:
                    line_start = handle.tell()
                    raw_line = handle.readline()
                    if not raw_line:
                        break
                    if not raw_line.endswith(b"\n"):
                        # Keep a partial JSONL record for the next poll instead of
                        # permanently skipping a concurrently appended event.
                        committed_size = line_start
                        break
                    try:
                        record = json.loads(raw_line)
                    except (ValueError, UnicodeDecodeError):
                        committed_size = handle.tell()
                        continue
                    if record.get("type") != "event_msg":
                        committed_size = handle.tell()
                        continue
                    payload = record.get("payload")
                    event = payload.get("type") if isinstance(payload, dict) else None
                    if event == CODEX_START_EVENT or event in CODEX_END_EVENTS:
                        cached.state = event
                    committed_size = handle.tell()
            cached.size = committed_size
            self.rollout_cache[key] = cached
            return cached.state
        except OSError:
            return None

    def _live_codex_background_processes(self) -> int:
        records = safe_json_load(
            self.codex_home / "process_manager" / "chat_processes.json", []
        )
        if not isinstance(records, list):
            return 0
        return sum(
            1
            for record in records
            if isinstance(record, dict) and pid_alive(record.get("osPid"))
        )

    def codex_state(self) -> SourceState:
        active_rollouts = 0
        cutoff = time.time() - self.codex_stale_seconds
        checked = 0
        for path in self._rollout_candidates():
            try:
                if path.stat().st_mtime < cutoff:
                    continue
            except OSError:
                continue
            checked += 1
            if self._rollout_state(path) == CODEX_START_EVENT:
                active_rollouts += 1
        background = self._live_codex_background_processes()
        total = active_rollouts + background
        detail = (
            f"{active_rollouts} active rollout(s), {background} live background process(es), "
            f"{checked} recent rollout(s) checked"
        )
        return SourceState(total, detail)

    @staticmethod
    def _count_active_agent_objects(value: Any) -> int:
        count = 0
        if isinstance(value, dict):
            if value.get("state") in ACTIVE_AGENT_STATES:
                count += 1
            for key, child in value.items():
                if key != "state":
                    count += TaskMonitor._count_active_agent_objects(child)
        elif isinstance(value, list):
            count += sum(TaskMonitor._count_active_agent_objects(item) for item in value)
        return count

    def _orca_cli(self) -> str | None:
        return shutil.which("orca") or (
            "/Applications/Orca.app/Contents/Resources/bin/orca"
            if Path("/Applications/Orca.app/Contents/Resources/bin/orca").exists()
            else None
        )

    def _orca_worktree_agents(self) -> tuple[int, bool, str | None]:
        command = self._orca_cli()
        if not command:
            return 0, False, "orca CLI not found"
        try:
            process = subprocess.run(
                [command, "worktree", "ps", "--json"],
                text=True,
                capture_output=True,
                timeout=8,
                check=False,
                env={**os.environ, "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 0, False, str(exc)
        try:
            payload = json.loads(process.stdout)
        except ValueError:
            return 0, False, "orca CLI returned invalid JSON"
        if process.returncode != 0 or payload.get("ok") is not True:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            return 0, False, str(error.get("code") or error.get("message") or "unavailable")
        worktrees = payload.get("result", {}).get("worktrees", [])
        active = 0
        if isinstance(worktrees, list):
            for worktree in worktrees:
                if isinstance(worktree, dict):
                    active += self._count_active_agent_objects(worktree.get("agents", []))
        return active, True, None

    def _orca_cached_agents(self) -> int:
        payload = safe_json_load(self.orca_support / "agent-hooks" / "last-status.json", {})
        cutoff_ms = now_ms() - self.orca_stale_seconds * 1000

        def count(value: Any) -> int:
            if isinstance(value, dict):
                state = value.get("state")
                updated = value.get("updatedAt") or value.get("receivedAt") or 0
                own = int(
                    state in ACTIVE_AGENT_STATES
                    and isinstance(updated, (int, float))
                    and updated >= cutoff_ms
                )
                return own + sum(count(child) for child in value.values())
            if isinstance(value, list):
                return sum(count(item) for item in value)
            return 0

        return count(payload.get("entries", payload) if isinstance(payload, dict) else payload)

    def _orca_automation_runs(self) -> int:
        payload = safe_json_load(self.orca_support / "orca-data.json", {})
        runs = payload.get("automationRuns", []) if isinstance(payload, dict) else []
        if not isinstance(runs, (list, dict)):
            return 0
        active_states = {"running", "starting", "queued"}

        def count(value: Any) -> int:
            if isinstance(value, dict):
                own = int(value.get("status") in active_states or value.get("state") in active_states)
                return own + sum(count(child) for child in value.values())
            if isinstance(value, list):
                return sum(count(item) for item in value)
            return 0

        return count(runs)

    def _orca_orchestration_runs(self) -> int:
        database = self.orca_support / "orchestration.db"
        if not database.exists():
            return 0
        queries = (
            "SELECT COUNT(*) FROM coordinator_runs "
            "WHERE status='running' AND scheduler_lost_at IS NULL",
            "SELECT COUNT(*) FROM worker_dispatches WHERE state IN "
            "('starting','ready','start_unknown','stopping','stop_unknown')",
        )
        total = 0
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.2)
            for query in queries:
                total += int(connection.execute(query).fetchone()[0])
            connection.close()
        except (sqlite3.Error, OSError, TypeError, ValueError):
            return 0
        return total

    def orca_state(self) -> SourceState:
        agents, runtime_ok, error = self._orca_worktree_agents()
        if not runtime_ok:
            agents = self._orca_cached_agents()
        automations = self._orca_automation_runs() if runtime_ok else 0
        orchestrations = self._orca_orchestration_runs() if runtime_ok else 0
        total = agents + automations + orchestrations
        detail = (
            f"{agents} active agent(s), {automations} automation run(s), "
            f"{orchestrations} orchestration run(s); runtime={'ready' if runtime_ok else 'fallback'}"
        )
        return SourceState(total, detail, error if not runtime_ok else None)

    @staticmethod
    def thermal_throttled() -> bool:
        try:
            process = subprocess.run(
                ["/usr/bin/pmset", "-g", "therm"],
                text=True,
                capture_output=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        for field in ("CPU_Scheduler_Limit", "CPU_Speed_Limit"):
            match = re.search(rf"{field}\s*=\s*(\d+)", process.stdout)
            if match and int(match.group(1)) < 100:
                return True
        return False

    def snapshot(self) -> dict[str, Any]:
        sources = {
            "claude": self.claude_state(),
            "codex_chatgpt": self.codex_state(),
            "orca": self.orca_state(),
        }
        tasks_active = any(source.active > 0 for source in sources.values())
        thermal_block = self.thermal_throttled()
        return {
            "tasks_active": tasks_active,
            "thermal_block": thermal_block,
            "keep_awake": tasks_active and not thermal_block,
            "sources": {name: source.as_dict() for name, source in sources.items()},
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }


class AwakeController:
    def __init__(self) -> None:
        self.caffeinate: subprocess.Popen[bytes] | None = None
        self.applied: bool | None = None
        self.pmset_available: bool | None = None

    def _set_pmset(self, awake: bool) -> None:
        if os.environ.get("MAC_AWAKE_SKIP_PMSET") == "1":
            return
        value = "1" if awake else "0"
        try:
            process = subprocess.run(
                ["/usr/bin/sudo", "-n", "/usr/bin/pmset", "-a", "disablesleep", value],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            self.pmset_available = process.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            self.pmset_available = False
        if not self.pmset_available:
            log("pmset unavailable; caffeinate protection remains active (configure exact sudoers rule for closed-lid mode)")

    def _start_caffeinate(self) -> None:
        if self.caffeinate and self.caffeinate.poll() is None:
            return
        try:
            self.caffeinate = subprocess.Popen(
                # -u defaults to only five seconds without -t. Use a bounded
                # one-hour assertion; the poll loop restarts it while work is
                # active and terminates it immediately when work finishes.
                ["/usr/bin/caffeinate", "-dimsu", "-t", "3600"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            self.caffeinate = None
            log(f"caffeinate start failed: {exc}")

    def _stop_caffeinate(self) -> None:
        if not self.caffeinate or self.caffeinate.poll() is not None:
            self.caffeinate = None
            return
        self.caffeinate.terminate()
        try:
            self.caffeinate.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.caffeinate.kill()
            self.caffeinate.wait(timeout=2)
        self.caffeinate = None

    def set_awake(self, awake: bool, reason: str) -> None:
        if self.applied is awake:
            if awake:
                self._start_caffeinate()
            return
        if awake:
            self._start_caffeinate()
            self._set_pmset(True)
        else:
            self._stop_caffeinate()
            self._set_pmset(False)
        self.applied = awake
        log(f"keep_awake={str(awake).lower()} reason={reason}")

    def close(self) -> None:
        self._stop_caffeinate()
        self._set_pmset(False)
        self.applied = False
        log("watchdog exit; sleep assertions released")


def heartbeat(action: str) -> int:
    try:
        raw = sys.stdin.read()
    except OSError:
        raw = ""
    payload: dict[str, Any] = {}
    if raw.strip():
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                payload = decoded
        except ValueError:
            pass
    session_id = str(
        payload.get("session_id")
        or payload.get("conversation_id")
        or os.environ.get("CLAUDE_SESSION_ID")
        or "default"
    )
    marker = CLAUDE_STATE_DIR / sanitize_id(session_id)
    try:
        CLAUDE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        if action == "remove":
            marker.unlink(missing_ok=True)
        else:
            marker.touch()
    except OSError:
        pass
    return 0


def plist_payload() -> dict[str, Any]:
    return {
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/python3", str(INSTALL_SCRIPT), "daemon"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        },
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": str(ERROR_LOG_FILE),
    }


def hook_command(action: str) -> str:
    quoted = "'" + str(INSTALL_SCRIPT).replace("'", "'\\''") + "'"
    return f"/usr/bin/python3 {quoted} heartbeat {action} # mac-awake"


def merge_claude_hooks(settings: dict[str, Any]) -> dict[str, Any]:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude settings 'hooks' must be an object")
    definitions = {
        "UserPromptSubmit": ("touch", None),
        "PostToolUse": ("touch", "*"),
        "Stop": ("remove", None),
        "SessionEnd": ("remove", None),
    }
    for event, (action, matcher) in definitions.items():
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError(f"Claude hook event '{event}' must be an array")
        command = hook_command(action)
        exists = any(
            isinstance(group, dict)
            and any(
                isinstance(item, dict) and item.get("command") == command
                for item in group.get("hooks", [])
            )
            for group in groups
        )
        if not exists:
            group: dict[str, Any] = {
                "hooks": [{"type": "command", "command": command}]
            }
            if matcher:
                group["matcher"] = matcher
            groups.append(group)
    return settings


def remove_claude_hooks(settings: dict[str, Any]) -> dict[str, Any]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        retained_groups = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                retained_groups.append(group)
                continue
            retained_items = [
                item
                for item in group["hooks"]
                if not (
                    isinstance(item, dict)
                    and str(INSTALL_SCRIPT) in str(item.get("command", ""))
                    and " heartbeat " in str(item.get("command", ""))
                )
            ]
            if retained_items:
                copy = dict(group)
                copy["hooks"] = retained_items
                retained_groups.append(copy)
        if retained_groups:
            hooks[event] = retained_groups
        else:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    return settings


def launchctl(*arguments: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/launchctl", *arguments],
        text=True,
        capture_output=True,
        timeout=15,
        check=check,
    )


def install(dry_run: bool) -> int:
    actions = [
        f"copy runtime to {INSTALL_SCRIPT}",
        f"write LaunchAgent {PLIST_FILE}",
        f"merge four owned hooks into {CLAUDE_SETTINGS}",
        f"bootstrap {LABEL} for gui/{os.getuid()}",
    ]
    if dry_run:
        print("Dry run; no files changed:")
        for action in actions:
            print(f"- {action}")
        print("- optional closed-lid mode requires the exact sudoers rule documented in SKILL.md")
        return 0

    source = Path(__file__).resolve()
    SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, INSTALL_SCRIPT)
    os.chmod(INSTALL_SCRIPT, 0o755)

    settings = safe_json_load(CLAUDE_SETTINGS, {})
    if not isinstance(settings, dict):
        raise RuntimeError(f"Refusing to overwrite invalid JSON object: {CLAUDE_SETTINGS}")
    if CLAUDE_SETTINGS.exists():
        backup = CLAUDE_SETTINGS.with_name("settings.json.mac-awake.bak")
        if not backup.exists():
            shutil.copy2(CLAUDE_SETTINGS, backup)
    atomic_json_write(CLAUDE_SETTINGS, merge_claude_hooks(settings))

    with PLIST_FILE.open("wb") as handle:
        plistlib.dump(plist_payload(), handle, sort_keys=False)

    domain = f"gui/{os.getuid()}"
    launchctl("bootout", domain, str(PLIST_FILE))
    result = launchctl("bootstrap", domain, str(PLIST_FILE))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "launchctl bootstrap failed")
    launchctl("kickstart", "-k", f"{domain}/{LABEL}")
    print(f"Installed {LABEL}.")
    print(f"Status: /usr/bin/python3 '{INSTALL_SCRIPT}' status")
    print("Closed-lid mode: configure the exact sudoers rule in SKILL.md, then restart the agent.")
    return 0


def uninstall(dry_run: bool) -> int:
    targets = [INSTALL_SCRIPT, PLIST_FILE]
    if dry_run:
        print("Dry run; would unload the LaunchAgent, remove its runtime/plist, and remove owned Claude hooks:")
        for target in targets:
            print(f"- {target}")
        return 0

    domain = f"gui/{os.getuid()}"
    launchctl("bootout", domain, str(PLIST_FILE))
    settings = safe_json_load(CLAUDE_SETTINGS, {})
    if isinstance(settings, dict) and CLAUDE_SETTINGS.exists():
        atomic_json_write(CLAUDE_SETTINGS, remove_claude_hooks(settings))
    for target in targets:
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Could not remove {target}: {exc}") from exc
    subprocess.run(
        ["/usr/bin/sudo", "-n", "/usr/bin/pmset", "-a", "disablesleep", "0"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
        check=False,
    )
    print(f"Uninstalled {LABEL}. Logs and state were retained for diagnosis.")
    print("Remove /etc/sudoers.d/mac-awake separately with sudo if it was configured.")
    return 0


def format_status(snapshot: dict[str, Any]) -> str:
    lines = [
        f"tasks_active={str(snapshot['tasks_active']).lower()}",
        f"thermal_block={str(snapshot['thermal_block']).lower()}",
        f"keep_awake={str(snapshot['keep_awake']).lower()}",
    ]
    for name, source in snapshot["sources"].items():
        line = f"{name}: active={source['active']} ({source['detail']})"
        if source.get("error"):
            line += f" [warning: {source['error']}]"
        lines.append(line)
    return "\n".join(lines)


def daemon(poll_seconds: int, foreground: bool) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_handle = LOCK_FILE.open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if foreground:
            print("mac-awake daemon is already running", file=sys.stderr)
        return 0

    stop = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    monitor = TaskMonitor()
    controller = AwakeController()
    log(f"watchdog up poll={poll_seconds}s")
    try:
        while not stop:
            cleanup_expired_logs()
            snapshot = monitor.snapshot()
            active_sources = ",".join(
                name
                for name, value in snapshot["sources"].items()
                if value["active"] > 0
            ) or "none"
            reason = "thermal" if snapshot["thermal_block"] else active_sources
            controller.set_awake(bool(snapshot["keep_awake"]), reason)
            if foreground:
                print(format_status(snapshot), flush=True)
            deadline = time.monotonic() + poll_seconds
            while not stop and time.monotonic() < deadline:
                time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
    finally:
        controller.close()
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()
    return 0


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="mac-awake-test-") as directory:
        root = Path(directory)
        marker_dir = root / "state" / "claude"
        codex_home = root / "codex"
        orca_support = root / "orca"
        marker_dir.mkdir(parents=True)
        (marker_dir / "session-1").touch()
        monitor = TaskMonitor(marker_dir, codex_home, orca_support)
        assert monitor.claude_state().active == 1

        rollout = root / "rollout.jsonl"
        rollout.write_text(
            json.dumps({"type": "event_msg", "payload": {"type": "task_started"}}) + "\n",
            encoding="utf-8",
        )
        codex_home.mkdir(parents=True)
        database = sqlite3.connect(codex_home / "state_5.sqlite")
        database.execute(
            "CREATE TABLE threads (rollout_path TEXT, archived INTEGER, updated_at INTEGER)"
        )
        database.execute(
            "INSERT INTO threads VALUES (?, 0, ?)", (str(rollout), int(time.time()))
        )
        database.commit()
        database.close()
        assert monitor._rollout_state(rollout) == "task_started"
        assert monitor.codex_state().active == 1
        with rollout.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "response_item", "payload": {"type": "message"}}) + "\n")
            handle.write(json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}}) + "\n")
        assert monitor._rollout_state(rollout) == "task_complete"
        assert monitor.codex_state().active == 0

        fixture = {
            "agents": [
                {"state": "working", "subagents": [{"state": "waiting"}]},
                {"state": "done"},
            ]
        }
        assert monitor._count_active_agent_objects(fixture) == 2
        assert sanitize_id("a/b:c") == "a_b_c"

        fixed_now = time.mktime(time.strptime("2026-08-02 12:00:00", "%Y-%m-%d %H:%M:%S"))
        test_log = root / "mac-awake.log"
        rotated_log = root / "mac-awake.log.1"
        error_log = root / "mac-awake.err.log"
        old_line = "2026-08-01 11:59:59 old\n"
        recent_line = "2026-08-01 12:00:01 recent\n"
        test_log.write_text(old_line + recent_line, encoding="utf-8")
        rotated_log.write_text(old_line, encoding="utf-8")
        error_log.write_text("old stderr\n", encoding="utf-8")
        old_mtime = fixed_now - LOG_RETENTION_SECONDS - 1
        os.utime(error_log, (old_mtime, old_mtime))
        cleanup_expired_logs(
            current_time=fixed_now,
            structured_paths=(test_log, rotated_log),
            unstructured_paths=(error_log,),
        )
        assert test_log.read_text(encoding="utf-8") == recent_line
        assert not rotated_log.exists()
        assert not error_log.exists()

        settings = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo keep"}]}]}}
        merged = merge_claude_hooks(settings)
        merged_again = merge_claude_hooks(merged)
        owned = sum(
            1
            for groups in merged_again["hooks"].values()
            for group in groups
            for item in group.get("hooks", [])
            if "# mac-awake" in item.get("command", "")
        )
        assert owned == 4
        removed = remove_claude_hooks(merged_again)
        assert "# mac-awake" not in json.dumps(removed)
        assert "echo keep" in json.dumps(removed)

    print("self-test: PASS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Keep macOS awake only while Claude, Codex/ChatGPT, or Orca tasks run."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    status_parser = subparsers.add_parser("status", help="detect active tasks without changing sleep state")
    status_parser.add_argument("--json", action="store_true", help="emit JSON")
    daemon_parser = subparsers.add_parser("daemon", help="run the watchdog")
    daemon_parser.add_argument("--poll", type=int, default=DEFAULT_POLL_SECONDS)
    daemon_parser.add_argument("--foreground", action="store_true")
    heartbeat_parser = subparsers.add_parser("heartbeat", help="Claude hook endpoint")
    heartbeat_parser.add_argument("action", choices=("touch", "remove"), nargs="?", default="touch")
    install_parser = subparsers.add_parser("install", help="install runtime, LaunchAgent, and Claude hooks")
    install_parser.add_argument("--dry-run", action="store_true")
    uninstall_parser = subparsers.add_parser("uninstall", help="remove owned runtime, plist, and hooks")
    uninstall_parser.add_argument("--dry-run", action="store_true")
    subparsers.add_parser("self-test", help="run deterministic tests without system changes")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "status":
            snapshot = TaskMonitor().snapshot()
            print(json.dumps(snapshot, ensure_ascii=False, indent=2) if args.json else format_status(snapshot))
            return 0
        if args.command == "daemon":
            if args.poll < 1:
                parser.error("--poll must be at least 1 second")
            return daemon(args.poll, args.foreground)
        if args.command == "heartbeat":
            return heartbeat(args.action)
        if args.command == "install":
            return install(args.dry_run)
        if args.command == "uninstall":
            return uninstall(args.dry_run)
        if args.command == "self-test":
            return self_test()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"mac-awake: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

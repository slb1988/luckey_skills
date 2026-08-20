#!/usr/bin/python3
"""Install and verify Memory Hub hooks for Claude Code, Codex, and Pi."""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import selectors
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List


SKILL_DIR = Path(__file__).resolve().parent.parent
MEMORY_HOOK = SKILL_DIR / "scripts" / "memory_hook.py"
PI_TEMPLATE = SKILL_DIR / "assets" / "pi-memory-hub.ts"
ALIAS_TEMPLATE = SKILL_DIR / "assets" / "project-aliases.json"
ALIAS_FILENAME = "project-aliases.json"
MANAGED_COMMAND_MARKER = "memory-hub/scripts/memory_hook.py"

PROFILE_BLOCK_BEGIN = "# >>> memory-hub identity >>>"
PROFILE_BLOCK_END = "# <<< memory-hub identity <<<"


class InstallError(RuntimeError):
    pass


def default_python() -> str:
    return "/usr/bin/python3" if Path("/usr/bin/python3").is_file() else sys.executable


def python_command(*args: str) -> str:
    return shlex.join([default_python(), str(MEMORY_HOOK), *args])


def desired_hooks(agent: str) -> Dict[str, Dict[str, Any]]:
    if agent not in ("claude", "codex"):
        raise ValueError("unsupported JSON hook agent: %s" % agent)
    session_end_timeout = 3 if agent == "codex" else 120
    hooks: Dict[str, Dict[str, Any]] = {
        "SessionStart": {
            "type": "command",
            "command": python_command("recall", "--source", agent),
            "timeout": 10,
        },
        "UserPromptSubmit": {
            "type": "command",
            "command": python_command("recall", "--source", agent),
            "timeout": 10,
        },
        "Stop": {
            "type": "command",
            "command": python_command("capture", "--source", agent),
            "timeout": 120,
        },
        "SessionEnd": {
            "type": "command",
            "command": python_command("capture", "--source", agent),
            "timeout": session_end_timeout,
        },
    }
    if agent == "codex":
        hooks["Stop"]["statusMessage"] = "Archiving session to Memory Hub"
    return hooks


def is_managed_handler(handler: Any) -> bool:
    return (
        isinstance(handler, dict)
        and isinstance(handler.get("command"), str)
        and MANAGED_COMMAND_MARKER in handler["command"].replace("\\", "/")
    )


def load_json_object(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InstallError("cannot read valid JSON from %s: %s" % (path, error))
    if not isinstance(value, dict):
        raise InstallError("expected a JSON object in %s" % path)
    return value


def remove_managed_handlers(data: Dict[str, Any]) -> None:
    hooks = data.get("hooks")
    if hooks is None:
        data["hooks"] = {}
        return
    if not isinstance(hooks, dict):
        raise InstallError("top-level hooks must be an object")
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            raise InstallError("hooks.%s must be an array" % event)
        retained_groups = []
        for group in groups:
            if not isinstance(group, dict):
                raise InstallError("hooks.%s entries must be objects" % event)
            handlers = group.get("hooks")
            if not isinstance(handlers, list):
                raise InstallError("hooks.%s[].hooks must be an array" % event)
            retained = [handler for handler in handlers if not is_managed_handler(handler)]
            if retained:
                copied = dict(group)
                copied["hooks"] = retained
                retained_groups.append(copied)
        if retained_groups:
            hooks[event] = retained_groups
        else:
            del hooks[event]


def render_json_hooks(existing: Dict[str, Any], agent: str) -> Dict[str, Any]:
    data = json.loads(json.dumps(existing))
    remove_managed_handlers(data)
    hooks = data.setdefault("hooks", {})
    for event, handler in desired_hooks(agent).items():
        hooks.setdefault(event, []).append({"hooks": [handler]})
    return data


def atomic_write(path: Path, content: str, mode: int = 0o600) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + ".memory-hub.bak")
        shutil.copy2(path, backup)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else mode)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return True


def install_json_hooks(path: Path, agent: str) -> bool:
    existing = load_json_object(path)
    rendered = render_json_hooks(existing, agent)
    return atomic_write(path, json.dumps(rendered, ensure_ascii=False, indent=2) + "\n")


def managed_handlers(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = []
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError("top-level hooks must be an object")
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise InstallError("hooks.%s must be an array" % event)
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise InstallError("hooks.%s[].hooks must be an array" % event)
            for handler in group["hooks"]:
                if is_managed_handler(handler):
                    result.append({"event": event, **handler})
    return result


def check_json_hooks(path: Path, agent: str) -> Dict[str, Any]:
    data = load_json_object(path)
    actual = managed_handlers(data)
    expected = desired_hooks(agent)
    errors = []
    by_event = {entry["event"]: entry for entry in actual}
    if len(actual) != len(expected):
        errors.append("expected %d managed hooks, found %d" % (len(expected), len(actual)))
    for event, handler in expected.items():
        found = by_event.get(event)
        if found is None:
            errors.append("missing %s" % event)
            continue
        comparable = {key: value for key, value in found.items() if key != "event"}
        if comparable != handler:
            errors.append("%s handler differs from the managed definition" % event)
    return {"ok": not errors, "path": str(path), "errors": errors, "hooks": len(actual)}


VERSION_PATTERN = re.compile(r'EXTENSION_VERSION\s*=\s*"([^"]+)"')


def pi_extension_version(content: str) -> str:
    match = VERSION_PATTERN.search(content)
    return match.group(1) if match else "unknown"


def render_pi_extension() -> str:
    template = PI_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("__MEMORY_HOOK_JSON__", json.dumps(str(MEMORY_HOOK))).replace(
        "__PYTHON_JSON__", json.dumps(default_python())
    )


def install_pi_extension(path: Path) -> bool:
    return atomic_write(path, render_pi_extension(), mode=0o600)


def check_pi_extension(path: Path) -> Dict[str, Any]:
    errors = []
    managed = render_pi_extension()
    managed_version = pi_extension_version(managed)
    installed_version = None
    if not path.is_file():
        errors.append("extension file is missing")
    else:
        content = path.read_text(encoding="utf-8")
        installed_version = pi_extension_version(content)
        if installed_version != managed_version:
            errors.append(
                "extension version %s is outdated (managed %s); rerun install"
                % (installed_version, managed_version)
            )
        elif content != managed:
            errors.append("extension differs from the managed definition")
        if "--flush-limit" in content:
            errors.append("agent_end must upload instead of deferring the flush")
        for event in ("before_agent_start", "agent_end", "session_shutdown"):
            if 'pi.on("%s"' % event not in content:
                errors.append("missing %s handler" % event)
    return {
        "ok": not errors,
        "path": str(path),
        "errors": errors,
        "version": installed_version,
        "managed_version": managed_version,
    }


class CodexAppServer:
    def __init__(self, executable: str, codex_home: Path):
        env = os.environ.copy()
        env["CODEX_HOME"] = str(codex_home)
        self.process = subprocess.Popen(
            [executable, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        if self.process.stdin is None or self.process.stdout is None:
            raise InstallError("failed to open Codex app-server pipes")
        # selectors/select() does not work on anonymous pipes on Windows;
        # use a reader thread + queue which is portable.
        self.lines: "queue.Queue[str]" = queue.Queue()
        self.reader = threading.Thread(
            target=self._read_lines, args=(self.process.stdout, self.lines), daemon=True
        )
        self.reader.start()
        self.next_id = 1
        self.request(
            "initialize",
            {
                "clientInfo": {"name": "memory-hub-hook-installer", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        self._send({"method": "initialized"})

    @staticmethod
    def _read_lines(stream: Any, out: "queue.Queue[str]") -> None:
        try:
            for line in stream:
                out.put(line)
        except Exception:
            pass
        out.put("")

    def _send(self, message: Dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        self._send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=max(0.05, deadline - time.monotonic()))
            except queue.Empty:
                break
            if not line:
                break
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise InstallError("Codex %s failed: %s" % (method, response["error"]))
            result = response.get("result")
            if not isinstance(result, dict):
                raise InstallError("Codex %s returned an invalid response" % method)
            return result
        raise InstallError("Codex %s timed out" % method)

    def close(self) -> None:
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)

    def __enter__(self) -> "CodexAppServer":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def codex_memory_hooks(result: Dict[str, Any], hooks_path: Path) -> List[Dict[str, Any]]:
    entries = result.get("data")
    if not isinstance(entries, list) or not entries:
        raise InstallError("Codex hooks/list returned no entries")
    errors = []
    warnings = []
    hooks = []
    expected_path = str(hooks_path.resolve())
    for entry in entries:
        errors.extend(entry.get("errors") or [])
        warnings.extend(entry.get("warnings") or [])
        for hook in entry.get("hooks") or []:
            if hook.get("sourcePath") == expected_path and MANAGED_COMMAND_MARKER in str(
                hook.get("command") or ""
            ).replace("\\", "/"):
                hooks.append(hook)
    if errors:
        raise InstallError("Codex hook errors: %s" % json.dumps(errors, ensure_ascii=False))
    relevant_warnings = [warning for warning in warnings if "memory_hook" in warning]
    if relevant_warnings:
        raise InstallError("Codex hook warnings: %s" % "; ".join(relevant_warnings))
    return hooks


def quoted_key_segment(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def verify_or_trust_codex(
    codex_home: Path,
    cwd: Path,
    executable: str,
    apply_trust: bool,
) -> Dict[str, Any]:
    hooks_path = codex_home / "hooks.json"
    config_path = codex_home / "config.toml"
    with CodexAppServer(executable, codex_home) as server:
        listed = server.request("hooks/list", {"cwds": [str(cwd.resolve())]})
        hooks = codex_memory_hooks(listed, hooks_path)
        if len(hooks) != 4:
            raise InstallError("Codex expected 4 Memory Hub hooks, found %d" % len(hooks))
        events = {hook.get("eventName") for hook in hooks}
        expected_events = {"sessionStart", "userPromptSubmit", "stop", "sessionEnd"}
        if events != expected_events:
            raise InstallError("Codex Memory Hub event set is incomplete: %s" % sorted(events))
        pending = [hook for hook in hooks if hook.get("trustStatus") != "trusted"]
        if pending and apply_trust:
            edits = []
            for hook in pending:
                key = str(hook["key"])
                current_hash = hook.get("currentHash")
                if not isinstance(current_hash, str) or not current_hash.startswith("sha256:"):
                    raise InstallError("Codex returned an invalid hook hash for %s" % key)
                edits.append(
                    {
                        "keyPath": 'hooks.state."%s".trusted_hash'
                        % quoted_key_segment(key),
                        "value": current_hash,
                        "mergeStrategy": "upsert",
                    }
                )
            server.request(
                "config/batchWrite",
                {
                    "filePath": str(config_path),
                    "reloadUserConfig": True,
                    "edits": edits,
                },
            )
            listed = server.request("hooks/list", {"cwds": [str(cwd.resolve())]})
            hooks = codex_memory_hooks(listed, hooks_path)
        statuses = {hook.get("trustStatus") for hook in hooks}
        if statuses != {"trusted"}:
            raise InstallError("Codex Memory Hub hooks are not all trusted: %s" % sorted(statuses))
        return {"ok": True, "trusted": len(hooks), "path": str(hooks_path)}


def alias_state_dir(home: Path) -> Path:
    override = os.environ.get("MEMORY_HOOK_STATE_DIR")
    if override:
        return Path(override).expanduser()
    return home / ".local" / "state" / "memory-hub-hook"


def _alias_version(data: Any) -> str:
    return str(data.get("version") or "") if isinstance(data, dict) else ""


def install_project_aliases(home: Path) -> Dict[str, Any]:
    """把 assets/project-aliases.json 部署到 hook state dir。

    memory_hook.py（三端 hook capture）与 upload_sessions.py（批量归档）都读
    这份本地副本，保证 project 归并口径一致。atomic_write 自带 .memory-hub.bak
    备份与 unchanged 短路。
    """
    target = alias_state_dir(home) / ALIAS_FILENAME
    try:
        content = ALIAS_TEMPLATE.read_text(encoding="utf-8")
        data = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise InstallError("alias template unreadable: %s" % error)
    if not isinstance(data, dict) or not isinstance(data.get("aliases"), dict):
        raise InstallError("alias template has no 'aliases' object")
    changed = atomic_write(target, content if content.endswith("\n") else content + "\n")
    return {
        "ok": True,
        "changed": changed,
        "path": str(target),
        "version": _alias_version(data),
    }


def check_project_aliases(home: Path) -> Dict[str, Any]:
    target = alias_state_dir(home) / ALIAS_FILENAME
    try:
        template_data = json.loads(ALIAS_TEMPLATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"ok": False, "errors": ["alias template unreadable: %s" % error]}
    template_version = _alias_version(template_data)
    if not target.exists():
        return {
            "ok": False,
            "errors": ["project aliases not installed; rerun install"],
            "path": str(target),
        }
    try:
        installed_data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"ok": False, "errors": ["project aliases unreadable: %s" % error]}
    installed_version = _alias_version(installed_data)
    if template_version and installed_version != template_version:
        return {
            "ok": False,
            "errors": [
                "project aliases version %s is outdated (managed %s); rerun install"
                % (installed_version or "<none>", template_version)
            ],
            "path": str(target),
        }
    return {
        "ok": True,
        "errors": [],
        "path": str(target),
        "version": installed_version,
    }


def health_check() -> Dict[str, Any]:
    url = os.environ.get("MEMORY_HUB_URL", "http://10.77.77.6:9287").rstrip("/")
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + "/health/ready", timeout=5) as response:
            result = json.loads(response.read())
        ready = (
            result.get("status") == "ready"
            and result.get("dependencies", {}).get("graphiti") is True
            and result.get("dependencies", {}).get("metadata") is True
            and result.get("write_degraded") is False
        )
        return {"ok": ready, "url": url, "response": result}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        return {"ok": False, "url": url, "error": str(error)}


def resolve_identity(args: argparse.Namespace) -> Dict[str, str]:
    """install 必须确定用户身份：优先命令行，其次已有环境变量。"""
    user_id = (
        args.user_id
        or os.environ.get("MEMORY_HUB_CLIENT_USER_ID")
        or os.environ.get("MEMORY_HUB_USER_ID")
        or ""
    ).strip()
    if not user_id:
        raise InstallError(
            "install requires --user-id (or a preset MEMORY_HUB_CLIENT_USER_ID)"
        )
    return {"MEMORY_HUB_CLIENT_USER_ID": user_id}


def persist_env_windows(values: Dict[str, str]) -> bool:
    """写入 HKCU\\Environment（用户级）并广播 WM_SETTINGCHANGE。返回是否有变化。"""
    import winreg

    changed = False
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
    ) as key:
        for name, value in values.items():
            try:
                current, _ = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                current = None
            if current != value:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
                changed = True
    if changed:
        try:
            import ctypes

            ctypes.windll.user32.SendMessageTimeoutW(
                0xFFFF,  # HWND_BROADCAST
                0x001A,  # WM_SETTINGCHANGE
                0,
                "Environment",
                0x0002,  # SMTO_ABORTIFHUNG
                5000,
                ctypes.byref(ctypes.c_ulong()),
            )
        except Exception:
            pass  # 广播失败不影响注册表持久化结果
    return changed


def persist_env_posix(values: Dict[str, str], home: Path) -> List[str]:
    """以标记块写入 ~/.profile（macOS 同时写 ~/.zprofile），返回涉及的文件。"""
    block_lines = [PROFILE_BLOCK_BEGIN]
    for name, value in values.items():
        block_lines.append("export %s=%s" % (name, shlex.quote(value)))
    block_lines.append(PROFILE_BLOCK_END)
    block = "\n".join(block_lines)
    pattern = re.compile(
        re.escape(PROFILE_BLOCK_BEGIN) + ".*?" + re.escape(PROFILE_BLOCK_END), re.DOTALL
    )
    targets = [home / ".profile"]
    if sys.platform == "darwin":
        targets.append(home / ".zprofile")
    written = []
    for target in targets:
        content = target.read_text(encoding="utf-8") if target.exists() else ""
        if pattern.search(content):
            updated = pattern.sub(block, content)
        elif content.strip():
            updated = content.rstrip("\n") + "\n\n" + block + "\n"
        else:
            updated = block + "\n"
        if updated != content:
            target.write_text(updated, encoding="utf-8")
        written.append(str(target))
    return written


def persist_identity(values: Dict[str, str], home: Path) -> Dict[str, Any]:
    """把身份三项持久化到用户级环境变量，全局进程默认读取。"""
    for name, value in values.items():
        os.environ[name] = value
    if os.name == "nt":
        changed = persist_env_windows(values)
        return {
            "user_id": values["MEMORY_HUB_CLIENT_USER_ID"],
            "backend": "registry:HKCU\\Environment",
            "changed": changed,
            "vars": sorted(values),
        }
    files = persist_env_posix(values, home)
    return {
        "user_id": values["MEMORY_HUB_CLIENT_USER_ID"],
        "backend": "shell-profile",
        "files": files,
        "vars": sorted(values),
    }


def identity_status() -> Dict[str, Any]:
    """check 用的只读身份状态。"""
    user_id = os.environ.get("MEMORY_HUB_CLIENT_USER_ID") or os.environ.get(
        "MEMORY_HUB_USER_ID"
    )
    return {
        "user_id": user_id,
        "source": "environment" if user_id else "missing",
    }


def parse_agents(value: str, home: Path) -> List[str]:
    supported = ("claude", "codex", "pi")
    if value == "all":
        return list(supported)
    if value == "auto":
        directories = {
            "claude": home / ".claude",
            "codex": home / ".codex",
            "pi": home / ".pi" / "agent",
        }
        commands = {"claude": "claude", "codex": "codex", "pi": "pi"}
        detected = [
            agent
            for agent in supported
            if directories[agent].exists() or shutil.which(commands[agent])
        ]
        if not detected:
            raise InstallError("no supported agent was detected; use --agents all")
        return detected
    requested = [item.strip().lower() for item in value.split(",") if item.strip()]
    invalid = sorted(set(requested) - set(supported))
    if invalid:
        raise InstallError("unsupported agents: %s" % ", ".join(invalid))
    return list(dict.fromkeys(requested))


def agent_paths(home: Path) -> Dict[str, Path]:
    return {
        "claude": home / ".claude" / "settings.json",
        "codex": home / ".codex" / "hooks.json",
        "pi": home / ".pi" / "agent" / "extensions" / "memory-hub.ts",
    }


def run(action: str, agents: Iterable[str], home: Path, codex_bin: str, cwd: Path) -> Dict[str, Any]:
    paths = agent_paths(home)
    results: Dict[str, Any] = {}
    for agent in agents:
        try:
            if action == "install":
                if agent in ("claude", "codex"):
                    changed = install_json_hooks(paths[agent], agent)
                else:
                    changed = install_pi_extension(paths[agent])
            else:
                changed = False
            if agent in ("claude", "codex"):
                check = check_json_hooks(paths[agent], agent)
            else:
                check = check_pi_extension(paths[agent])
            if not check["ok"]:
                raise InstallError("; ".join(check["errors"]))
            if agent == "codex":
                config_path = home / ".codex" / "config.toml"
                if action == "install" and not config_path.exists():
                    atomic_write(config_path, "")
                trust = verify_or_trust_codex(
                    home / ".codex", cwd, codex_bin, apply_trust=action == "install"
                )
                check.update(trust)
            results[agent] = {"ok": True, "changed": changed, **check}
        except (InstallError, OSError, UnicodeError, subprocess.SubprocessError) as error:
            results[agent] = {"ok": False, "error": str(error), "path": str(paths[agent])}
    return {"ok": all(value.get("ok") for value in results.values()), "agents": results}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory-hub-install-hooks")
    parser.add_argument("action", choices=("install", "check"))
    parser.add_argument("--agents", default="auto", help="auto, all, or comma-separated agents")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--codex-bin", default=shutil.which("codex") or "codex")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument(
        "--user-id",
        default=None,
        help="Memory Hub user id; install 时必填，持久化到用户环境变量 MEMORY_HUB_CLIENT_USER_ID",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        agents = parse_agents(args.agents, args.home)
        result = run(args.action, agents, args.home, args.codex_bin, args.cwd)
        if args.action == "install":
            identity = resolve_identity(args)
            result["identity"] = persist_identity(identity, args.home)
            result["project_aliases"] = install_project_aliases(args.home)
        else:
            result["identity"] = identity_status()
            result["project_aliases"] = check_project_aliases(args.home)
        if not result["project_aliases"].get("ok"):
            result["ok"] = False
        result["service"] = health_check()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    except InstallError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

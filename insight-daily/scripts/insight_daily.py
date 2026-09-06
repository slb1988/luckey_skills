#!/usr/bin/env python3
"""Extract selected daily-note sections and run Memory Hub daily insights.

The client is intentionally standard-library-only.  Source verification and
manifest verification are local operations; --dry-run never opens a socket.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


MANIFEST_SCHEMA = "insight-daily-manifest/1"
INPUT_SCHEMA = "insight-daily-input/1"
RUN_SCHEMA = "insight-daily-run/1"
EXTRACTOR_VERSION = "1"
DEFAULT_HUB_URL = "http://10.77.77.6:9287"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_POLL_SECONDS = 1.0
STATE_SUBDIR = Path("insight-daily") / "manifests"
TEAM_SETTINGS_PATH = Path(".team") / "settings.local.json"
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WINDOWS_PATH_PATTERN = re.compile(r"^(?:[A-Za-z]:|\\\\)")
ATX_HEADING_PATTERN = re.compile(r"^[ \t]{0,3}(#{1,6})(?:[ \t]+)(.*?)[ \t]*$")
FENCE_PATTERN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
EMPTY_LIST_PATTERN = re.compile(r"^[-*+]\s*(?:\[[ xX]?\]?)?\s*$")
HORIZONTAL_RULE_PATTERN = re.compile(r"^(?:[-*_][ \t]*){3,}$")

_RAW_SECTION_ALIASES: Dict[str, Tuple[str, ...]] = {
    "daily_success": (
        "DailySucc",
        "Daily Succ",
        "Daily Success",
        "今日成果",
        "今日完成",
        "今日成功",
    ),
    "todo": ("TODO", "TO DO", "待办", "待办事项"),
    "decisions": ("决策", "今日决策", "决策记录", "Decision", "Decisions"),
    "long_term_goals": (
        "长期目标",
        "长期目标变动",
        "长期目标变化",
        "长期目标更新",
        "Long-term Goals",
        "Long Term Goals",
    ),
}


class InsightDailyError(RuntimeError):
    """Stable, non-secret-bearing CLI error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True)
class Section:
    key: str
    heading: str
    occurrence: int
    start_line: int
    end_line: int
    source_text: str
    payload_text: str

    def manifest_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "heading": self.heading,
            "occurrence": self.occurrence,
            "locator": "L%d-L%d" % (self.start_line, self.end_line),
            "start_line": self.start_line,
            "end_line": self.end_line,
            "source_sha256": sha256_text(self.source_text),
            "payload_sha256": sha256_text(self.payload_text),
        }


@dataclass(frozen=True)
class PreparedDaily:
    vault_root: Path
    note_path: Path
    note_relative: str
    local_date: str
    note_bytes: bytes
    note_text: str
    note_sha256: str
    sections: Tuple[Section, ...]
    sections_md: str
    sections_sha256: str

    def extraction_manifest(self) -> Dict[str, Any]:
        return {
            "extractor_version": EXTRACTOR_VERSION,
            "sections_count": len(self.sections),
            "sections_chars": len(self.sections_md),
            "sections_sha256": self.sections_sha256,
            "sections": [section.manifest_dict() for section in self.sections],
        }


@dataclass(frozen=True)
class ClientConfig:
    base_url: str
    dashboard_url: str
    api_key: Optional[str]
    user_id: Optional[str]
    project_id: str
    state_dir: Path
    request_timeout: float = 15.0


@dataclass(frozen=True)
class PersonaCardIdentity:
    person_id: Optional[str]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical_json_bytes(value: Dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def normalize_heading(value: str) -> str:
    value = HTML_TAG_PATTERN.sub("", value)
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    # Remove presentation-only emoji/punctuation/spacing while keeping letters and CJK.
    return "".join(character for character in value if character.isalnum())


SECTION_ALIASES: Dict[str, set[str]] = {
    key: {normalize_heading(alias) for alias in aliases}
    for key, aliases in _RAW_SECTION_ALIASES.items()
}


def section_key_for_heading(heading: str) -> Optional[str]:
    normalized = normalize_heading(heading)
    for key, aliases in SECTION_ALIASES.items():
        if normalized in aliases:
            return key
    return None


def strip_heading_closer(value: str) -> str:
    return re.sub(r"[ \t]+#+[ \t]*$", "", value).strip()


def _scan_headings(lines: Sequence[str]) -> List[Tuple[int, int, str]]:
    headings: List[Tuple[int, int, str]] = []
    fence_character: Optional[str] = None
    fence_length = 0
    for index, line in enumerate(lines):
        raw = line.rstrip("\r\n")
        fence = FENCE_PATTERN.match(raw)
        if fence:
            marker = fence.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
                continue
            if marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            continue
        if fence_character is not None:
            continue
        match = ATX_HEADING_PATTERN.match(raw)
        if not match:
            continue
        title = strip_heading_closer(match.group(2))
        if title:
            headings.append((index, len(match.group(1)), title))
    return headings


def _section_has_content(source_text: str) -> bool:
    lines = source_text.splitlines()
    if lines:
        lines = lines[1:]
    body = "\n".join(lines)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if ATX_HEADING_PATTERN.match(stripped):
            continue
        if stripped in {"```", "~~~"}:
            continue
        if HORIZONTAL_RULE_PATTERN.fullmatch(stripped):
            continue
        if EMPTY_LIST_PATTERN.fullmatch(stripped):
            continue
        # The current daily template contains an intentionally incomplete "- [".
        if stripped in {"- [", "* [", "+ ["}:
            continue
        return True
    return False


def extract_sections(note_text: str) -> Tuple[Tuple[Section, ...], str]:
    lines = note_text.splitlines(keepends=True)
    headings = _scan_headings(lines)
    relevant_seen = 0
    occurrences: Dict[str, int] = {}
    extracted: List[Section] = []
    for heading_index, (start_index, level, heading) in enumerate(headings):
        if level != 2:
            continue
        key = section_key_for_heading(heading)
        if key is None:
            continue
        relevant_seen += 1
        end_index = len(lines)
        for candidate_index, candidate_level, _ in headings[heading_index + 1 :]:
            if candidate_level <= 2:
                end_index = candidate_index
                break
        source_text = "".join(lines[start_index:end_index])
        if not _section_has_content(source_text):
            continue
        occurrences[key] = occurrences.get(key, 0) + 1
        payload_text = source_text.rstrip("\r\n")
        section = Section(
            key=key,
            heading=heading,
            occurrence=occurrences[key],
            start_line=start_index + 1,
            end_line=max(start_index + 1, end_index),
            source_text=source_text,
            payload_text=payload_text,
        )
        # Local literal check: locator lines must reproduce the selected source exactly.
        if "".join(lines[start_index:end_index]) != section.source_text:
            raise InsightDailyError(
                "LOCATOR_MISMATCH", "section locator did not reproduce the source text"
            )
        extracted.append(section)
    if relevant_seen == 0:
        raise InsightDailyError(
            "NO_RELEVANT_SECTIONS",
            "no DailySucc, TODO, decision, or long-term-goal section was found",
        )
    if not extracted:
        raise InsightDailyError(
            "EMPTY_SECTIONS",
            "relevant sections exist but contain only empty template placeholders",
        )
    sections_md = "\n\n".join(section.payload_text for section in extracted) + "\n"
    return tuple(extracted), sections_md


def validate_date(raw: str) -> str:
    if not DATE_PATTERN.fullmatch(raw):
        raise InsightDailyError("INVALID_DATE", "date must use YYYY-MM-DD")
    try:
        return dt.date.fromisoformat(raw).isoformat()
    except ValueError as error:
        raise InsightDailyError("INVALID_DATE", "date is not a real calendar day") from error


def _lexically_safe_relative(raw: str, label: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise InsightDailyError("UNSAFE_PATH", "%s must not be empty" % label)
    value = raw.strip()
    if "\x00" in value or "\\" in value or WINDOWS_PATH_PATTERN.match(value):
        raise InsightDailyError(
            "UNSAFE_PATH", "%s must be a vault-relative POSIX path" % label
        )
    path = Path(value)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise InsightDailyError(
            "UNSAFE_PATH", "%s must stay inside the configured vault" % label
        )
    return path


def _confined(root: Path, relative: Path, label: str) -> Path:
    resolved_root = root.expanduser().resolve()
    try:
        resolved = (resolved_root / relative).resolve()
        resolved.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError) as error:
        raise InsightDailyError(
            "UNSAFE_PATH", "%s resolves outside the configured vault" % label
        ) from error
    return resolved


def discover_vault(start: Optional[Path] = None) -> Path:
    candidates: List[Path] = []
    for origin in (start or Path.cwd(), Path(__file__).resolve().parent):
        try:
            resolved = origin.expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if not resolved.is_dir():
            resolved = resolved.parent
        candidates.extend([resolved, *resolved.parents])
    seen: set[str] = set()
    for candidate in candidates:
        marker = str(candidate)
        if marker in seen:
            continue
        seen.add(marker)
        if (candidate / ".obsidian" / "daily-notes.json").is_file():
            return candidate.resolve()
        luckey = candidate / "luckey"
        if (luckey / ".obsidian" / "daily-notes.json").is_file():
            return luckey.resolve()
    raise InsightDailyError(
        "VAULT_NOT_FOUND",
        "could not locate a vault containing .obsidian/daily-notes.json",
    )


def daily_folder(vault_root: Path) -> Path:
    config_path = vault_root / ".obsidian" / "daily-notes.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InsightDailyError(
            "DAILY_NOTES_CONFIG_NOT_FOUND", "missing .obsidian/daily-notes.json"
        ) from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InsightDailyError(
            "BAD_DAILY_NOTES_CONFIG", "daily-notes.json is unreadable or invalid JSON"
        ) from error
    if not isinstance(config, dict) or not isinstance(config.get("folder"), str):
        raise InsightDailyError(
            "BAD_DAILY_NOTES_CONFIG", "daily-notes.json must contain a string folder"
        )
    folder_relative = _lexically_safe_relative(config["folder"], "daily notes folder")
    return _confined(vault_root, folder_relative, "daily notes folder")


def resolve_note(
    vault_root: Path,
    local_date: str,
    note_argument: Optional[str] = None,
) -> Path:
    folder = daily_folder(vault_root)
    if note_argument:
        relative = _lexically_safe_relative(note_argument, "note")
        if len(relative.parts) == 1:
            candidate = (folder / relative).resolve()
        else:
            candidate = _confined(vault_root, relative, "note")
    else:
        candidate = (folder / (local_date + ".md")).resolve()
    try:
        candidate.relative_to(vault_root.resolve())
    except ValueError as error:
        raise InsightDailyError("UNSAFE_PATH", "note resolves outside the vault") from error
    if candidate.parent != folder.resolve():
        raise InsightDailyError(
            "UNSAFE_PATH", "note must be a direct child of the configured daily notes folder"
        )
    expected_name = local_date + ".md"
    if candidate.name != expected_name:
        raise InsightDailyError(
            "NOTE_DATE_MISMATCH",
            "note filename must be %s for the selected date" % expected_name,
        )
    if not candidate.is_file():
        raise InsightDailyError(
            "NOTE_NOT_FOUND",
            "daily note does not exist; run daily-report first or pass --date/--note",
            details={"note": candidate.relative_to(vault_root.resolve()).as_posix()},
        )
    return candidate


def prepare_daily(
    vault_root: Path,
    local_date: str,
    note_argument: Optional[str] = None,
) -> PreparedDaily:
    canonical_date = validate_date(local_date)
    root = vault_root.expanduser().resolve()
    note = resolve_note(root, canonical_date, note_argument)
    try:
        note_bytes = note.read_bytes()
        note_text = note_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InsightDailyError("NOTE_NOT_UTF8", "daily note must be UTF-8") from error
    except OSError as error:
        raise InsightDailyError("NOTE_READ_FAILED", "daily note could not be read") from error
    sections, sections_md = extract_sections(note_text)
    return PreparedDaily(
        vault_root=root,
        note_path=note,
        note_relative=note.relative_to(root).as_posix(),
        local_date=canonical_date,
        note_bytes=note_bytes,
        note_text=note_text,
        note_sha256=sha256_bytes(note_bytes),
        sections=sections,
        sections_md=sections_md,
        sections_sha256=sha256_text(sections_md),
    )


def read_persisted_env_var(name: str) -> Optional[str]:
    """Read only the user-level stores written by memory-hub install hooks."""
    if os.name == "nt":
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_QUERY_VALUE
            ) as key:
                value, _ = winreg.QueryValueEx(key, name)
            return str(value) if value else None
        except (OSError, FileNotFoundError):
            return None
    pattern = re.compile(
        r"^\s*export\s+" + re.escape(name) + r"\s*=\s*(.+?)\s*$", re.MULTILINE
    )
    for filename in (".profile", ".zprofile", ".bash_profile"):
        try:
            content = (Path.home() / filename).read_text(encoding="utf-8")
        except OSError:
            continue
        value: Optional[str] = None
        for match in pattern.finditer(content):
            raw = match.group(1).strip()
            value = raw.strip("'\"") if raw else None
        if value:
            return value
    return None


def load_team_user_id(start: Path) -> Optional[str]:
    try:
        resolved = start.resolve()
    except (OSError, RuntimeError):
        return None
    for directory in (resolved, *resolved.parents):
        path = directory / TEAM_SETTINGS_PATH
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        value = payload.get("currentMember") if isinstance(payload, dict) else None
        if isinstance(value, str) and IDENTIFIER_PATTERN.fullmatch(value.strip()):
            return value.strip()
        return None
    return None


def load_profile_user_id(state_dir: Path) -> Optional[str]:
    try:
        payload = json.loads((state_dir / "client-profile.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    value = payload.get("user_id") if isinstance(payload, dict) else None
    if isinstance(value, str) and IDENTIFIER_PATTERN.fullmatch(value.strip()):
        return value.strip()
    return None


def normalize_project_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._:-]+", "-", value.strip().lower()).strip("-._:")
    return normalized[:128] or "obsidianvault"


def derive_dashboard_url(base_url: str) -> str:
    explicit = os.environ.get("MEMORY_HUB_DASHBOARD_URL")
    if explicit:
        return explicit.rstrip("/") + "/"
    parsed = urllib.parse.urlsplit(base_url)
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is not None:
        host = parsed.hostname or "localhost"
        if ":" in host and not host.startswith("["):
            host = "[%s]" % host
        netloc = host + ":" + str(9288 if port == 9287 else port + 1)
        return urllib.parse.urlunsplit((parsed.scheme or "http", netloc, "/", "", ""))
    return base_url.rstrip("/") + "/"


def client_config(vault_root: Path, *, require_auth: bool = True) -> ClientConfig:
    state_dir = Path(
        os.environ.get(
            "MEMORY_HOOK_STATE_DIR",
            str(Path.home() / ".local" / "state" / "memory-hub-hook"),
        )
    ).expanduser()
    base_url = (
        os.environ.get("MEMORY_HUB_URL")
        or os.environ.get("BASE_URL")
        or read_persisted_env_var("MEMORY_HUB_URL")
        or read_persisted_env_var("BASE_URL")
        or DEFAULT_HUB_URL
    ).rstrip("/")
    api_key = os.environ.get("MEMORY_HUB_API_KEY") or read_persisted_env_var(
        "MEMORY_HUB_API_KEY"
    )
    user_id = (
        os.environ.get("MEMORY_HUB_CLIENT_USER_ID")
        or os.environ.get("CLIENT_USER_ID")
        or os.environ.get("MEMORY_HUB_USER_ID")
        or read_persisted_env_var("MEMORY_HUB_CLIENT_USER_ID")
        or read_persisted_env_var("CLIENT_USER_ID")
        or load_team_user_id(vault_root)
        or load_profile_user_id(state_dir)
    )
    if user_id and not IDENTIFIER_PATTERN.fullmatch(user_id):
        raise InsightDailyError("INVALID_USER_ID", "configured client user id is invalid")
    if require_auth and not api_key:
        raise InsightDailyError(
            "MISSING_API_KEY",
            "MEMORY_HUB_API_KEY is missing; rerun the Memory Hub hook installer",
        )
    if require_auth and not user_id:
        raise InsightDailyError(
            "MISSING_USER_ID",
            "client user id is missing; rerun the Memory Hub hook installer",
        )
    project_source = vault_root.parent.name if vault_root.name.lower() == "luckey" else vault_root.name
    project_id = normalize_project_id(
        os.environ.get("MEMORY_HUB_PROJECT_ID", project_source)
    )
    request_timeout = float(os.environ.get("MEMORY_HOOK_TIMEOUT_SECONDS", "15"))
    return ClientConfig(
        base_url=base_url,
        dashboard_url=derive_dashboard_url(base_url),
        api_key=api_key,
        user_id=user_id,
        project_id=project_id,
        state_dir=state_dir,
        request_timeout=max(0.05, request_timeout),
    )


class HubClient:
    def __init__(self, config: ClientConfig) -> None:
        self.config = config
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        body = None
        headers = {
            "Accept": "application/json",
            "X-Agent-Id": "insight-daily",
            "X-Project-Id": self.config.project_id,
            "X-User-Id": self.config.user_id or "",
        }
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        if json_body is not None:
            body = canonical_json_bytes(json_body)
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.config.base_url + path,
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with self.opener.open(
                request, timeout=timeout or self.config.request_timeout
            ) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            raw = error.read()
            code = "UNAUTHENTICATED" if error.code == 401 else "HTTP_%d" % error.code
            try:
                decoded = json.loads(raw.decode("utf-8"))
                remote_error = decoded.get("error") if isinstance(decoded, dict) else None
                remote_code = remote_error.get("code") if isinstance(remote_error, dict) else None
                if isinstance(remote_code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", remote_code):
                    code = remote_code
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            message = {
                "UNAUTHENTICATED": "Memory Hub rejected the configured agent token",
                "PERSON_NOT_FOUND": "no active self persona is available; create one or pass --person-id",
            }.get(code, "Memory Hub returned HTTP %d" % error.code)
            raise InsightDailyError(code, message, status_code=error.code) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise InsightDailyError(
                "NETWORK_ERROR", "Memory Hub request failed or timed out"
            ) from error
        if not payload:
            raise InsightDailyError("BAD_RESPONSE", "Memory Hub returned an empty response")
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InsightDailyError(
                "BAD_RESPONSE", "Memory Hub returned invalid JSON"
            ) from error
        if not isinstance(value, dict):
            raise InsightDailyError(
                "BAD_RESPONSE", "Memory Hub returned a non-object response"
            )
        return value

    def submit_input(
        self, prepared: PreparedDaily, person_id: Optional[str]
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "schema_version": INPUT_SCHEMA,
            "sections_md": prepared.sections_md,
            "note_path": prepared.note_relative,
            "note_sha256": prepared.note_sha256,
        }
        if person_id:
            body["person_id"] = person_id
        response = self.request(
            "POST",
            "/v1/insights/daily/%s/input" % prepared.local_date,
            json_body=body,
        )
        created = response.get("created")
        item = response.get("input")
        if not isinstance(created, bool) or not isinstance(item, dict):
            raise InsightDailyError("BAD_RESPONSE", "daily input response has an invalid shape")
        for key in ("input_id", "person_id", "content_sha256", "note_path", "note_sha256"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise InsightDailyError(
                    "BAD_RESPONSE", "daily input response is missing %s" % key
                )
        if item["content_sha256"] != prepared.sections_sha256:
            raise InsightDailyError(
                "CONTENT_HASH_MISMATCH", "Hub input hash does not match the selected sections"
            )
        if item["note_path"] != prepared.note_relative or item["note_sha256"] != prepared.note_sha256:
            raise InsightDailyError(
                "NOTE_MANIFEST_MISMATCH",
                "Hub idempotent input metadata does not match the current daily note",
            )
        return {"created": created, "input": item}

    def create_run(
        self,
        prepared: PreparedDaily,
        *,
        input_id: str,
        person_id: Optional[str],
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "schema_version": RUN_SCHEMA,
            "input_id": input_id,
        }
        if person_id:
            body["person_id"] = person_id
        response = self.request(
            "POST",
            "/v1/insights/daily/%s/run" % prepared.local_date,
            json_body=body,
        )
        created = response.get("created")
        run = response.get("run")
        if not isinstance(created, bool) or not isinstance(run, dict):
            raise InsightDailyError("BAD_RESPONSE", "daily run response has an invalid shape")
        self.validate_run(run)
        return {"created": created, "run": run}

    @staticmethod
    def validate_run(run: Dict[str, Any]) -> None:
        if not isinstance(run.get("run_id"), str) or not run["run_id"]:
            raise InsightDailyError("BAD_RESPONSE", "run response is missing run_id")
        status = run.get("status")
        if status not in {"queued", "running", "done", "failed"}:
            raise InsightDailyError("BAD_RESPONSE", "run response contains an unknown status")
        for key in ("sources_total", "sources_processed", "proposals_created"):
            value = run.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InsightDailyError(
                    "BAD_RESPONSE", "run response contains an invalid %s" % key
                )

    def get_run(self, run_id: str, *, timeout: Optional[float] = None) -> Dict[str, Any]:
        path_id = urllib.parse.quote(run_id, safe="")
        run = self.request("GET", "/v1/insights/runs/%s" % path_id, timeout=timeout)
        self.validate_run(run)
        if run["run_id"] != run_id:
            raise InsightDailyError("BAD_RESPONSE", "run response id does not match the request")
        return run


def build_manifest(
    prepared: PreparedDaily,
    *,
    person_id: Optional[str] = None,
    input_id: Optional[str] = None,
    run_id: Optional[str] = None,
    status: str = "prepared",
    input_created: Optional[bool] = None,
    run_created: Optional[bool] = None,
    sources_total: int = 0,
    sources_processed: int = 0,
    proposals_created: int = 0,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA,
        "local_date": prepared.local_date,
        "note": {
            "path": prepared.note_relative,
            "sha256": prepared.note_sha256,
            "size_bytes": len(prepared.note_bytes),
        },
        "extraction": prepared.extraction_manifest(),
        "hub": {
            "person_id": person_id,
            "input_id": input_id,
            "run_id": run_id,
            "status": status,
            "input_created": input_created,
            "run_created": run_created,
            "sources_total": sources_total,
            "sources_processed": sources_processed,
            "proposals_created": proposals_created,
            "error": error,
        },
    }


def write_manifest(state_dir: Path, manifest: Dict[str, Any]) -> Path:
    canonical = canonical_json_bytes(manifest)
    digest = sha256_bytes(canonical)
    directory = state_dir.expanduser() / STATE_SUBDIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (digest + ".json")
    if path.is_file():
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise InsightDailyError("MANIFEST_WRITE_FAILED", "manifest could not be read") from error
        if existing.rstrip(b"\n") != canonical:
            raise InsightDailyError(
                "MANIFEST_HASH_COLLISION", "existing content-addressed manifest differs"
            )
        return path
    temporary_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=str(directory), prefix=".manifest-", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(canonical + b"\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        return path
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise InsightDailyError(
            "MANIFEST_WRITE_FAILED", "manifest could not be written atomically"
        ) from error


def _manifest_summary(
    prepared: PreparedDaily,
    manifest_path: Path,
    manifest: Dict[str, Any],
    dashboard_url: str,
) -> Dict[str, Any]:
    hub = manifest["hub"]
    person_id = hub.get("person_id")
    dashboard = dashboard_url.rstrip("/") + "/#persona"
    if person_id:
        dashboard += "?person=%s&section=proposals" % urllib.parse.quote(
            str(person_id), safe=""
        )
    return {
        "ok": hub.get("status") in {"done", "dry_run"},
        "command": "run",
        "status": hub.get("status"),
        "date": prepared.local_date,
        "note_path": prepared.note_relative,
        "sections": len(prepared.sections),
        "sections_sha256": prepared.sections_sha256,
        "person_id": person_id,
        "input_id": hub.get("input_id"),
        "run_id": hub.get("run_id"),
        "proposals_created": hub.get("proposals_created", 0),
        "manifest_path": str(manifest_path),
        "dashboard_url": dashboard,
    }


def _run_counts(run: Dict[str, Any]) -> Tuple[int, int, int]:
    return (
        int(run.get("sources_total", 0)),
        int(run.get("sources_processed", 0)),
        int(run.get("proposals_created", 0)),
    )


def execute_run(
    *,
    vault_root: Path,
    local_date: str,
    note_argument: Optional[str],
    person_id: Optional[str],
    dry_run: bool,
    timeout_seconds: float,
    poll_seconds: Optional[float] = None,
    config: Optional[ClientConfig] = None,
) -> Dict[str, Any]:
    if person_id and not IDENTIFIER_PATTERN.fullmatch(person_id):
        raise InsightDailyError("INVALID_PERSON_ID", "person id has an invalid format")
    if timeout_seconds <= 0:
        raise InsightDailyError("INVALID_TIMEOUT", "timeout must be greater than zero")
    prepared = prepare_daily(vault_root, local_date, note_argument)
    local_config = config or client_config(vault_root, require_auth=not dry_run)
    manifest = build_manifest(
        prepared,
        person_id=person_id,
        status="dry_run" if dry_run else "prepared",
    )
    manifest_path = write_manifest(local_config.state_dir, manifest)
    if dry_run:
        return _manifest_summary(
            prepared, manifest_path, manifest, local_config.dashboard_url
        )

    client = HubClient(local_config)
    try:
        input_result = client.submit_input(prepared, person_id)
    except InsightDailyError as error:
        error.details.setdefault("manifest_path", str(manifest_path))
        raise
    item = input_result["input"]
    resolved_person_id = item["person_id"]
    manifest = build_manifest(
        prepared,
        person_id=resolved_person_id,
        input_id=item["input_id"],
        status="input_ready",
        input_created=input_result["created"],
    )
    manifest_path = write_manifest(local_config.state_dir, manifest)
    try:
        run_result = client.create_run(
            prepared,
            input_id=item["input_id"],
            person_id=person_id,
        )
    except InsightDailyError as error:
        error.details.setdefault("manifest_path", str(manifest_path))
        error.details.setdefault("input_id", item["input_id"])
        raise
    run = run_result["run"]
    run_id = run["run_id"]
    sources_total, sources_processed, proposals_created = _run_counts(run)
    manifest = build_manifest(
        prepared,
        person_id=resolved_person_id,
        input_id=item["input_id"],
        run_id=run_id,
        status=run["status"],
        input_created=input_result["created"],
        run_created=run_result["created"],
        sources_total=sources_total,
        sources_processed=sources_processed,
        proposals_created=proposals_created,
        error=run.get("error") if isinstance(run.get("error"), str) else None,
    )
    manifest_path = write_manifest(local_config.state_dir, manifest)

    deadline = time.monotonic() + timeout_seconds
    interval = poll_seconds
    if interval is None:
        try:
            interval = float(
                os.environ.get("INSIGHT_DAILY_POLL_INTERVAL", str(DEFAULT_POLL_SECONDS))
            )
        except ValueError:
            interval = DEFAULT_POLL_SECONDS
    interval = max(0.001, interval)
    while run["status"] not in {"done", "failed"}:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timeout_manifest = build_manifest(
                prepared,
                person_id=resolved_person_id,
                input_id=item["input_id"],
                run_id=run_id,
                status="timeout",
                input_created=input_result["created"],
                run_created=run_result["created"],
                sources_total=sources_total,
                sources_processed=sources_processed,
                proposals_created=proposals_created,
            )
            manifest_path = write_manifest(local_config.state_dir, timeout_manifest)
            raise InsightDailyError(
                "POLL_TIMEOUT",
                "insight run did not reach done/failed before the timeout",
                details={
                    "run_id": run_id,
                    "manifest_path": str(manifest_path),
                },
            )
        time.sleep(min(interval, remaining))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            continue
        run = client.get_run(
            run_id, timeout=min(local_config.request_timeout, max(0.05, remaining))
        )
        sources_total, sources_processed, proposals_created = _run_counts(run)

    error_code = run.get("error") if isinstance(run.get("error"), str) else None
    manifest = build_manifest(
        prepared,
        person_id=resolved_person_id,
        input_id=item["input_id"],
        run_id=run_id,
        status=run["status"],
        input_created=input_result["created"],
        run_created=run_result["created"],
        sources_total=sources_total,
        sources_processed=sources_processed,
        proposals_created=proposals_created,
        error=error_code,
    )
    manifest_path = write_manifest(local_config.state_dir, manifest)
    summary = _manifest_summary(
        prepared, manifest_path, manifest, local_config.dashboard_url
    )
    if run["status"] == "failed":
        raise InsightDailyError(
            "RUN_FAILED",
            "insight run failed%s"
            % (" (%s)" % error_code if error_code else ""),
            details={
                "run_id": run_id,
                "manifest_path": str(manifest_path),
                "proposals_created": proposals_created,
            },
        )
    return summary


def load_manifest(path: Path) -> Dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except FileNotFoundError as error:
        raise InsightDailyError("MANIFEST_NOT_FOUND", "manifest file does not exist") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InsightDailyError("BAD_MANIFEST", "manifest is unreadable or invalid JSON") from error
    if not isinstance(value, dict):
        raise InsightDailyError("BAD_MANIFEST", "manifest root must be an object")
    expected_name = sha256_bytes(canonical_json_bytes(value)) + ".json"
    if path.name != expected_name:
        raise InsightDailyError(
            "MANIFEST_HASH_MISMATCH",
            "manifest filename does not match its canonical content hash",
        )
    return value


def verify_manifest(
    manifest_path: Path,
    *,
    vault_root: Path,
    note_argument: Optional[str] = None,
) -> Dict[str, Any]:
    manifest = load_manifest(manifest_path.expanduser().resolve())
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise InsightDailyError("BAD_MANIFEST", "unsupported manifest schema")
    local_date = manifest.get("local_date")
    note = manifest.get("note")
    extraction = manifest.get("extraction")
    if not isinstance(local_date, str) or not isinstance(note, dict) or not isinstance(extraction, dict):
        raise InsightDailyError("BAD_MANIFEST", "manifest is missing source metadata")
    note_path = note.get("path")
    if not isinstance(note_path, str):
        raise InsightDailyError("BAD_MANIFEST", "manifest note path is invalid")
    prepared = prepare_daily(
        vault_root,
        local_date,
        note_argument if note_argument is not None else note_path,
    )
    expected_note = {
        "path": prepared.note_relative,
        "sha256": prepared.note_sha256,
        "size_bytes": len(prepared.note_bytes),
    }
    if note != expected_note:
        raise InsightDailyError(
            "NOTE_HASH_MISMATCH", "daily note bytes/path no longer match the manifest"
        )
    expected_extraction = prepared.extraction_manifest()
    if extraction != expected_extraction:
        raise InsightDailyError(
            "LOCATOR_MISMATCH",
            "selected sections, hashes, or line locators no longer match the vault source",
        )
    return {
        "ok": True,
        "command": "verify",
        "manifest_path": str(manifest_path.expanduser().resolve()),
        "date": prepared.local_date,
        "note_path": prepared.note_relative,
        "sections": len(prepared.sections),
        "sections_sha256": prepared.sections_sha256,
        "network_requests": 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="insight-daily")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="extract a daily note and run persona insights")
    run.add_argument("--date")
    run.add_argument("--note")
    run.add_argument("--person-id")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--json", action="store_true")
    run.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    run.add_argument("--vault", help=argparse.SUPPRESS)
    verify = commands.add_parser("verify", help="verify a content-addressed manifest locally")
    verify.add_argument("manifest")
    verify.add_argument("--note")
    verify.add_argument("--json", action="store_true")
    verify.add_argument("--vault", help=argparse.SUPPRESS)
    return parser


def print_human_run(result: Dict[str, Any]) -> None:
    status = result["status"]
    if status == "dry_run":
        print(
            "Insight Daily dry-run: %d verified section(s), zero network requests"
            % result["sections"]
        )
    else:
        print(
            "Insight Daily done: %d proposal(s), run %s"
            % (result["proposals_created"], result["run_id"])
        )
    print("Manifest: %s" % result["manifest_path"])
    print("Dashboard: %s" % result["dashboard_url"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    json_mode = bool(getattr(args, "json", False))
    try:
        vault = discover_vault(Path(args.vault)) if getattr(args, "vault", None) else discover_vault()
        if args.command == "run":
            local_date = args.date or dt.date.today().isoformat()
            result = execute_run(
                vault_root=vault,
                local_date=local_date,
                note_argument=args.note,
                person_id=args.person_id,
                dry_run=args.dry_run,
                timeout_seconds=args.timeout,
            )
            if json_mode:
                print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            else:
                print_human_run(result)
            return 0
        result = verify_manifest(
            Path(args.manifest), vault_root=vault, note_argument=args.note
        )
        if json_mode:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        else:
            print(
                "Insight Daily manifest verified: %d section(s), zero network requests"
                % result["sections"]
            )
            print("Manifest: %s" % result["manifest_path"])
        return 0
    except InsightDailyError as error:
        if json_mode:
            print(
                json.dumps(
                    {"ok": False, "error": error.as_dict()},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            print("insight-daily: %s: %s" % (error.code, error.message), file=sys.stderr)
            if error.details:
                for key in ("run_id", "input_id", "manifest_path", "note"):
                    if key in error.details:
                        print("%s: %s" % (key, error.details[key]), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

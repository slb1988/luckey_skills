#!/usr/bin/env python3
"""Manual bulk upload of historical agent session transcripts to Memory Hub.

Uploads Claude Code / Pi / Codex session transcripts (.jsonl) as independent
immutable sessions, each with a searchable ``session_summary`` memory.

Idempotent by design:

* Transcripts are wrapped into a single JSON document
  (``agent-session-archive/1``) before upload, because Memory Hub validates
  that session files parse as JSON; raw .jsonl does not. The wrapper keeps
  every original event at full fidelity and serializes deterministically.
* The file SHA-256 is computed over that deterministic JSON document, so it
  is stable across machines and re-runs.
* Before uploading, the script fetches the existing session and compares the
  latest version's ``content_sha256``; a match means ``skipped``.
* All mutating calls use deterministic ``Idempotency-Key`` headers derived
  from ``{session_id}:{sha256}``, so interrupted runs can be safely retried.

Only the Python standard library is used.

Examples
--------
# Upload every Pi/Claude session found under a directory (auto-detect):
python upload_sessions.py --project-id unity2018 ~/.pi/agent/sessions/--E--sununity--

# Upload specific files with explicit identities:
python upload_sessions.py --source claude --agent-id claude-code \
    --project-id unity2018 --user-id sun session1.jsonl session2.jsonl

# See what would happen without touching the server:
python upload_sessions.py --project-id unity2018 --dry-run <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9._:-]+")
FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
WHITESPACE_RE = re.compile(r"\s+")
MAX_MESSAGE_CHARS = 4000
MAX_DISTILLED_CHARS = 16 * 1024
DEFAULT_HUB_URL = "http://10.77.77.6:9287"
SOURCE_AGENT_DEFAULTS = {"claude": "claude-code", "pi": "pi", "codex": "codex"}


def normalize_identifier(value: str, fallback: str) -> str:
    normalized = IDENTIFIER_RE.sub("-", value.strip()).strip("-._:")
    if not normalized or not normalized[0].isalnum():
        normalized = fallback
    return normalized[:128]


def compact_text(value: str, limit: int) -> str:
    return WHITESPACE_RE.sub(" ", value).strip()[:limit]


def sanitize_message_text(value: str) -> str:
    return FENCED_CODE_RE.sub("\n", value).strip()[:MAX_MESSAGE_CHARS]


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(part for part in (flatten_text(item) for item in value) if part)
    if not isinstance(value, dict):
        return ""
    for key in ("text", "message", "content"):
        if key in value:
            text = flatten_text(value[key])
            if text:
                return text
    return ""


# ---------------------------------------------------------------------------
# Session file scanning
# ---------------------------------------------------------------------------


@dataclass
class SessionFile:
    path: Path
    source: str  # claude | pi | codex
    source_session_id: str
    archive_session_id: str
    cwd: str
    started_at: str
    payload: bytes  # JSON document wrapping the transcript events
    size_bytes: int
    sha256: str
    event_count: int = 0
    first_user: str = ""
    last_user: str = ""
    last_assistant: str = ""


def detect_source(path: Path, head_records: List[Dict[str, Any]]) -> Optional[str]:
    """Detect which agent produced a transcript from path + content."""
    normalized = str(path).replace("\\", "/")
    if "/.claude/projects/" in normalized:
        return "claude"
    if "/.pi/agent/sessions/" in normalized:
        return "pi"
    if "/.codex/" in normalized:
        return "codex"
    for record in head_records:
        if record.get("type") == "session" and record.get("id"):
            return "pi"  # pi transcripts open with {"type":"session",...}
        if record.get("sessionId"):
            return "claude"
        payload = record.get("payload")
        if isinstance(payload, dict) and payload.get("type"):
            return "codex"
    return None


def extract_session_id(
    path: Path, source: str, head_records: List[Dict[str, Any]]
) -> Optional[str]:
    if source == "pi":
        for record in head_records:
            if record.get("type") == "session" and record.get("id"):
                return str(record["id"])
        stem = path.stem
        if "_" in stem:  # 2026-07-20T15-44-15-604Z_<uuid>.jsonl
            return stem.rsplit("_", 1)[-1]
        return stem or None
    if source == "claude":
        for record in head_records:
            if record.get("sessionId"):
                return str(record["sessionId"])
        return path.stem or None
    # codex / unknown: fall back to filename
    return path.stem or None


def build_archive_payload(
    path: Path, source: str, source_session_id: str, cwd: str, events: List[Dict[str, Any]]
) -> bytes:
    """Wrap raw jsonl events in one valid JSON document.

    Memory Hub validates that session files parse as JSON; raw .jsonl is NOT
    valid JSON (trailing garbage after the first line). Wrapping preserves
    full transcript fidelity while passing validation. Serialization is
    deterministic (compact separators, insertion-ordered keys) so the same
    transcript always yields the same SHA-256 across machines.
    """
    document = {
        "schema_version": "agent-session-archive/1",
        "source": {
            "agent": source,
            "session_id": source_session_id,
            "cwd": cwd,
            "transcript_path": str(path),
            "format": "jsonl",
        },
        "event_count": len(events),
        "events": events,
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def scan_session_file(path: Path, forced_source: Optional[str]) -> Optional[SessionFile]:
    """Read a transcript once, extracting identity + summary material."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        print("  [error] cannot read %s: %s" % (path, error), file=sys.stderr)
        return None
    if not raw.strip():
        print("  [skip] empty file: %s" % path)
        return None

    head_records: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    cwd = ""
    started_at = ""
    first_user = ""
    last_user = ""
    last_assistant = ""
    codex_session_id = ""

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                events.append({"type": "unparsed", "raw": line.rstrip("\n")})
                continue
            if not isinstance(record, dict):
                events.append({"type": "unparsed", "raw": line.rstrip("\n")})
                continue
            events.append(record)
            if line_number < 50:
                head_records.append(record)
            if not cwd and isinstance(record.get("cwd"), str):
                cwd = record["cwd"]
            if not started_at and isinstance(record.get("timestamp"), str):
                started_at = record["timestamp"]
            if not codex_session_id:
                payload = record.get("payload")
                if isinstance(payload, dict) and payload.get("type") == "session":
                    codex_session_id = str(payload.get("id") or "")
            extracted = extract_role_text(record)
            if not extracted:
                continue
            role, raw_text = extracted
            text = sanitize_message_text(raw_text)
            if not text:
                continue
            if role == "user":
                if not first_user:
                    first_user = text
                last_user = text
            else:
                last_assistant = text

    source = forced_source or detect_source(path, head_records)
    if not source:
        print("  [skip] cannot detect agent source: %s" % path)
        return None
    if source == "codex" and codex_session_id:
        source_session_id = codex_session_id
    else:
        source_session_id = extract_session_id(path, source, head_records)
    if not source_session_id:
        print("  [skip] no session id found: %s" % path)
        return None

    archive_session_id = normalize_identifier(
        "%s:%s" % (source, source_session_id), "%s-session" % source
    )
    payload = build_archive_payload(path, source, source_session_id, cwd, events)
    return SessionFile(
        path=path,
        source=source,
        source_session_id=source_session_id,
        archive_session_id=archive_session_id,
        cwd=cwd,
        started_at=started_at,
        payload=payload,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        event_count=len(events),
        first_user=compact_text(first_user, 700),
        last_user=compact_text(last_user, 700),
        last_assistant=compact_text(last_assistant, 1400),
    )


def extract_role_text(record: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    record_type = record.get("type")
    message = record.get("message")
    if record_type in ("user", "assistant") and isinstance(message, dict):
        text = flatten_text(message.get("content"))
        return (record_type, text) if text else None
    if record_type == "message" and isinstance(message, dict):
        role = message.get("role")
        if role in ("user", "assistant"):
            text = flatten_text(message.get("content"))
            return (role, text) if text else None
    payload = record.get("payload")
    if isinstance(payload, dict):
        payload_type = payload.get("type")
        if payload_type == "user_message":
            text = flatten_text(payload.get("message") or payload.get("content"))
            return ("user", text) if text else None
        role = payload.get("role")
        if role in ("user", "assistant"):
            text = flatten_text(payload.get("content"))
            return (role, text) if text else None
        if payload_type in ("agent_message", "assistant_message"):
            text = flatten_text(payload.get("message") or payload.get("content"))
            return ("assistant", text) if text else None
    return None


def collect_files(paths: List[str]) -> List[Path]:
    files: List[Path] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if path.is_dir():
            files.extend(sorted(path.rglob("*.jsonl")))
        elif path.is_file():
            files.append(path)
        else:
            print("  [warn] path not found: %s" % path, file=sys.stderr)
    # de-duplicate while keeping order
    seen = set()
    unique = []
    for item in files:
        key = str(item.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# ---------------------------------------------------------------------------
# Hub HTTP client
# ---------------------------------------------------------------------------


class HubError(Exception):
    pass


@dataclass
class HubConfig:
    hub_url: str
    user_id: str
    project_id: str
    api_key: Optional[str]
    timeout_seconds: float


class HubClient:
    def __init__(self, config: HubConfig) -> None:
        self.config = config
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def headers(
        self,
        agent_id: str,
        idempotency_key: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> Dict[str, str]:
        headers = {
            "X-User-Id": self.config.user_id,
            "X-Agent-Id": agent_id,
            "X-Project-Id": self.config.project_id,
            "Accept": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def request(
        self,
        method: str,
        path: str,
        agent_id: str,
        body: Optional[bytes] = None,
        json_body: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        content_type: Optional[str] = None,
        allow_404: bool = False,
        retries: int = 1,
    ) -> Optional[Dict[str, Any]]:
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            content_type = "application/json"
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            request = urllib.request.Request(
                self.config.hub_url + path,
                data=body,
                method=method,
                headers=self.headers(agent_id, idempotency_key, content_type),
            )
            try:
                with self.opener.open(request, timeout=self.config.timeout_seconds) as response:
                    payload = response.read()
            except urllib.error.HTTPError as error:
                if allow_404 and error.code == 404:
                    return None
                detail = error.read().decode("utf-8", errors="replace")
                raise HubError("HTTP %s: %s" % (error.code, compact_text(detail, 800)))
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = error
                if attempt < retries:
                    time.sleep(2 * (attempt + 1))
                continue
            if not payload:
                return {}
            try:
                value = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise HubError("invalid JSON response: %s" % error)
            if not isinstance(value, dict):
                raise HubError("unexpected non-object response")
            return value
        raise HubError("network error after retries: %s" % last_error)


# ---------------------------------------------------------------------------
# Upload pipeline
# ---------------------------------------------------------------------------


@dataclass
class UploadResult:
    status: str  # uploaded | skipped | failed
    session_id: str
    detail: str = ""
    version: Optional[int] = None
    memory_id: Optional[str] = None


def idem_key(kind: str, session_id: str, sha256: str) -> str:
    return "manual-upload:%s:%s:%s" % (kind, session_id, sha256[:16])


def ensure_memory(
    client: HubClient, session: "SessionFile", agent_id: str, version: int, file_id: str
) -> str:
    date_part = session.started_at[:10] if session.started_at else "未知日期"
    distilled = (
        "%s 会话归档（%s），工作目录：%s。首个用户目标：%s。最近用户目标：%s。最近会话结果：%s"
        % (
            session.source,
            date_part,
            session.cwd or "未知",
            session.first_user or "未提取到用户文本",
            session.last_user or "未提取到用户文本",
            session.last_assistant or "未提取到助手最终文本",
        )
    )
    memory = client.request(
        "POST",
        "/v1/memories",
        agent_id,
        idempotency_key=idem_key("memory", session.archive_session_id, session.sha256),
        json_body={
            "schema_version": "memory-write/1",
            "agent_id": agent_id,
            "project_id": client.config.project_id,
            "session_id": session.archive_session_id,
            "session_version": version,
            "file_id": file_id,
            "scope_type": "project",
            "memory_type": "session_summary",
            "distilled_content": distilled[:MAX_DISTILLED_CHARS],
            "summary": (session.last_user or session.first_user or "会话归档")[:1024],
            "source_event_id": idem_key("event", session.archive_session_id, session.sha256),
        },
    )
    return str(memory.get("memory_id") or "")


def upload_session(
    client: HubClient, session: SessionFile, agent_id: str
) -> UploadResult:
    sid = session.archive_session_id
    existing = client.request(
        "GET", "/v1/sessions/%s" % sid, agent_id, allow_404=True
    )
    if existing:
        latest_version = int(existing["latest_version"])
        latest = client.request(
            "GET", "/v1/sessions/%s/versions/%s" % (sid, latest_version), agent_id
        )
        if latest and latest.get("content_sha256") == session.sha256:
            memory_id = ensure_memory(
                client, session, agent_id, latest_version, latest["file_id"]
            )
            return UploadResult(
                status="skipped",
                session_id=sid,
                detail="content unchanged",
                version=latest_version,
                memory_id=memory_id,
            )

    upload = client.request(
        "POST",
        "/v1/files/uploads",
        agent_id,
        idempotency_key=idem_key("upload", sid, session.sha256),
        json_body={
            "schema_version": "file-upload/1",
            "purpose": "session_snapshot",
            "media_type": "application/json",
            "compression": "none",
            "size_bytes": session.size_bytes,
            "sha256": session.sha256,
        },
    )
    upload_id = upload["upload_id"]
    file_id = upload["file_id"]
    file_status = client.request("GET", "/v1/files/%s" % file_id, agent_id)
    if not file_status or file_status.get("status") != "available":
        client.request(
            "PUT",
            "/v1/files/uploads/%s/content" % upload_id,
            agent_id,
            body=session.payload,
            content_type="application/json",
        )
        completed = client.request(
            "POST", "/v1/files/uploads/%s/complete" % upload_id, agent_id
        )
        if not completed or completed.get("status") != "available":
            raise HubError("uploaded file did not become available")

    base_version = int(existing["latest_version"]) if existing else None
    version_response = client.request(
        "PUT",
        "/v1/sessions/%s/versions" % sid,
        agent_id,
        idempotency_key=idem_key("session", sid, session.sha256),
        json_body={
            "schema_version": "session-version/1",
            "agent_id": agent_id,
            "project_id": client.config.project_id,
            "file_id": file_id,
            "base_version": base_version,
            "update_mode": "append" if existing else "replace",
            "session_schema": "%s-session" % session.source,
            "session_schema_version": "2",
        },
    )
    version = int(version_response["version"])
    memory_id = ensure_memory(client, session, agent_id, version, file_id)
    return UploadResult(
        status="uploaded", session_id=sid, version=version, memory_id=memory_id
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_default_user_id() -> Optional[str]:
    if os.environ.get("MEMORY_HUB_CLIENT_USER_ID"):
        return os.environ["MEMORY_HUB_CLIENT_USER_ID"]
    state_dir = Path(
        os.environ.get(
            "MEMORY_HOOK_STATE_DIR", Path.home() / ".local" / "state" / "memory-hub-hook"
        )
    )
    profile_path = state_dir / "client-profile.json"
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        user_id = profile.get("user_id")
        if isinstance(user_id, str) and user_id.strip():
            return user_id.strip()
    except (OSError, json.JSONDecodeError):
        pass
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manually upload historical agent session transcripts to Memory Hub (idempotent).",
        epilog="Agents default per source: claude->claude-code, pi->pi, codex->codex.",
    )
    parser.add_argument("paths", nargs="+", help="Session .jsonl files or directories to scan")
    parser.add_argument(
        "--source",
        choices=["auto", "claude", "pi", "codex"],
        default="auto",
        help="Force agent source for all files (default: auto-detect per file)",
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("MEMORY_HUB_PROJECT_ID"),
        help="Target project scope (default: derive from each session's cwd folder name)",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="Memory Hub user id (default: MEMORY_HUB_CLIENT_USER_ID or hook client profile)",
    )
    parser.add_argument(
        "--agent-id",
        default=None,
        help="Override agent id for ALL files (default: per-source claude-code/pi/codex)",
    )
    parser.add_argument(
        "--hub-url",
        default=os.environ.get("MEMORY_HUB_URL", DEFAULT_HUB_URL),
        help="Memory Hub base URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("MEMORY_HUB_API_KEY"),
        help="Bearer token (production only)",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N files")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, no network calls")
    parser.add_argument("--verbose", action="store_true", help="Print per-file details")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    forced_source = None if args.source == "auto" else args.source

    files = collect_files(args.paths)
    if args.limit > 0:
        files = files[: args.limit]
    total = len(files)
    if total == 0:
        print("No session files found under: %s" % ", ".join(args.paths))
        return 1

    user_id = args.user_id or load_default_user_id()
    if not args.dry_run and not user_id:
        print(
            "error: no user id. Pass --user-id or configure the memory-hub hook client profile.",
            file=sys.stderr,
        )
        return 2

    client: Optional[HubClient] = None
    if not args.dry_run:
        client = HubClient(
            HubConfig(
                hub_url=args.hub_url.rstrip("/"),
                user_id=user_id,
                project_id=args.project_id or "",
                api_key=args.api_key,
                timeout_seconds=args.timeout,
            )
        )
        try:
            ready = client.request("GET", "/health/ready", SOURCE_AGENT_DEFAULTS["pi"])
        except HubError as error:
            print("error: Memory Hub not ready at %s: %s" % (args.hub_url, error), file=sys.stderr)
            return 2
        if ready and ready.get("status") != "ready":
            print("warning: hub reports not fully ready: %s" % ready, file=sys.stderr)

    results: List[UploadResult] = []
    failures = 0
    per_project_clients: Dict[str, HubClient] = {}

    for index, path in enumerate(files, 1):
        session = scan_session_file(path, forced_source)
        if session is None:
            failures += 1
            continue
        agent_id = args.agent_id or SOURCE_AGENT_DEFAULTS.get(session.source, session.source)
        project_id = args.project_id or normalize_identifier(
            Path(session.cwd).name if session.cwd else "", "agent-history"
        )

        if args.dry_run or client is None:
            print(
                "[dry-run %d/%d] %s | source=%s agent=%s project=%s session=%s size=%d"
                % (
                    index,
                    total,
                    path.name,
                    session.source,
                    agent_id,
                    project_id,
                    session.archive_session_id,
                    session.size_bytes,
                )
            )
            continue

        # Project can vary per file when derived from cwd; reuse a client per project.
        upload_client = client
        if project_id != client.config.project_id:
            if project_id not in per_project_clients:
                per_project_clients[project_id] = HubClient(
                    HubConfig(
                        hub_url=client.config.hub_url,
                        user_id=client.config.user_id,
                        project_id=project_id,
                        api_key=client.config.api_key,
                        timeout_seconds=client.config.timeout_seconds,
                    )
                )
            upload_client = per_project_clients[project_id]

        try:
            result = upload_session(upload_client, session, agent_id)
        except HubError as error:
            failures += 1
            result = UploadResult(
                status="failed", session_id=session.archive_session_id, detail=str(error)
            )
        results.append(result)
        if args.verbose or result.status == "failed" or index % 50 == 0 or index == total:
            print(
                "[%d/%d] %s | %s | %s %s"
                % (
                    index,
                    total,
                    result.status,
                    result.session_id,
                    path.name,
                    ("| " + result.detail) if result.detail else "",
                )
            )

    if args.dry_run:
        print("dry-run: %d file(s) scanned." % total)
        return 0

    uploaded = sum(1 for r in results if r.status == "uploaded")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")
    print(
        "\nDone. uploaded=%d skipped=%d failed=%d (total scanned=%d)"
        % (uploaded, skipped, failed, total)
    )
    if failed:
        print("Failures:")
        for r in results:
            if r.status == "failed":
                print("  - %s: %s" % (r.session_id, r.detail))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from session_messages import extract_session_pairs

MAX_RECENT_MESSAGES = 10

IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9._:-]+")
FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
WHITESPACE_RE = re.compile(r"\s+")
MAX_MESSAGE_CHARS = 4000
MAX_DISTILLED_CHARS = 16 * 1024
TITLE_MAX_CHARS = 80
TITLE_LLM_DEFAULT_BASE_URL = "http://192.168.2.76:8000/v1"
TITLE_LLM_DEFAULT_MODEL = "qwen3-30b"
THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
TRAILING_PUNCTUATION = "。.!！?？;；,，、~～…-—_ \"'`「」『』《》〈〉:："
NOISE_USER_TEXTS = {
    "hi", "hello", "hey", "你好", "您好", "在吗", "在么", "在",
    "继续", "continue", "ok", "okay", "好的", "好", "嗯", "嗯嗯",
    "test", "测试", "go", "yes", "是", "对", "谢谢", "thanks",
}
DEFAULT_HUB_URL = "http://10.77.77.6:9287"
SOURCE_AGENT_DEFAULTS = {"claude": "claude-code", "pi": "pi", "codex": "codex"}
# 历史目录名归并：E:\sununity 的归档统一进 unity2018 project。
DEFAULT_PROJECT_ALIASES = {"sununity": "unity2018"}


def normalize_identifier(value: str, fallback: str) -> str:
    normalized = IDENTIFIER_RE.sub("-", value.strip()).strip("-._:")
    if not normalized or not normalized[0].isalnum():
        normalized = fallback
    return normalized[:128]


def compact_text(value: str, limit: int) -> str:
    return WHITESPACE_RE.sub(" ", value).strip()[:limit]


def sanitize_message_text(value: str) -> str:
    return FENCED_CODE_RE.sub("\n", value).strip()[:MAX_MESSAGE_CHARS]


def is_noise_user_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    if lowered in NOISE_USER_TEXTS:
        return True
    if stripped.startswith(("<", "/")):  # system-reminder / command wrappers, slash commands
        return True
    if lowered.startswith(("caveat:", "system-reminder")):
        return True
    return False


SKILL_BLOCK_RE = re.compile(r"<skill\s[^>]*>.*?</skill>", re.DOTALL | re.IGNORECASE)


def strip_skill_wrapper(text: str) -> str:
    """剥掉 pi skill 注入的 <skill ...>...</skill> 包装，取出用户真实输入。
    与 memory_hook.py 保持同步。"""
    if "<skill" not in text:
        return text.strip()
    return SKILL_BLOCK_RE.sub("\n", text).strip()


def head_tail_sample(seq: List[str], head: int = 4, tail: int = 4) -> List[str]:
    """整会话抽样：条数超过 head+tail 时保留首（目标）尾（近况），中段抽掉。
    与 memory_hook.py 保持同步。"""
    if len(seq) <= head + tail:
        return list(seq)
    return list(seq[:head]) + list(seq[-tail:])


def clean_llm_title(raw: str) -> str:
    content = THINK_BLOCK_RE.sub(" ", raw)
    first_line = ""
    for line in content.splitlines():
        if line.strip():
            first_line = line.strip()
            break
    return compact_text(first_line.strip(TRAILING_PUNCTUATION), TITLE_MAX_CHARS)


def heuristic_title(user_texts: List[str]) -> str:
    for text in user_texts:
        if not is_noise_user_text(text):
            return compact_text(text, TITLE_MAX_CHARS)
    return ""


def heuristic_meaningful(user_texts: List[str]) -> bool:
    """No-information sessions (pure greetings / model probes) need no archive."""
    if not user_texts:
        return True  # 没有用户文本时保守保留
    return any(not is_noise_user_text(text) for text in user_texts)


def title_llm_enabled() -> bool:
    return os.environ.get("MEMORY_HUB_TITLE_LLM", "0").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def llm_classify_session(user_texts: List[str], last_assistant: str) -> Optional[Dict[str, Any]]:
    """Classify archival value + summarize topic via the intranet LLM.

    Controlled by env (default OFF): MEMORY_HUB_TITLE_LLM=1 enables;
    MEMORY_HUB_TITLE_LLM_BASE_URL / _MODEL / _API_KEY / _TIMEOUT customize.
    Returns {"title": str, "meaningful": bool}, or None on any failure so
    callers fall back to heuristics.
    """
    if not title_llm_enabled():
        return None
    # 整会话判定材料：非噪声用户消息过多时首尾抽样，避免尾部例行消息
    # （如「commit」）盖掉前段的真实任务。与 memory_hook.py 保持同步。
    material = head_tail_sample(
        [text for text in user_texts if text and not is_noise_user_text(text)]
    )
    if not material and not last_assistant:
        return None
    lines = ["用户消息 %d: %s" % (index + 1, text) for index, text in enumerate(material)]
    if not material and user_texts:
        lines = [
            "用户消息 %d: %s" % (index + 1, text)
            for index, text in enumerate(head_tail_sample(user_texts))
        ]
    if last_assistant:
        lines.append("助手最近回复: %s" % compact_text(last_assistant, 200))
    prompt = (
        "你是编程助手会话的归档助手。下面是整个会话的全部用户消息（条数过多时为首尾抽样），"
        "请据此判断这个会话是否有归档价值，并给出主题标题。\n"
        "没有归档价值的会话：只是打招呼、闲聊、测试模型是否可用（如只说了 hi/hello）、"
        "没有任何实际任务或技术内容；以及纯例行运维操作——如 git-tool update/sync/commit 仓库同步、"
        "skill 更新提交、memory-hub check/install 等 hook 安装检查、批量上传 session 归档等机械性维护，"
        "只有命令执行结果、没有可复用的技术内容。注意：运维会话中如果包含真实的故障排查、bug 修复或"
        "技术决策（如发现并修复了某个问题），仍有归档价值。\n"
        "只输出 JSON：{\"meaningful\": true或false, \"title\": \"不超过20字的主题标题，meaningful为false时给空字符串\"}\n\n"
        "整个会话的用户消息：\n" + "\n".join(lines)
    )
    base_url = os.environ.get("MEMORY_HUB_TITLE_LLM_BASE_URL", TITLE_LLM_DEFAULT_BASE_URL).rstrip("/")
    body = {
        "model": os.environ.get("MEMORY_HUB_TITLE_LLM_MODEL", TITLE_LLM_DEFAULT_MODEL),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 128,
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {"type": "json_object"},
    }
    api_key = os.environ.get("MEMORY_HUB_TITLE_LLM_API_KEY", "vllm")
    timeout = float(os.environ.get("MEMORY_HUB_TITLE_LLM_TIMEOUT", "15"))
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        message = choices[0].get("message")
        if not isinstance(message, dict):
            return None
        verdict = json.loads(THINK_BLOCK_RE.sub(" ", str(message.get("content") or "")))
        if not isinstance(verdict, dict):
            return None
        meaningful = verdict.get("meaningful")
        title = clean_llm_title(str(verdict.get("title") or ""))
        return {"title": title, "meaningful": bool(meaningful)}
    except Exception:
        return None


def title_cache_path() -> Path:
    state_dir = os.environ.get("MEMORY_HOOK_STATE_DIR")
    base = Path(state_dir) if state_dir else Path.home() / ".local" / "state" / "memory-hub-hook"
    return base / "title-cache.jsonl"


def load_title_cache(path: Path) -> Dict[str, Dict[str, Any]]:
    cache: Dict[str, Dict[str, Any]] = {}
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sha256 = record.get("sha256")
                title = record.get("title")
                if isinstance(sha256, str) and isinstance(title, str):
                    cache[sha256] = {
                        "title": title,
                        "meaningful": bool(record.get("meaningful", True)),
                    }
    except OSError:
        pass
    return cache


def append_title_cache(path: Path, sha256: str, title: str, meaningful: bool) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"sha256": sha256, "title": title, "meaningful": meaningful},
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        pass


def resolve_classification(
    session: "SessionFile",
    cache: Dict[str, Dict[str, Any]],
    cache_path: Path,
    use_llm: bool,
    persist: bool = True,
) -> None:
    """Decide the session topic title and whether it is worth archiving."""
    cached = cache.get(session.content_sha256)
    if cached is not None:
        session.title = cached["title"]
        session.meaningful = cached["meaningful"]
        return
    verdict = None
    if not session.claude_summary and use_llm:
        verdict = llm_classify_session(session.user_texts, session.last_assistant)
    if verdict is not None:
        meaningful = verdict["meaningful"]
        title = verdict["title"]
    else:
        meaningful = heuristic_meaningful(session.user_texts)
        title = compact_text(session.claude_summary, TITLE_MAX_CHARS) if session.claude_summary else ""
    if not title:
        title = heuristic_title(session.user_texts)
    if not title:
        title = "未命名会话" if meaningful else "（低价值会话）"
    session.title = title
    session.meaningful = meaningful
    if persist:
        cache[session.content_sha256] = {"title": title, "meaningful": meaningful}
        append_title_cache(cache_path, session.content_sha256, title, meaningful)


PROJECT_ALIASES_FILENAME = "project-aliases.json"
PROJECT_LOCAL_FILENAME = "project-aliases.local.json"


def _hook_state_dir() -> Path:
    state_dir = os.environ.get("MEMORY_HOOK_STATE_DIR")
    return (
        Path(state_dir).expanduser()
        if state_dir
        else Path.home() / ".local" / "state" / "memory-hub-hook"
    )


def parse_alias_map(raw: Any) -> Dict[str, str]:
    """把 JSON 里的 aliases 对象解析成 {派生名: project} 映射。

    "*" 是 catch-all：派生名命中不到具体条目时统一落其目标 project。
    """
    if not isinstance(raw, dict):
        return {}
    aliases: Dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        dst = normalize_identifier(value.strip().lower(), "")
        if not dst:
            continue
        if key.strip() == "*":
            aliases["*"] = dst
            continue
        src = normalize_identifier(key.strip().lower(), "")
        if src:
            aliases[src] = dst
    return aliases


def _read_aliases_file(path: Path) -> Dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return parse_alias_map(data.get("aliases"))


def load_installed_project_aliases() -> Dict[str, str]:
    """读取 install_hooks.py 部署到 state dir 的共享模板别名（模板为
    skill 仓库 assets/project-aliases.json），与 memory_hook.py 共用口径。"""
    return _read_aliases_file(_hook_state_dir() / PROJECT_ALIASES_FILENAME)


def load_local_project_aliases() -> Dict[str, str]:
    """读取本机级 project 别名（state dir 的 project-aliases.local.json）。

    本机级映射不进 git、不随 skill 模板扩散，与其他机器的项目完全隔离；
    支持 "*" catch-all（如 {"*": "nas"} = 本机全部归 nas）。
    """
    return _read_aliases_file(_hook_state_dir() / PROJECT_LOCAL_FILENAME)


def _apply_alias_pairs(aliases: Dict[str, str], source: str) -> None:
    for item in source.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            print(
                "warning: ignore invalid project alias %r (expect from=to)" % item,
                file=sys.stderr,
            )
            continue
        src, dst = (part.strip().lower() for part in item.split("=", 1))
        dst = normalize_identifier(dst, "")
        if not dst:
            continue
        if src.strip() == "*":
            aliases["*"] = dst
            continue
        src = normalize_identifier(src, "")
        if src:
            aliases[src] = dst


def load_project_aliases(cli_aliases: Optional[List[str]]) -> Dict[str, str]:
    # 优先级：内置默认 < 环境变量 < 共享模板 JSON < 本机 local JSON < CLI --project-alias。
    aliases = dict(DEFAULT_PROJECT_ALIASES)
    env_value = os.environ.get("MEMORY_HUB_PROJECT_ALIASES", "")
    if env_value:
        _apply_alias_pairs(aliases, env_value)
    aliases.update(load_installed_project_aliases())
    aliases.update(load_local_project_aliases())
    for source in cli_aliases or []:
        _apply_alias_pairs(aliases, source)
    return aliases


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
    content_sha256: str = ""  # title-independent hash; title cache key
    event_count: int = 0
    first_user: str = ""
    last_user: str = ""
    last_assistant: str = ""
    user_texts: List[str] = field(default_factory=list)
    claude_summary: str = ""
    title: str = ""
    meaningful: bool = True
    # 最近消息窗口（backfill-full 模式重建等价快照用；与 hook 的 sanitize 口径一致）
    recent_messages: List[Dict[str, str]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)


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
        "schema_version": "agent-session-archive/2",
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


def finalize_payload(session: "SessionFile") -> None:
    """Embed the resolved topic title into the archive document.

    The title participates in the payload SHA-256, so a tombstoned session
    re-uploaded with a title becomes a genuinely new version instead of
    hitting the "content unchanged" path against a deleted file.
    """
    document = json.loads(session.payload.decode("utf-8"))
    document["archive"] = {"title": session.title}
    session.payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    session.size_bytes = len(session.payload)
    session.sha256 = hashlib.sha256(session.payload).hexdigest()


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
    user_texts: List[str] = []
    recent_messages: deque = deque(maxlen=MAX_RECENT_MESSAGES)
    cwd = ""
    started_at = ""
    first_user = ""
    last_user = ""
    last_assistant = ""
    codex_session_id = ""
    claude_summary = ""

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
            if not claude_summary and record.get("type") == "summary":
                summary_value = record.get("summary")
                if isinstance(summary_value, str):
                    claude_summary = summary_value
            payload = record.get("payload")
            if not cwd and isinstance(record.get("cwd"), str):
                cwd = record["cwd"]
            if not cwd and isinstance(payload, dict) and isinstance(payload.get("cwd"), str):
                # codex 新格式（session_meta）：cwd 在 payload 内
                cwd = payload["cwd"]
            if not started_at and isinstance(record.get("timestamp"), str):
                started_at = record["timestamp"]
            if not codex_session_id and isinstance(payload, dict):
                if payload.get("type") == "session":
                    codex_session_id = str(payload.get("id") or "")
                elif record.get("type") == "session_meta":
                    # codex 新格式：首行 session_meta，真实 uuid 在 payload.id
                    codex_session_id = str(
                        payload.get("id") or payload.get("session_id") or ""
                    )
    source = forced_source or detect_source(path, head_records)
    if not source:
        print("  [skip] cannot detect agent source: %s" % path)
        return None
    for role, raw_text in extract_session_pairs(events, source=source):
        text = sanitize_message_text(raw_text)
        if not text:
            continue
        if role == "user":
            # 剥掉 pi skill 注入包装，否则用户目标被 SKILL.md 模板污染。
            text = strip_skill_wrapper(text)
            if not text:
                continue
        recent_messages.append({"role": role, "content": text})
        if role == "user":
            # 首个/最近用户目标都只取非噪声消息（「hi」「继续」之类不算目标）；
            # 全是噪声时退而求其次取字面首/末条，保证用户目标不为空。
            if not is_noise_user_text(text):
                if not first_user:
                    first_user = text
                last_user = text
            if len(user_texts) < 30:
                user_texts.append(compact_text(text, 300))
        else:
            last_assistant = text
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
    if user_texts:
        # 全是噪声消息时退而求其次，保证用户目标不为空。
        if not first_user:
            first_user = user_texts[0]
        if not last_user:
            last_user = user_texts[-1]
    payload = build_archive_payload(path, source, source_session_id, cwd, events)
    content_sha256 = hashlib.sha256(payload).hexdigest()
    return SessionFile(
        path=path,
        source=source,
        source_session_id=source_session_id,
        archive_session_id=archive_session_id,
        cwd=cwd,
        started_at=started_at,
        payload=payload,
        size_bytes=len(payload),
        sha256=content_sha256,
        content_sha256=content_sha256,
        event_count=len(events),
        first_user=compact_text(first_user, 700),
        last_user=compact_text(last_user, 700),
        last_assistant=compact_text(last_assistant, 1400),
        user_texts=user_texts,
        claude_summary=claude_summary,
        recent_messages=list(recent_messages),
        events=events,
    )


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
    # v2: summary format with LLM/heuristic topic titles; v1 keys must not
    # replay old "会话归档" memories when sessions are re-uploaded.
    return "manual-upload-v2:%s:%s:%s" % (kind, session_id, sha256[:16])


def ensure_memory(
    client: HubClient, session: "SessionFile", agent_id: str, version: int, file_id: str
) -> str:
    topic = session.title or heuristic_title(session.user_texts) or "未命名会话"
    # 归档摘要只保留会话内容本身，不内嵌来源/标题/日期/工作目录等元数据——
    # 元数据由 Hub 侧 source_description 携带，避免被 Graphiti 抽成噪声实体。
    distilled = (
        "首个用户目标：%s。最近用户目标：%s。会话结果：%s"
        % (
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
            "summary": topic[:1024],
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
# Backfill-full：为存量快照 session 补传完整 session 文件（ADR-009 双资产）
# ---------------------------------------------------------------------------
# 语义：只补 full 文件 + 等价快照新版本（纯本地构建），不走 LLM title、不重写
# memory（存量快照链路已执行过，重复执行很费）。session 不存在（hook 从未
# capture 过）则跳过——那些走正常全量上传模式。
# --hook-namespace：正常全量上传但使用 hook 三段式 session_id + 双资产（快照
# /3 + 完整文件 full/1 关联），与 hook capture 产物同轨同构（resume 后 hook
# 继续追加版本，不会产生两段式平行记录）。

import gzip  # noqa: E402  (backfill 段集中使用)


def _gzip_bytes(document: Dict[str, Any]) -> bytes:
    """确定性 gzip（mtime=0）：同一文档跨机器得到同一 SHA-256。"""
    raw = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw, mtime=0)


def _source_format_for(source: str) -> str:
    """与 hub session_usage / dashboard usage_scan / 前端 sessionParse 判定链一致。"""
    return "claude-code-jsonl" if source == "claude" else "jsonl"


def build_full_package_bytes(session: SessionFile, session_id: str) -> bytes:
    """完整 session 文件（agent-session-full/1）：全量事件原样，信息不缺失。"""
    return _gzip_bytes(
        {
            "schema_version": "agent-session-full/1",
            "source": {
                "agent": session.source,
                "session_id": session_id,
                "cwd": session.cwd,
                "transcript_path": str(session.path),
                "format": _source_format_for(session.source),
            },
            "events": session.events,
            "event_count": len(session.events),
        }
    )


def build_backfill_snapshot_bytes(
    session: SessionFile, session_id: str, full_object_name: str, full_sha256: str
) -> bytes:
    """等价窗口快照（agent-session/3）：与 hook 快照同构（最近 N 条消息窗口），
    内嵌 full_session 指针关联完整文件。内容含 full sha → 全量文件变化时快照
    sha 随之变化，commit 幂等键自然失效产生新版本。"""
    return _gzip_bytes(
        {
            "schema_version": "agent-session/3",
            "source": {
                "agent": session.source,
                "session_id": session_id,
                "cwd": session.cwd,
                "transcript_path": str(session.path),
                "format": _source_format_for(session.source),
            },
            "window": {
                "max_messages": MAX_RECENT_MESSAGES,
                "message_count": len(session.recent_messages),
                "fenced_code_removed": True,
            },
            "messages": session.recent_messages,
            "full_session": {
                "object_name": full_object_name,
                "content_sha256": full_sha256,
            },
        }
    )


def _upload_blob(
    client: HubClient,
    agent_id: str,
    idem: str,
    blob: bytes,
    object_name: Optional[str] = None,
) -> str:
    """上传一个 gzip blob（幂等键含内容 sha），返回 file_id。"""
    sha = hashlib.sha256(blob).hexdigest()
    request: Dict[str, Any] = {
        "schema_version": "file-upload/1",
        "purpose": "session_snapshot",
        "media_type": "application/gzip",
        "compression": "gzip",
        "size_bytes": len(blob),
        "sha256": sha,
    }
    if object_name is not None:
        request["object_name"] = object_name
    upload = client.request(
        "POST", "/v1/files/uploads", agent_id, idempotency_key=idem, json_body=request
    )
    upload_id = upload["upload_id"]
    file_id = upload["file_id"]
    file_status = client.request("GET", "/v1/files/%s" % file_id, agent_id)
    if not file_status or file_status.get("status") != "available":
        client.request(
            "PUT",
            "/v1/files/uploads/%s/content" % upload_id,
            agent_id,
            body=blob,
            content_type="application/gzip",
        )
        completed = client.request(
            "POST", "/v1/files/uploads/%s/complete" % upload_id, agent_id
        )
        if not completed or completed.get("status") != "available":
            raise HubError("uploaded file did not become available")
    return file_id


def backfill_full(
    client: HubClient,
    session: SessionFile,
    agent_id: str,
    project_id: str,
    sid: Optional[str] = None,
) -> UploadResult:
    """为存量 session 补传完整 session 文件：
    full（命名对象覆盖写）+ 等价快照新版本（full_file_id 关联），不重写 memory。
    sid 缺省为 hook 三段式（source:project:uuid）；两段式旧归档由调用方传入。"""
    if sid is None:
        sid = normalize_identifier(
            "%s:%s:%s" % (session.source, project_id, session.source_session_id),
            "%s-session" % session.source,
        )
    existing = client.request("GET", "/v1/sessions/%s" % sid, agent_id, allow_404=True)
    if not existing:
        return UploadResult(
            status="skipped", session_id=sid, detail="no existing session (never captured)"
        )
    if existing.get("status") == "deleted":
        return UploadResult(status="skipped", session_id=sid, detail="session is deleted")

    full_object_name = "%s/%s" % (session.source, session.path.name)
    full_blob = build_full_package_bytes(session, sid)
    full_sha = hashlib.sha256(full_blob).hexdigest()
    snapshot_blob = build_backfill_snapshot_bytes(session, sid, full_object_name, full_sha)
    snapshot_sha = hashlib.sha256(snapshot_blob).hexdigest()

    latest_version = int(existing["latest_version"])
    latest = client.request(
        "GET", "/v1/sessions/%s/versions/%s" % (sid, latest_version), agent_id
    )
    if latest and latest.get("full_file_id") and latest.get("content_sha256") == snapshot_sha:
        return UploadResult(
            status="skipped", session_id=sid, detail="already has up-to-date full file",
            version=latest_version,
        )

    full_file_id = _upload_blob(
        client,
        agent_id,
        idem_key("backfill-full", sid, full_sha),
        full_blob,
        object_name=full_object_name,
    )
    snapshot_file_id = _upload_blob(
        client, agent_id, idem_key("backfill-snapshot", sid, snapshot_sha), snapshot_blob
    )
    version_response = client.request(
        "PUT",
        "/v1/sessions/%s/versions" % sid,
        agent_id,
        idempotency_key=idem_key("backfill-commit", sid, snapshot_sha),
        json_body={
            "schema_version": "session-version/1",
            "agent_id": agent_id,
            "project_id": project_id,
            "file_id": snapshot_file_id,
            "full_file_id": full_file_id,
            "base_version": latest_version,
            "update_mode": "append",
            "session_schema": "%s-session" % session.source,
            "session_schema_version": "3",
        },
    )
    version = int(version_response["version"])
    return UploadResult(status="uploaded", session_id=sid, version=version)


def upload_session_dual(
    client: HubClient, session: SessionFile, agent_id: str, project_id: str, sid: str
) -> UploadResult:
    """双资产全量上传（--hook-namespace）：完整文件（命名对象覆盖写）+ 快照（/3
    CAS，内嵌 full_session 指针），commit 关联 full_file_id，写入 memory。
    与 hook capture 产物同构（同 session_id 轨道、同 schema）。"""
    full_object_name = "%s/%s" % (session.source, session.path.name)
    full_blob = build_full_package_bytes(session, sid)
    full_sha = hashlib.sha256(full_blob).hexdigest()
    snapshot_blob = build_backfill_snapshot_bytes(session, sid, full_object_name, full_sha)
    snapshot_sha = hashlib.sha256(snapshot_blob).hexdigest()

    existing = client.request("GET", "/v1/sessions/%s" % sid, agent_id, allow_404=True)
    if existing:
        latest_version = int(existing["latest_version"])
        latest = client.request(
            "GET", "/v1/sessions/%s/versions/%s" % (sid, latest_version), agent_id
        )
        if latest and latest.get("content_sha256") == snapshot_sha:
            memory_id = ensure_memory(client, session, agent_id, latest_version, latest["file_id"])
            return UploadResult(
                status="skipped",
                session_id=sid,
                detail="content unchanged",
                version=latest_version,
                memory_id=memory_id,
            )

    full_file_id = _upload_blob(
        client,
        agent_id,
        idem_key("dual-full", sid, full_sha),
        full_blob,
        object_name=full_object_name,
    )
    snapshot_file_id = _upload_blob(
        client, agent_id, idem_key("dual-snapshot", sid, snapshot_sha), snapshot_blob
    )
    base_version = int(existing["latest_version"]) if existing else None
    version_response = client.request(
        "PUT",
        "/v1/sessions/%s/versions" % sid,
        agent_id,
        idempotency_key=idem_key("dual-commit", sid, snapshot_sha),
        json_body={
            "schema_version": "session-version/1",
            "agent_id": agent_id,
            "project_id": project_id,
            "file_id": snapshot_file_id,
            "full_file_id": full_file_id,
            "base_version": base_version,
            "update_mode": "append" if existing else "replace",
            "session_schema": "%s-session" % session.source,
            "session_schema_version": "3",
        },
    )
    version = int(version_response["version"])
    memory_id = ensure_memory(client, session, agent_id, version, snapshot_file_id)
    return UploadResult(
        status="uploaded", session_id=sid, version=version, memory_id=memory_id
    )


def fetch_session_inventory(
    dashboard_url: str, api_key: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """从 dashboard（直读 hub SQLite 的只读 BFF）拉全量 session 清单：
    session_id -> {project_id, agent_id, status}。backfill 用它匹配两段式/三段式
    存量并取得真实归属 project/agent（避免探测式 404/403）。新版 dashboard
    启用鉴权（DASHBOARD_API_KEY/MEMORY_HUB_API_KEY 同一套），必须带 Bearer。"""
    inventory: Dict[str, Dict[str, Any]] = {}
    offset = 0
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    headers = {}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    while True:
        request = urllib.request.Request(
            "%s/api/v1/sessions?limit=500&offset=%d" % (dashboard_url.rstrip("/"), offset),
            headers=headers,
        )
        with opener.open(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("sessions", [])
        for row in rows:
            inventory[row["session_id"]] = {
                "project_id": row.get("project_id") or "",
                "agent_id": row.get("agent_id") or "",
                "status": row.get("status") or "",
            }
        offset += len(rows)
        if not rows or offset >= int(payload.get("total", 0)):
            break
    return inventory


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
        "--existing-map",
        default=os.environ.get("MEMORY_HUB_EXISTING_MAP"),
        help="JSON file mapping session_id -> hub project for sessions already on the hub "
        "(session ownership is fixed at first commit; reuse their original project)",
    )
    parser.add_argument(
        "--project-alias",
        action="append",
        default=None,
        metavar="FROM=TO",
        help="Map a derived (lowercased) project name to another; repeatable. "
        "Env MEMORY_HUB_PROJECT_ALIASES accepts comma-separated pairs. "
        "Built-in default: sununity=unity2018",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Never touch sessions already on the hub (per --existing-map): no new "
        "version, no new memory; they are reported as skipped",
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
    parser.add_argument(
        "--backfill-full",
        action="store_true",
        help="Backfill mode (ADR-009): for sessions ALREADY on the hub, upload the "
        "full session file (named object, overwrite) + an equivalent snapshot "
        "version carrying the full_session pointer. Matches both hook three-part "
        "ids (source:project:uuid) and legacy two-part archive ids (source:uuid) "
        "via the dashboard session inventory. Pure local build: no LLM title, no "
        "memory rewrite. Sessions not on the hub are skipped.",
    )
    parser.add_argument(
        "--hook-namespace",
        action="store_true",
        help="Upload with the hook's three-part session id (source:project:uuid) "
        "and dual-asset packages (snapshot /3 + full file, ADR-009): same track as "
        "hook captures, so a later resume+end appends versions instead of creating "
        "a parallel two-part record.",
    )
    parser.add_argument(
        "--dashboard-url",
        default=os.environ.get("MEMORY_HUB_DASHBOARD_URL"),
        help="Dashboard BFF base URL for the session inventory (default: hub URL "
        "with port 9288, e.g. http://nas:9288)",
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
    title_cache_file = title_cache_path()
    title_cache = load_title_cache(title_cache_file)
    use_llm = title_llm_enabled() and not args.dry_run
    # backfill：从 dashboard 拉全量 session 清单（只读），用于两段式/三段式匹配
    # 与真实归属 project 解析（避免探测式 404/403）。dry-run 也拉（纯只读 GET）。
    inventory: Dict[str, Dict[str, Any]] = {}
    if args.backfill_full:
        dashboard_url = args.dashboard_url or re.sub(
            r":9287(/|$)", r":9288\1", args.hub_url
        )
        try:
            inventory = fetch_session_inventory(dashboard_url, args.api_key)
            print("inventory: %d sessions on hub (from %s)" % (len(inventory), dashboard_url))
        except Exception as error:
            print("error: cannot fetch session inventory: %s" % error, file=sys.stderr)
            return 2
    existing_map: Dict[str, str] = {}
    if args.existing_map:
        try:
            raw_map = json.loads(Path(args.existing_map).read_text(encoding="utf-8"))
            for key, value in raw_map.items():
                if isinstance(value, str) and value:
                    existing_map[key] = value
                elif isinstance(value, dict) and value.get("project"):
                    existing_map[key] = str(value["project"])
        except (OSError, json.JSONDecodeError) as error:
            print("error: cannot load existing map %s: %s" % (args.existing_map, error), file=sys.stderr)
            return 2
    project_aliases = load_project_aliases(args.project_alias)

    for index, path in enumerate(files, 1):
        session = scan_session_file(path, forced_source)
        if session is None:
            failures += 1
            continue
        if args.skip_existing and session.archive_session_id in existing_map:
            result = UploadResult(
                status="skipped",
                session_id=session.archive_session_id,
                detail="already on hub (%s)" % existing_map[session.archive_session_id],
            )
            results.append(result)
            print(
                "[%d/%d] skipped | %s | 「已在库」 | %s | %s"
                % (index, total, result.session_id, path.name, result.detail)
            )
            continue
        agent_id = args.agent_id or SOURCE_AGENT_DEFAULTS.get(session.source, session.source)
        # 按工作根目录名分类归档（小写归一，避免 MainDev/maindev 分裂），与 hook 一致；
        # 已在 hub 存在的 session 归属在首版固定，沿用其原 project。
        mapped_project = existing_map.get(session.archive_session_id)
        if args.project_id:
            project_id = args.project_id
        elif mapped_project:
            project_id = mapped_project
        else:
            derived = normalize_identifier(
                Path(session.cwd).name if session.cwd else "", "agent-history"
            ).lower()
            project_id = project_aliases.get(derived, project_aliases.get("*", derived))

        if args.backfill_full:
            # 补传模式：纯本地构建，不走 LLM title / finalize / memory 重写。
            # 双候选匹配：hook 三段式（source:project:uuid）优先，其次两段式旧归档
            # （source:uuid）；project 归属以 inventory 记录为准。
            sid3 = normalize_identifier(
                "%s:%s:%s" % (session.source, project_id, session.source_session_id),
                "%s-session" % session.source,
            )
            sid2 = session.archive_session_id
            if sid3 in inventory:
                target_sid = sid3
                target_project = inventory[sid3]["project_id"] or project_id
            elif sid2 in inventory:
                target_sid = sid2
                target_project = inventory[sid2]["project_id"] or project_id
            else:
                if args.dry_run or args.verbose:
                    print(
                        "[%s%d/%d] skip | %s | not on hub (neither %s nor %s)"
                        % ("dry-run " if args.dry_run else "", index, total, path.name, sid3, sid2)
                    )
                continue
            # 归属跟随存量记录（scope 校验要求与首版创建时的 agent/project 一致）
            target_agent = inventory[target_sid]["agent_id"] or agent_id
            if inventory[target_sid]["status"] == "deleted":
                if args.verbose or args.dry_run:
                    print(
                        "[%s%d/%d] skip | %s | session deleted"
                        % ("dry-run " if args.dry_run else "", index, total, path.name)
                    )
                continue
            if args.dry_run:
                print(
                    "[dry-run %d/%d] backfill-full | %s | project=%s session=%s events=%d"
                    % (index, total, path.name, target_project, target_sid, session.event_count)
                )
                continue
            assert client is not None
            upload_client = client
            if target_project != client.config.project_id:
                if target_project not in per_project_clients:
                    per_project_clients[target_project] = HubClient(
                        HubConfig(
                            hub_url=client.config.hub_url,
                            user_id=client.config.user_id,
                            project_id=target_project,
                            api_key=client.config.api_key,
                            timeout_seconds=client.config.timeout_seconds,
                        )
                    )
                upload_client = per_project_clients[target_project]
            try:
                result = backfill_full(upload_client, session, target_agent, target_project, sid=target_sid)
            except HubError as error:
                failures += 1
                result = UploadResult(status="failed", session_id=target_sid, detail=str(error))
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
            continue

        resolve_classification(
            session,
            title_cache,
            title_cache_file,
            use_llm,
            persist=not args.dry_run,
        )
        if not session.meaningful:
            result = UploadResult(
                status="skipped",
                session_id=session.archive_session_id,
                detail="low-value session, not uploaded",
            )
            results.append(result)
            if not args.dry_run:
                print(
                    "[%d/%d] skipped | %s | 「低价值」 | %s | %s"
                    % (index, total, result.session_id, path.name, result.detail)
                )
                continue
        if not args.dry_run:
            finalize_payload(session)
        # agent_id / project_id 已在上方统一计算（backfill 分支共用）
        if args.hook_namespace:
            # 三段式 session_id（与 hook capture 同轨）：resume 后 hook 追加版本，
            # 不产生两段式平行记录
            session.archive_session_id = normalize_identifier(
                "%s:%s:%s" % (session.source, project_id, session.source_session_id),
                "%s-session" % session.source,
            )

        if args.dry_run or client is None:
            print(
                "[dry-run %d/%d] %s | source=%s agent=%s project=%s session=%s size=%d title=%s"
                % (
                    index,
                    total,
                    path.name,
                    session.source,
                    agent_id,
                    project_id,
                    session.archive_session_id,
                    session.size_bytes,
                    session.title,
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
            if args.hook_namespace:
                result = upload_session_dual(
                    upload_client, session, agent_id, project_id, session.archive_session_id
                )
            else:
                result = upload_session(upload_client, session, agent_id)
        except HubError as error:
            failures += 1
            result = UploadResult(
                status="failed", session_id=session.archive_session_id, detail=str(error)
            )
        results.append(result)
        if args.verbose or result.status == "failed" or index % 50 == 0 or index == total:
            print(
                "[%d/%d] %s | %s | 「%s」 | %s %s"
                % (
                    index,
                    total,
                    result.status,
                    result.session_id,
                    session.title,
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

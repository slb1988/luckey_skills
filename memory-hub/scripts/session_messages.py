"""Shared transcript message extraction for Memory Hub hook utilities.

The Codex Desktop rollout format has changed more than once and can persist
the same visible message through multiple event families.  Transcript-level
selection is therefore as important as record-level parsing: choosing one
canonical Codex family prevents duplicate messages and excludes the injected
developer/context records carried by ``response_item``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


TEXT_BLOCK_TYPES = {"text", "input_text", "output_text"}
INJECTED_USER_PREFIXES = (
    "<recommended_plugins>",
    "<environment_context>",
    "<app-context>",
    "<skills_instructions>",
    "<permissions instructions>",
    "<user_action>",
    "<turn_aborted>",
    "<user_instructions>",
    "<skill>",
    "<collaboration_mode>",
    "# agents.md instructions",
    "the following is the codex agent history",
    "warning: apply_patch was requested via exec_command.",
)
SYNTHETIC_ASSISTANT_PREFIXES = (
    "**handoff summary**",
    "## current request",
    "# current request",
)
ATTACHMENT_WRAPPER_RE = re.compile(r"<image(?:\s[^>]*)?>.*?</image>", re.IGNORECASE | re.DOTALL)


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if any(isinstance(item, dict) and isinstance(item.get("type"), str) for item in value):
            return " ".join(
                part for part in (flatten_block(item) for item in value) if part
            )
        return " ".join(part for part in (flatten_text(item) for item in value) if part)
    if not isinstance(value, dict):
        return ""
    for key in ("text", "message", "content"):
        if key in value:
            text = flatten_text(value[key])
            if text:
                return text
    return ""


def flatten_block(item: Any) -> str:
    if isinstance(item, dict) and isinstance(item.get("type"), str):
        if item["type"].lower() not in TEXT_BLOCK_TYPES:
            return ""
    return flatten_text(item)


def _item_completed_role_text(record: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    if record.get("type") != "event_msg":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "item_completed":
        return None
    item = payload.get("item")
    if not isinstance(item, dict):
        return None
    item_type = str(item.get("type") or "").lower()
    role = "user" if item_type == "usermessage" else "assistant" if item_type == "agentmessage" else ""
    if not role:
        return None
    # Codex Desktop persists progress updates as AgentMessage items too.  They
    # are visible in the UI, but they are not the completed turn result that a
    # session summary should archive.  Older item_completed records did not
    # carry ``phase``, so keep those as a compatibility fallback.
    phase = str(item.get("phase") or "").lower()
    if role == "assistant" and phase and phase != "final_answer":
        return None
    text = flatten_text(item.get("content") or item.get("message"))
    return (role, text) if text else None


def _legacy_codex_role_text(record: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    if record.get("type") != "event_msg":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None
    payload_type = payload.get("type")
    if payload_type == "user_message":
        text = flatten_text(payload.get("message") or payload.get("content"))
        return ("user", text) if text else None
    if payload_type in ("agent_message", "assistant_message"):
        phase = str(payload.get("phase") or "").lower()
        if phase and phase != "final_answer":
            return None
        text = flatten_text(payload.get("message") or payload.get("content"))
        return ("assistant", text) if text else None
    return None


def _response_item_role_text(record: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    if record.get("type") != "response_item":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return None
    role = payload.get("role")
    if role not in ("user", "assistant"):
        return None
    phase = str(payload.get("phase") or "").lower()
    if role == "assistant" and phase and phase != "final_answer":
        return None
    content = payload.get("content")
    if role == "user" and isinstance(content, list):
        content = [
            block
            for block in content
            if not flatten_block(block).lstrip().lower().startswith(INJECTED_USER_PREFIXES)
        ]
    text = flatten_text(content)
    lowered = text.lstrip().lower()
    if role == "user" and lowered.startswith(INJECTED_USER_PREFIXES):
        return None
    if role == "assistant" and lowered.startswith(SYNTHETIC_ASSISTANT_PREFIXES):
        return None
    return (role, text) if text else None


def _mirror_key(pair: Tuple[str, str]) -> Tuple[str, str]:
    """Normalize response-only attachment markup before mirror comparison."""
    role, value = pair
    without_attachments = ATTACHMENT_WRAPPER_RE.sub(" ", value)
    return role, " ".join(without_attachments.split())


def extract_role_text(record: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Extract one user/assistant record from Claude, Pi, or Codex JSONL."""
    item_completed = _item_completed_role_text(record)
    if item_completed:
        return item_completed

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

    legacy_codex = _legacy_codex_role_text(record)
    if legacy_codex:
        return legacy_codex

    # ``response_item`` user messages can contain only injected app/context
    # blocks.  Return the filtered result directly so the generic payload
    # fallback below cannot re-introduce those blocks.
    if record.get("type") == "response_item":
        return _response_item_role_text(record)

    payload = record.get("payload")
    if isinstance(payload, dict):
        role = payload.get("role")
        if payload.get("type") == "message" and role in ("user", "assistant"):
            text = flatten_text(payload.get("content"))
            return (role, text) if text else None
        if role in ("user", "assistant"):
            text = flatten_text(payload.get("content"))
            return (role, text) if text else None
    return None


def extract_session_pairs(
    events: Iterable[Dict[str, Any]], source: Optional[str] = None
) -> List[Tuple[str, str]]:
    """Extract one canonical visible-message stream from a transcript.

    Codex rollout files duplicate assistant messages between ``item_completed``
    and ``response_item``.  Older files similarly pair legacy ``event_msg``
    messages with response items.  Prefer the richest visible-message family
    for Codex and only fall back when that family is absent.
    """
    records = list(events)
    if source == "codex":
        families = [
            [
                (index, pair)
                for index, record in enumerate(records)
                if (pair := extractor(record))
            ]
            for extractor in (
                _item_completed_role_text,
                _legacy_codex_role_text,
                _response_item_role_text,
            )
        ]
        # The canonical format can change inside one resumed rollout. Keep
        # both canonical families in event order, then match response mirrors
        # to the nearest canonical event. A global text counter is unsafe when
        # separate turns repeat a short prompt such as "continue".
        canonical = sorted([*families[0], *families[1]], key=lambda entry: entry[0])
        if canonical:
            response = families[2]
            mirrored: set[int] = set()
            for canonical_index, canonical_pair in canonical:
                canonical_key = _mirror_key(canonical_pair)
                candidates = [
                    (abs(response_index - canonical_index), position)
                    for position, (response_index, response_pair) in enumerate(response)
                    if position not in mirrored
                    and _mirror_key(response_pair) == canonical_key
                    and abs(response_index - canonical_index) <= 8
                ]
                if candidates:
                    mirrored.add(min(candidates)[1])
            merged = [
                *canonical,
                *(entry for position, entry in enumerate(response) if position not in mirrored),
            ]
            return [pair for _, pair in sorted(merged, key=lambda entry: entry[0])]
        if families[2]:
            return [pair for _, pair in families[2]]
    return [pair for record in records if (pair := extract_role_text(record))]

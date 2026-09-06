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


# ---------------------------------------------------------------------------
# chat-hub 微信信封处理
# ---------------------------------------------------------------------------
#
# chat-hub（.pi/extensions/chat-hub）投递的用户消息带三层包装：
#   [weixin dm from <chatId>]                                   ← 传输行
#   [chat-hub 可信逻辑说话人] profile_id/display_name/... [/…]   ← 身份封套（新版）
#   [入站微信语音 1: ... 微信侧自动转写（…）："真实文本"]          ← 媒体信封
# 不剥离时归档摘要的 700/700/1400 字符预算全被信封占满，真实内容（语音转写、
# 答题文本）完全丢失（2026-09-06 小樱桃数学测评会话事故）。语音转写是正文的
# 最佳代理，予以保留；无转写（微信未提供/失败）的语音消息剥离后为空，交由
# 调用方的噪声过滤处理。

CHAT_HUB_TRANSPORT_RE = re.compile(r"^\[[a-z]+\s+(?:dm|group)\s+from\s+[^\]\n]+\]")
CHAT_HUB_IDENTITY_BLOCK_RE = re.compile(
    r"\[chat-hub 可信逻辑说话人\](?P<block>.*?)\[/chat-hub 可信逻辑说话人\]",
    re.DOTALL,
)
CHAT_HUB_PROFILE_ID_RE = re.compile(r'profile_id:\s*"([^"]+)"')
CHAT_HUB_DISPLAY_NAME_RE = re.compile(r'display_name:\s*"([^"]+)"')
CHAT_HUB_MEDIA_LINE_RE = re.compile(r"^\[入站微信[^\]\n]*\]$")
CHAT_HUB_VOICE_TRANSCRIPT_RE = re.compile(r'不准确）："(?P<text>[^"\n]*)"\s*\]?\s*$')


def strip_chat_hub_envelope(text: str) -> Tuple[str, Optional[Dict[str, str]]]:
    """剥掉 chat-hub 微信信封，返回 (clean_text, speaker|None)。

    speaker 从身份封套解析（profile_id/display_name）；旧版无封套消息为 None。
    非 chat-hub 消息原样返回且 speaker 为 None（零影响普通会话）。
    """
    if not text:
        return text, None
    speaker: Optional[Dict[str, str]] = None
    match = CHAT_HUB_IDENTITY_BLOCK_RE.search(text)
    if match:
        block = match.group("block")
        speaker = {}
        profile = CHAT_HUB_PROFILE_ID_RE.search(block)
        display = CHAT_HUB_DISPLAY_NAME_RE.search(block)
        if profile:
            speaker["profile_id"] = profile.group(1)
        if display:
            speaker["display_name"] = display.group(1)
        text = CHAT_HUB_IDENTITY_BLOCK_RE.sub("\n", text)
    stripped = text.lstrip()
    transport = CHAT_HUB_TRANSPORT_RE.match(stripped)
    if not transport:
        if speaker is not None:
            return text.strip(), speaker
        return text, None
    text = stripped[transport.end():]
    kept: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if CHAT_HUB_MEDIA_LINE_RE.match(line):
            voice = CHAT_HUB_VOICE_TRANSCRIPT_RE.search(line)
            if voice:
                transcript = voice.group("text").strip()
                if transcript:
                    kept.append(transcript)
            continue
        kept.append(line)
    return "\n".join(kept).strip(), speaker


def chat_hub_speakers_from_pairs(
    pairs: Iterable[Tuple[str, str]]
) -> List[Dict[str, Any]]:
    """统计 chat-hub 会话的说话人（按用户消息数降序）；非 chat-hub 会话返回 []。

    排序首位即「对话主体」（消息数最多的说话人），用于归档标记记录。
    """
    order: List[str] = []
    stats: Dict[str, Dict[str, Any]] = {}
    for role, raw_text in pairs:
        if role != "user":
            continue
        _clean, speaker = strip_chat_hub_envelope(raw_text)
        if not speaker:
            continue
        key = speaker.get("profile_id") or speaker.get("display_name") or "unknown"
        entry = stats.get(key)
        if entry is None:
            entry = {
                "profile_id": speaker.get("profile_id") or "",
                "display_name": speaker.get("display_name") or "",
                "messages": 0,
            }
            stats[key] = entry
            order.append(key)
        entry["messages"] += 1
    speakers = [stats[key] for key in order]
    speakers.sort(key=lambda item: (-item["messages"], item["profile_id"]))
    return speakers


def chat_hub_speaker_names(speakers: List[Dict[str, Any]]) -> List[str]:
    return [
        name
        for name in (s.get("display_name") or s.get("profile_id") for s in speakers)
        if name
    ]


def chat_hub_speaker_note(speakers: List[Dict[str, Any]]) -> str:
    """会话主体标记文本（写入 distilled 开头）。主体 = 消息数最多的说话人。"""
    names = chat_hub_speaker_names(speakers)
    if not names:
        return ""
    if len(names) == 1:
        return "对话主体：%s（chat-hub 微信会话）。" % names[0]
    return "对话主体：%s（chat-hub 微信会话，参与者：%s）。" % (names[0], "、".join(names))


def chat_hub_speaker_title_prefix(speakers: List[Dict[str, Any]]) -> str:
    """标题前缀：单人「[小樱桃] 」，多人「[孙来兵+小樱桃] 」（多数派在前）。"""
    names = chat_hub_speaker_names(speakers)
    if not names:
        return ""
    if len(names) == 1:
        return "[%s] " % names[0]
    return "[%s] " % ("+".join(names))


_CHAT_HUB_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")


def chat_hub_project_for_speakers(
    speakers: List[Dict[str, Any]], owner_user_id: str
) -> Optional[str]:
    """chat-hub 会话的 project 路由：单一非机主说话人 → 其 profile_id 作为 project。

    机主本人、多人混合、无身份封套（legacy 会话）都返回 None（维持 cwd 派生），
    避免把可能含机主上下文的混合会话误归到他人 scope（机主私密记忆不外流）。
    返回的 project 与 profile_id 一致（如 xiaoyingtao），非法字符一律拒判。
    """
    owner = (owner_user_id or "").strip().lower()
    if not owner or len(speakers) != 1:
        return None
    profile_id = (speakers[0].get("profile_id") or "").strip().lower()
    if not profile_id or profile_id == owner:
        return None
    if not _CHAT_HUB_PROJECT_ID_RE.match(profile_id):
        return None
    return profile_id

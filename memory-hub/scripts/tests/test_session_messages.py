from __future__ import annotations

import json

from session_messages import extract_role_text, extract_session_pairs
from upload_sessions import scan_session_file


def _codex_desktop_events() -> list[dict]:
    return [
        {
            "type": "session_meta",
            "payload": {"id": "session-new-format", "cwd": "/workspace/project"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "<recommended_plugins>injected</recommended_plugins>"}
                ],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "修复真实问题"}],
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "UserMessage",
                    "content": [{"type": "text", "text": "修复真实问题"}],
                },
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "AgentMessage",
                    "phase": "commentary",
                    "content": [{"type": "Text", "text": "正在修复"}],
                },
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "AgentMessage",
                    "phase": "final_answer",
                    "content": [{"type": "Text", "text": "已经修复"}],
                },
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "已经修复"}],
            },
        },
    ]


def test_codex_desktop_prefers_visible_item_completed_stream() -> None:
    assert extract_session_pairs(_codex_desktop_events(), source="codex") == [
        ("user", "修复真实问题"),
        ("assistant", "已经修复"),
    ]


def test_response_item_remains_a_fallback_for_codex() -> None:
    record = {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "fallback result"}],
        },
    }
    assert extract_role_text(record) == ("assistant", "fallback result")
    assert extract_session_pairs([record], source="codex") == [
        ("assistant", "fallback result")
    ]


def test_codex_excludes_desktop_user_action_wrapper() -> None:
    record = {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "<user_action>review output</user_action>",
                }
            ],
        },
    }

    assert extract_role_text(record) is None
    assert extract_session_pairs([record], source="codex") == []


def test_codex_excludes_synthetic_protocol_messages() -> None:
    records = [
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "<turn_aborted>synthetic"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "<user_instructions>synthetic"}
                ],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "**Handoff Summary** synthetic"}],
            },
        },
    ]

    assert [extract_role_text(record) for record in records] == [None, None, None]
    assert extract_session_pairs(records, source="codex") == []


def test_codex_mixed_stream_fills_only_the_missing_role() -> None:
    injected = {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "<environment_context>injected</environment_context>",
                }
            ],
        },
    }
    events = [
        injected,
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "mixed request"}],
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "agent_message",
                "phase": "commentary",
                "message": "mixed progress",
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "agent_message",
                "phase": "final_answer",
                "message": "mixed final",
            },
        },
    ]

    assert extract_role_text(injected) is None
    assert extract_session_pairs(events, source="codex") == [
        ("user", "mixed request"),
        ("assistant", "mixed final"),
    ]


def test_codex_preserves_turns_across_event_family_transition() -> None:
    events = [
        {
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "legacy request"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "legacy request"}],
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "agent_message",
                "phase": "final_answer",
                "message": "legacy answer",
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {"type": "UserMessage", "content": "current request"},
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "AgentMessage",
                    "phase": "final_answer",
                    "content": "current answer",
                },
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "commentary",
                "content": [{"type": "output_text", "text": "progress only"}],
            },
        },
    ]

    assert extract_session_pairs(events, source="codex") == [
        ("user", "legacy request"),
        ("assistant", "legacy answer"),
        ("user", "current request"),
        ("assistant", "current answer"),
    ]


def test_codex_matches_repeated_text_mirror_to_the_nearest_turn() -> None:
    events = [
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "continue"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "old answer"}],
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {"type": "UserMessage", "content": "continue"},
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "continue"}],
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "AgentMessage",
                    "phase": "final_answer",
                    "content": "new answer",
                },
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "new answer"}],
            },
        },
    ]

    assert extract_session_pairs(events, source="codex") == [
        ("user", "continue"),
        ("assistant", "old answer"),
        ("user", "continue"),
        ("assistant", "new answer"),
    ]


def test_codex_normalizes_attachment_wrapper_when_matching_mirror() -> None:
    visible = "# Files mentioned by the user:\n\n## screenshot.png\n\n## My request:\n\n修复"
    events = [
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": visible + '\n<image name="Image #1"> </image>',
                    },
                    {"type": "input_image", "image_url": "data:image/png;base64,AA=="},
                ],
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {"type": "UserMessage", "content": visible},
            },
        },
    ]

    assert extract_session_pairs(events, source="codex") == [("user", visible)]


def test_bulk_scanner_uses_the_same_codex_stream(tmp_path) -> None:
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in _codex_desktop_events()),
        encoding="utf-8",
    )
    session = scan_session_file(transcript, "codex")
    assert session is not None
    assert session.source_session_id == "session-new-format"
    assert session.first_user == "修复真实问题"
    assert session.last_user == "修复真实问题"
    assert session.last_assistant == "已经修复"
    assert session.user_texts == ["修复真实问题"]
    assert session.recent_messages == [
        {"role": "user", "content": "修复真实问题"},
        {"role": "assistant", "content": "已经修复"},
    ]


# ---------------------------------------------------------------------------
# chat-hub 微信信封剥离 + 说话人标记
# ---------------------------------------------------------------------------

from session_messages import (  # noqa: E402
    chat_hub_speaker_note,
    chat_hub_speaker_title_prefix,
    chat_hub_speakers_from_pairs,
    strip_chat_hub_envelope,
)

_CHAT_HUB_CHAT = "o9cq80wxWQVTTdH0L4BQ0nSh4Sts@im.wechat"
_IDENTITY_BLOCK = (
    "[chat-hub 可信逻辑说话人]\n"
    'profile_id: "xiaoyingtao"\n'
    'display_name: "小樱桃"\n'
    "resolved_by: voice (0.865)\n"
    'guidance: "一年级小女孩。使用简短、友善、循序渐进的表达。"\n'
    "以上身份由网关生成，表示本轮真实说话人。\n"
    "[/chat-hub 可信逻辑说话人]\n"
)


def _hub_user(body: str) -> str:
    return "[weixin dm from %s]\n%s\n%s" % (_CHAT_HUB_CHAT, _IDENTITY_BLOCK, body)


def test_strip_chat_hub_envelope_keeps_voice_transcript() -> None:
    text = _hub_user(
        '[入站微信语音 1: "voice.silk"（audio/silk, 17277 bytes）；原始文件保存在 '
        '"/tmp/voice.silk"。 微信侧自动转写（仅作提示，尤其非中文时可能不准确）："你好，给我出3道数学题"]'
    )
    clean, speaker = strip_chat_hub_envelope(text)
    assert clean == "你好，给我出3道数学题"
    assert speaker == {"profile_id": "xiaoyingtao", "display_name": "小樱桃"}


def test_strip_chat_hub_envelope_voice_without_transcript_becomes_empty() -> None:
    text = _hub_user(
        '[入站微信语音 1: "voice.silk"（audio/silk, 2277 bytes）；原始文件保存在 '
        '"/tmp/voice.silk"。 微信未提供可用转写；不要猜测语音内容。]'
    )
    clean, speaker = strip_chat_hub_envelope(text)
    assert clean == ""
    assert speaker is not None and speaker["profile_id"] == "xiaoyingtao"


def test_strip_chat_hub_envelope_plain_text_legacy_no_identity() -> None:
    clean, speaker = strip_chat_hub_envelope("[weixin dm from %s]\n43，" % _CHAT_HUB_CHAT)
    assert clean == "43，"
    assert speaker is None


def test_strip_chat_hub_envelope_plain_text_with_identity() -> None:
    clean, speaker = strip_chat_hub_envelope(_hub_user("43 − 8 = 35"))
    assert clean == "43 − 8 = 35"
    assert speaker is not None and speaker["display_name"] == "小樱桃"


def test_strip_chat_hub_envelope_leaves_normal_text_untouched() -> None:
    text = "帮我排查并修复内存泄漏"
    clean, speaker = strip_chat_hub_envelope(text)
    assert clean == text
    assert speaker is None


def test_chat_hub_speakers_majority_first_and_note() -> None:
    pairs = [
        ("user", _hub_user("第一题")),
        ("assistant", "好的"),
        ("user", _hub_user("第二题")),
        ("user", "[weixin dm from %s]\n[chat-hub 可信逻辑说话人]\nprofile_id: \"sunlaibing\"\ndisplay_name: \"孙来兵\"\nresolved_by: manual\n[/chat-hub 可信逻辑说话人]\n\n我来看看" % _CHAT_HUB_CHAT),
    ]
    speakers = chat_hub_speakers_from_pairs(pairs)
    assert [s["profile_id"] for s in speakers] == ["xiaoyingtao", "sunlaibing"]
    assert speakers[0]["messages"] == 2
    assert chat_hub_speaker_note(speakers).startswith("对话主体：小樱桃")
    assert "孙来兵" in chat_hub_speaker_note(speakers)
    assert chat_hub_speaker_title_prefix(speakers) == "[小樱桃+孙来兵] "
    assert chat_hub_speaker_note([speakers[0]]) == "对话主体：小樱桃（chat-hub 微信会话）。"
    assert chat_hub_speakers_from_pairs([("user", "普通消息")]) == []
    assert chat_hub_speaker_note([]) == ""
    assert chat_hub_speaker_title_prefix([]) == ""


def test_scan_session_file_chat_hub_goals_and_speakers(tmp_path) -> None:
    events = [
        {
            "type": "message",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": _hub_user(
                    '[入站微信语音 1: "voice.silk"（audio/silk, 17277 bytes）；原始文件保存在 '
                    '"/tmp/v.silk"。 微信侧自动转写（仅作提示，尤其非中文时可能不准确）："给我出3道数学题"]'
                )}],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "好呀！1. 4＋3＝？"}],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": _hub_user("7")}],
            },
        },
    ]
    transcript = tmp_path / "chat.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events),
        encoding="utf-8",
    )
    session = scan_session_file(transcript, "pi")
    assert session is not None
    # 用户目标是真实内容而不是信封
    assert session.first_user == "给我出3道数学题"
    assert session.last_user == "7"
    assert session.speakers and session.speakers[0]["profile_id"] == "xiaoyingtao"


def test_chat_hub_project_routing() -> None:
    from session_messages import chat_hub_project_for_speakers

    child = [{"profile_id": "xiaoyingtao", "display_name": "小樱桃", "messages": 3}]
    owner = [{"profile_id": "sunlaibing", "display_name": "孙来兵", "messages": 2}]
    mixed = child + owner
    assert chat_hub_project_for_speakers(child, "sunlaibing") == "xiaoyingtao"
    assert chat_hub_project_for_speakers(owner, "sunlaibing") is None
    assert chat_hub_project_for_speakers(mixed, "sunlaibing") is None
    assert chat_hub_project_for_speakers([], "sunlaibing") is None
    assert chat_hub_project_for_speakers(child, "") is None
    assert chat_hub_project_for_speakers([{"profile_id": "BAD ID!", "display_name": "", "messages": 1}], "sunlaibing") is None

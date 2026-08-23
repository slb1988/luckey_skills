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

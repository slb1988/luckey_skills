from __future__ import annotations

import gzip
import json
import shlex
from unittest.mock import Mock

import pytest

from memory_hook import (
    Config,
    HubClient,
    StateStore,
    UserProfile,
    build_distilled_summary,
    compact_text,
    load_session_texts,
    session_user_texts,
)
from session_messages import (
    choose_session_result,
    extract_session_pairs,
    extract_worker_done_summary,
    strip_orca_worker_envelope,
)

ENVELOPE = (
    "You are working inside Orca, a multi-agent IDE. You are a dispatched worker.\n"
    "Your coordinator's terminal handle is: term_fixture\n"
    "=== CLI COMMANDS ===\n" + "boilerplate instructions\n" * 300
)
TASK = "修复版本保护，并补回归测试。"
SUBJECT = '完成 "版本保护"'
BODY = "修复 old/new 版本冲突。\n新增 '回归' 测试，41 passed。待审核，不提交。"


def completion_command(subject=SUBJECT, body=BODY):
    return "orca orchestration send --from term_fixture --type worker_done --subject %s --body %s" % (
        shlex.quote(subject), shlex.quote(body)
    )


def pi_message(role, content):
    return {"type": "message", "message": {"role": role, "content": content}}


def tool_event(command):
    return pi_message("assistant", [{"type": "toolCall", "name": "bash", "arguments": {"command": command}}])


def custom_call_event(name, input_text):
    return {"type": "response_item",
            "payload": {"type": "custom_tool_call", "name": name, "input": input_text}}


def js_bridge(command):
    return 'const r = await tools.exec_command({cmd:%s})' % json.dumps(command)


@pytest.fixture
def pi_worker_events():
    return [
        pi_message("user", [{"type": "text", "text": ENVELOPE + "\n=== TASK ===\n" + TASK}]),
        pi_message("assistant", [{"type": "thinking", "thinking": "hidden reasoning"}]),
        tool_event("pytest tests"),
        tool_event(completion_command()),
        pi_message("assistant", [{"type": "text", "text": ""}]),
    ]


def test_pi_worker_hook_upload_uses_task_and_completion(tmp_path, pi_worker_events):
    transcript = tmp_path / "worker.jsonl"
    transcript.write_text("\n".join(json.dumps(event) for event in pi_worker_events), encoding="utf-8")
    config = Config(hub_url="http://memory.test", default_user_id="user-a", agent_id="pi",
                    archive_project_id="test-project", api_key=None, timeout_seconds=1,
                    state_dir=tmp_path / "state")
    store = StateStore(config)
    store.enqueue(UserProfile("user-a", "Test", "Fixture"), "pi", "worker", str(tmp_path), transcript)
    job = store.queued(1)[0]
    texts = load_session_texts(job)
    assert texts[1] == TASK
    assert texts[3] == SUBJECT + ": " + BODY
    client = HubClient(config)
    client.request = Mock(return_value={"memory_id": "new-memory", "status": "pending_intake"})
    client.ensure_memory(job, 1, "file-fixture", "版本保护")
    content = client.request.call_args.kwargs["json_body"]["distilled_content"]
    assert content == build_distilled_summary(TASK, TASK, SUBJECT + ": " + BODY)
    assert "boilerplate" not in content
    assert compact_text(BODY, 1400) in content


@pytest.mark.parametrize("prefix", [ENVELOPE, ENVELOPE.replace("You are", "  You \n are").replace("dispatched worker", "dispatched\tworker")])
def test_envelope_sections_and_whitespace(prefix):
    text = prefix + "\n=== TASK ===\n" + TASK + "\n=== EXTRA ===\nnot a task"
    assert strip_orca_worker_envelope(text) == TASK
    assert strip_orca_worker_envelope(prefix) == ""


def test_bare_template_does_not_occupy_first_user():
    assert session_user_texts([("user", ENVELOPE)])[1:3] == ("", "")
    assert session_user_texts([("user", ENVELOPE), ("user", TASK)])[1] == TASK
    assert strip_orca_worker_envelope("Please discuss dispatched worker tools") == "Please discuss dispatched worker tools"
    assert strip_orca_worker_envelope("=== TASK ===\nordinary message") == "=== TASK ===\nordinary message"


def test_worker_done_last_matching_call_wins(pi_worker_events):
    events = [tool_event(completion_command("earlier", "old result")), *pi_worker_events,
              tool_event("orca orchestration send --type heartbeat --body ignored")]
    assert extract_worker_done_summary(events) == SUBJECT + ": " + BODY
    assert extract_worker_done_summary([tool_event('echo "' + completion_command("fake", "not executed") + '"')]) == ""
    assert extract_worker_done_summary([tool_event("orca orchestration send --type worker_done --body 'broken")]) == ""


def test_worker_done_shell_options_and_multiple_commands():
    command = "printf ready\n" + completion_command("one", "first") + "; " + completion_command("two", "second")
    assert extract_worker_done_summary([tool_event(command)]) == "two: second"
    assert extract_worker_done_summary([tool_event("orca orchestration send --type=worker_done --subject=done --body='line one\nline two'")]) == "done: line one\nline two"


@pytest.mark.parametrize("name,arguments", [
    ("exec_command", {"cmd": completion_command()}),
    ("shell_command", {"command": completion_command()}),
    ("shell", {"command": ["bash", "-lc", completion_command()]}),
    ("functions.shell", {"command": shlex.split(completion_command())}),
])
def test_codex_function_call_format(name, arguments):
    event = {"type": "response_item", "payload": {"type": "function_call", "name": name,
                                                    "arguments": json.dumps(arguments)}}
    assert extract_worker_done_summary([event]) == SUBJECT + ": " + BODY


@pytest.mark.parametrize("name", ["exec", "exec_command", "shell", "bash"])
def test_codex_custom_tool_call_js_bridge(name):
    assert extract_worker_done_summary([custom_call_event(name, js_bridge(completion_command()))]) == SUBJECT + ": " + BODY


def test_codex_custom_tool_call_escaped_quotes_like_production():
    # 线上实证形态（session codex:maindev:01a077ef events[1159]）：JS 桥 + \" 转义
    input_text = (
        'const r = await tools.exec_command({cmd:"orca orchestration send --from term_xxx '
        '--type worker_done --subject \\"LUC-98 中文章节已完成\\" '
        '--body \\"已用 Linear 插件 MCP save_issue 将 LUC-98 回写为已完成。全文 12 节。待用户审阅。\\""})'
    )
    assert extract_worker_done_summary([custom_call_event("exec", input_text)]) == (
        "LUC-98 中文章节已完成: 已用 Linear 插件 MCP save_issue 将 LUC-98 回写为已完成。全文 12 节。待用户审阅。"
    )


def test_codex_custom_tool_call_json_quoted_cmd_key():
    # 线上变体（session codex:maindev:01a07793 等）：桥参数是 JSON 风格 {"cmd":"..."}
    input_text = (
        'const r = await tools.exec_command({"cmd":"orca orchestration send --from term_xxx '
        "--type worker_done --subject 'LUC-87 章节回写完成' "
        "--body '已把 LUC-87 升级为可独立阅读的中文技术章节，并通过 Linear MCP save_issue 回写及 get_issue 复验。'\"})"
    )
    assert extract_worker_done_summary([custom_call_event("exec", input_text)]) == (
        "LUC-87 章节回写完成: 已把 LUC-87 升级为可独立阅读的中文技术章节，并通过 Linear MCP save_issue 回写及 get_issue 复验。"
    )


def test_codex_custom_tool_call_non_shell_name_ignored():
    assert extract_worker_done_summary([custom_call_event("apply_patch", js_bridge(completion_command()))]) == ""


TEMPLATE_COMMAND = (
    'orca orchestration send --from term_fixture --dispatch-capability dcap_x '
    '--type worker_done --subject "<short status>" '
    '--body "<3-sentence summary: what you did, what you found, what\'s left>" '
    '--task-id task_x --dispatch-id ctx_x --outcome succeeded'
)


def test_worker_done_template_placeholder_body_is_dropped():
    assert extract_worker_done_summary([tool_event(TEMPLATE_COMMAND)]) == ""
    assert extract_worker_done_summary([custom_call_event("exec", js_bridge(TEMPLATE_COMMAND))]) == ""
    # 占位符在前、真实汇报在后时，真实汇报仍生效
    events = [tool_event(TEMPLATE_COMMAND), tool_event(completion_command())]
    assert extract_worker_done_summary(events) == SUBJECT + ": " + BODY


def test_choose_session_result_prefers_richer_worker_done():
    summary = SUBJECT + ": " + BODY
    assert choose_session_result("", summary) == (summary, True)
    assert choose_session_result("  ", summary) == (summary, True)
    assert choose_session_result("worker_done 已发送，任务完成。", summary) == (summary, True)
    long_final = "完整收尾报告。" * 20
    assert choose_session_result(long_final, summary) == (long_final, False)
    assert choose_session_result(long_final, "") == (long_final, False)
    assert choose_session_result("", "") == ("", False)


def test_thin_closing_text_is_replaced_by_worker_done_summary(tmp_path, pi_worker_events):
    events = [*pi_worker_events, pi_message("assistant", [{"type": "text", "text": "worker_done 已发送，任务完成。"}])]
    full = tmp_path / "full.gz"
    full.write_bytes(gzip.compress(json.dumps({"events": events}).encode()))
    texts = load_session_texts({"full_path": str(full), "snapshot_path": "", "source": "pi"})
    assert texts[3] == SUBJECT + ": " + BODY


def test_longer_assistant_text_keeps_precedence(tmp_path, pi_worker_events):
    final_text = "正常最终总结：" + "完成内容详述。" * 10
    events = [*pi_worker_events, pi_message("assistant", [{"type": "text", "text": final_text}])]
    full = tmp_path / "full.gz"
    full.write_bytes(gzip.compress(json.dumps({"events": events}).encode()))
    texts = load_session_texts({"full_path": str(full), "snapshot_path": "", "source": "pi"})
    assert texts[3] == final_text


def test_window_and_job_only_templates_are_noise(tmp_path):
    window = tmp_path / "window.gz"
    window.write_bytes(gzip.compress(json.dumps({"messages": [{"role": "user", "content": ENVELOPE}]}).encode()))
    job = {"snapshot_path": str(window), "source": "pi", "last_user": ENVELOPE, "last_assistant": ""}
    assert load_session_texts(job)[1:3] == ("", "")
    job["snapshot_path"] = ""
    assert load_session_texts(job)[1:3] == ("", "")


def test_non_worker_distilled_bytes_and_budgets_are_unchanged():
    pairs = [("user", "ordinary task"), ("assistant", "fixed"), ("user", "commit"), ("assistant", "done")]
    assert session_user_texts(pairs) == (["ordinary task", "commit"], "ordinary task", "commit", "done")
    goal, recent, result = "目标 " * 800, "近况 " * 800, "结果\n" * 1500
    expected = "首个用户目标：%s。最近用户目标：%s。会话结果：%s" % (
        compact_text(goal, 700), compact_text(recent, 700), compact_text(result, 1400)
    )
    assert build_distilled_summary(goal, recent, result).encode() == expected.encode()


def test_tool_results_and_user_commands_are_not_completion_events():
    command = completion_command()
    events = [pi_message("user", [{"type": "text", "text": command}]),
              pi_message("toolResult", [{"type": "text", "text": command}])]
    assert extract_worker_done_summary(events) == ""
    assert session_user_texts(extract_session_pairs(events, "pi"))[3] == ""

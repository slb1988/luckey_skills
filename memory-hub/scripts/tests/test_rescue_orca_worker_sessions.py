from __future__ import annotations

import gzip
import json
from unittest.mock import Mock

import pytest

import rescue_orca_worker_sessions as rescue
from memory_hook import build_distilled_summary, compact_text
from test_orca_worker_sessions import (
    BODY, ENVELOPE, SUBJECT, TASK, pi_worker_events,  # noqa: F401
)


@pytest.fixture
def memory():
    return {"memory_id": "old-1", "project_id": "original-project", "user_id": "original-user",
            "agent_id": "pi", "session_id": "pi:project:session", "session_version": 3,
            "file_id": "window-1", "scope_type": "project", "memory_type": "session_summary",
            "summary": "旧标题", "distilled_content": "旧快照" * 100}


@pytest.fixture
def review(memory):
    return {"review_id": "r-1", "memory_id": memory["memory_id"], "project_id": memory["project_id"],
            "memory_type": "session_summary", "rationale": "纯派发模板", "content_snapshot": "旧快照",
            "created_at": "2026-09-01T00:00:00Z"}


@pytest.mark.parametrize("file_format", ["events", "jsonl", "window"])
def test_session_file_formats_share_hook_distiller(file_format, memory, pi_worker_events):
    if file_format == "events":
        raw = json.dumps({"events": pi_worker_events, "source": {"agent": "pi"}}).encode()
    elif file_format == "jsonl":
        raw = "\n".join(json.dumps(event) for event in pi_worker_events).encode()
    else:
        raw = json.dumps({"messages": [{"role": "user", "content": ENVELOPE + "\n=== TASK ===\n" + TASK},
                                       {"role": "assistant", "content": SUBJECT + ": " + BODY}]}).encode()
    distilled = rescue.distill_session(rescue.decode_session(gzip.compress(raw)), memory)
    assert distilled["distilled_content"] == build_distilled_summary(TASK, TASK, SUBJECT + ": " + BODY)
    assert distilled["still_no_substantive_content"] is False
    assert distilled["used_worker_done"] is (file_format != "window")


def test_pure_template_is_flagged_empty(memory):
    distilled = rescue.distill_session({"messages": [{"role": "user", "content": ENVELOPE}]}, memory)
    assert distilled["still_no_substantive_content"] is True
    assert distilled["has_result"] is False


def test_distill_prefers_richer_worker_done_over_thin_closing(memory, pi_worker_events):
    events = [*pi_worker_events,
              {"type": "message", "message": {"role": "assistant",
                                              "content": [{"type": "text", "text": "worker_done 已发送，任务完成。"}]}}]
    raw = json.dumps({"events": events, "source": {"agent": "pi"}}).encode()
    distilled = rescue.distill_session(rescue.decode_session(gzip.compress(raw)), memory)
    assert distilled["used_worker_done"] is True
    assert compact_text(SUBJECT + ": " + BODY, 1400) in distilled["distilled_content"]


def test_distill_keeps_longer_final_text(memory, pi_worker_events):
    final_text = "完整的最终总结。" * 10
    events = [*pi_worker_events,
              {"type": "message", "message": {"role": "assistant",
                                              "content": [{"type": "text", "text": final_text}]}}]
    raw = json.dumps({"events": events, "source": {"agent": "pi"}}).encode()
    distilled = rescue.distill_session(rescue.decode_session(gzip.compress(raw)), memory)
    assert distilled["used_worker_done"] is False
    assert final_text in distilled["distilled_content"]


def test_queue_paginates_filters_and_sorts(review):
    old = dict(review, review_id="r-old", created_at="2026-08-01T00:00:00Z")
    other = dict(review, review_id="not-matching", rationale="nothing useful")
    client = Mock()
    client.get_json.side_effect = [{"items": [review, other], "total": 3}, {"items": [old], "total": 3}]
    assert rescue.rejected_reviews(client) == [old, review]
    assert client.get_json.call_args_list[0].args[0].endswith("limit=500&offset=0")
    assert client.get_json.call_args_list[1].args[0].endswith("limit=500&offset=2")


def test_prepare_records_full_403_and_falls_back(review, memory, pi_worker_events):
    client = Mock()
    client.get_json.side_effect = [memory, {"full_file_id": "full-1"}]
    window = {"messages": [{"role": "user", "content": ENVELOPE + "\n=== TASK ===\n" + TASK}]}
    client.request.side_effect = [rescue.DownloadError(403, "not committed"), (200, json.dumps(window).encode())]
    row = {}
    got_memory, distilled = rescue.prepare_review(client, review, row)
    assert got_memory == memory
    assert row["full_download"] == "forbidden/fallback"
    assert row["downloaded_file_id"] == memory["file_id"]
    assert row["has_result"] is False
    assert len(row["old_preview"]) == 120
    assert row["new_preview"] == distilled["distilled_content"][:120]
    for call in client.request.call_args_list:
        assert call.kwargs["project_id"] == memory["project_id"]
        assert call.kwargs["user_id"] == memory["user_id"]


def test_prepare_without_full_downloads_window(review, memory):
    client = Mock()
    client.get_json.side_effect = [memory, {"full_file_id": None}]
    client.request.return_value = 200, json.dumps({"messages": [{"role": "user", "content": TASK}]}).encode()
    row = {}
    rescue.prepare_review(client, review, row)
    assert row["full_download"] == "absent"
    assert client.request.call_count == 1


def test_default_client_refuses_post_and_redirect():
    client = rescue.Client("test-key", "test-user")
    client.opener = Mock()
    with pytest.raises(RuntimeError, match="--apply"):
        client.request("agent-api/v1/memories", body={})
    client.opener.open.assert_not_called()
    with pytest.raises(RuntimeError, match="redirect refused"):
        rescue.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.org/")


def test_apply_payload_and_headers_keep_original_identity(review, memory):
    client = rescue.Client("test-key", "runner-user", apply=True)
    response = Mock()
    response.status = 202
    response.read.return_value = b'{"memory_id":"new-1"}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    client.opener = Mock()
    client.opener.open.return_value = response
    rescue.apply_review(client, review, memory, {"distilled_content": "new content"})
    request = client.opener.open.call_args.args[0]
    headers = {key.lower(): value for key, value in request.header_items()}
    assert request.method == "POST"
    assert request.full_url == rescue.BASE_URL + "agent-api/v1/memories"
    assert headers["x-project-id"] == memory["project_id"]
    assert headers["x-user-id"] == memory["user_id"]
    assert headers["x-agent-id"] == "pi"
    assert headers["authorization"] == "Bearer test-key"
    assert headers["idempotency-key"].startswith("rescue:r-1:")
    body = json.loads(request.data)
    for field in ("session_id", "session_version", "file_id", "project_id", "scope_type"):
        assert body[field] == memory[field]
    assert body["source_event_id"] == headers["idempotency-key"]
    assert body["schema_version"] == "memory-write/1"
    assert body["memory_type"] == "session_summary"
    assert body["dry_run"] is False


def prepare_stub(memory):
    def prepare(client, review, row):
        row.update(new_preview="result", still_no_substantive_content=False, has_result=True,
                   unchanged=False)
        return memory, {"distilled_content": "result"}
    return prepare


def test_dry_run_never_submits(monkeypatch, memory, review):
    monkeypatch.setattr(rescue, "rejected_reviews", lambda client: [review])
    monkeypatch.setattr(rescue, "prepare_review", prepare_stub(memory))
    post = Mock(side_effect=AssertionError("must not POST"))
    monkeypatch.setattr(rescue, "apply_review", post)
    report = rescue.run(Mock())
    post.assert_not_called()
    assert report["summary"]["substantive"] == 1
    assert report["summary"]["submitted"] == 0


def test_apply_reports_self_dedup_and_continues_failures(monkeypatch, memory, review):
    reviews = [dict(review, review_id="r-%s" % i) for i in range(3)]
    monkeypatch.setattr(rescue, "rejected_reviews", lambda client: reviews)
    monkeypatch.setattr(rescue, "prepare_review", prepare_stub(memory))
    post = Mock(side_effect=[(202, {"deduplicated": True, "deduplicated_from_memory_id": memory["memory_id"]}),
                            rescue.DownloadError(500, "failure"), (202, {"memory_id": "new"})])
    monkeypatch.setattr(rescue, "apply_review", post)
    sleep = Mock()
    monkeypatch.setattr(rescue.time, "sleep", sleep)
    monkeypatch.setattr(rescue.time, "monotonic", lambda: 1.0)
    report = rescue.run(Mock(), apply=True)
    assert report["summary"]["submitted"] == 3
    assert report["summary"]["accepted_202"] == 2
    assert report["summary"]["failed"] == 2
    assert "内容未变化" in report["items"][0]["error"]
    assert report["items"][2]["status"] == "submitted"
    assert [call.args for call in sleep.call_args_list] == [(0.3,), (0.3,)]


def test_main_defaults_to_dry_run_writes_report(tmp_path, monkeypatch, review, memory):
    monkeypatch.setenv("MEMORY_HUB_API_KEY", "test-key")
    monkeypatch.setenv("MEMORY_HUB_CLIENT_USER_ID", "runner-user")
    monkeypatch.setattr(rescue, "rejected_reviews", lambda client: [review])
    monkeypatch.setattr(rescue, "prepare_review", prepare_stub(memory))
    output = tmp_path / "report.json"
    assert rescue.main(["--output", str(output)]) == 0
    report = json.loads(output.read_text())
    assert report["mode"] == "dry-run"
    assert report["projects"][memory["project_id"]]["substantive"] == 1

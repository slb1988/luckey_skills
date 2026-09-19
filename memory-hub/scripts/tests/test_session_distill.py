"""Offline 23084 extraction contract; no live model or Hub writes."""
import copy
import io
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from memory_hook import Config, HubClient, classify_snapshot, llm_classify_session
from session_distill import DISTILL_VERSION, parse_troubleshooting, render_troubleshooting

CASE = json.loads((Path(__file__).parent / "fixtures/troubleshooting_copy_cook_logs.json").read_text(encoding="utf-8"))
SOURCE = "\n".join([*CASE["user_messages"], CASE["last_assistant"]])


def config(tmp_path):
    return Config(hub_url="http://unused.test", default_user_id="user-a", agent_id="claude",
                  archive_project_id="project-a", api_key=None, timeout_seconds=8, state_dir=tmp_path)


def test_23084_structure_is_verbatim_and_does_not_claim_verification():
    parsed = parse_troubleshooting(CASE["troubleshooting"], SOURCE)
    assert parsed == CASE["troubleshooting"]
    text = render_troubleshooting(parsed)
    assert all(label + "：" in text for label in ("症状", "组件或脚本", "已验证路径", "根因", "修复状态", "验证点"))
    assert "${dst}:" in text and "待新构建验证" in text and "根因：unknown" in text


@pytest.mark.parametrize("change", [None, {}, {"root_cause": "已经确认语法是唯一根因"},
    {"verified_paths": ["D:/invented/BuildProjectWindows.kts"]}, {"fix_status": "新构建已通过"},
    {"verification_points": "not a list"}, {"symptom": "x" * 601}])
def test_optional_invalid_or_invented_structure_is_omitted(change):
    value = {**CASE["troubleshooting"], **change} if change else change
    assert parse_troubleshooting(value, SOURCE) is None


def test_existing_classifier_one_request_returns_grounded_optional_fields():
    verdict = {"meaningful": True, "title": "修复构建脚本", "troubleshooting": CASE["troubleshooting"]}
    response = {"choices": [{"message": {"content": json.dumps(verdict, ensure_ascii=False)}}]}
    requests = []
    class Opener:
        def open(self, request, timeout):
            requests.append(json.loads(request.data))
            return io.BytesIO(json.dumps(response).encode())
    with patch.dict(os.environ, {"MEMORY_HUB_TITLE_LLM": "1"}), patch("urllib.request.build_opener", return_value=Opener()):
        result = llm_classify_session(CASE["user_messages"], CASE["last_assistant"])
    assert result["troubleshooting"] == CASE["troubleshooting"] and result["distill_version"] == DISTILL_VERSION
    assert len(requests) == 1
    prompt = requests[0]["messages"][0]["content"]
    assert "verified_paths" in prompt and "待新构建验证" in prompt


def test_classify_cache_and_resumed_upload_render_same_structure_in_existing_body(tmp_path):
    cfg = config(tmp_path)
    job = {"user_id": "user-a", "project_id": "project-a", "source": "claude",
           "session_id": "session-a", "sha256": "snapshot-a"}
    texts = (CASE["user_messages"], CASE["user_messages"][0], CASE["user_messages"][0], CASE["last_assistant"], [])
    verdict = {"meaningful": True, "title": "构建脚本修复", "troubleshooting": copy.deepcopy(CASE["troubleshooting"])}
    with patch("memory_hook.llm_classify_session", return_value=verdict) as llm:
        details = {}
        classify_snapshot(cfg, job["sha256"], texts[0], texts[3], details=details)
        assert details["troubleshooting"] == verdict["troubleshooting"]
        client, writes = HubClient(cfg), []
        def request(method, path, project, user, **kwargs):
            if method == "POST":
                writes.append(kwargs["json_body"])
                return {"memory_id": "memory-a", "status": "pending"}
            return {"latest_version": 1, "content_sha256": job["sha256"], "file_id": "file-a"}
        client.request = request
        with patch("memory_hook.load_session_texts", return_value=texts):
            client.upload_job(job)
        assert llm.call_count == 1  # Cached structure, no new distillation pipeline/call.
    body = writes[0]
    assert body["scope_type"] == "project" and body["memory_type"] == "session_summary"
    assert "排障记录" in body["distilled_content"] and "待新构建验证" in body["distilled_content"]
    assert "首个用户目标" in body["distilled_content"] and len(body["distilled_content"]) <= 16 * 1024
    assert not any(key in body for key in ("approved", "root_cause", "troubleshooting"))


@pytest.mark.parametrize("mode", ["disabled", "invalid_optional", "old_cache", "unavailable"])
def test_missing_structure_never_blocks_existing_archival(tmp_path, mode):
    cfg, details = config(tmp_path), {}
    if mode == "old_cache":
        (tmp_path / "title-cache.jsonl").write_text(json.dumps({"sha256": "s", "title": "旧标题", "meaningful": True}) + "\n")
    verdict = {"title": "构建", "meaningful": True, "troubleshooting": {}} if mode == "invalid_optional" else None
    with patch.dict(os.environ, {"MEMORY_HUB_TITLE_LLM": "0"}), patch("memory_hook.llm_classify_session", return_value=verdict):
        title, meaningful = classify_snapshot(cfg, "s", CASE["user_messages"], CASE["last_assistant"], details=details)
    assert title and meaningful and "troubleshooting" not in details

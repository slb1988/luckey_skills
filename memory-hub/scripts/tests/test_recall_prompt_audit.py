"""The audit-only input is independent of the bounded request and injected response."""
import hashlib
import io
import json
from types import SimpleNamespace
from unittest.mock import patch

from memory_hook import (Config, HubClient, UserProfile, command_search,
                         recall_prompt_audit, recall_prompt_audit_lines, markdown_fenced_lines)


def test_long_raw_prompt_survives_locally_not_in_request_stdout_or_trace(tmp_path):
    raw = "  修复 PowerShell 解析\r\n```pwsh\n" + "unchanged source  😀\n" * 650 + "```\nEND_RAW_INPUT  "
    config = Config(hub_url="http://unit.invalid", default_user_id="user-a", agent_id="pi",
                    archive_project_id="test", api_key=None, timeout_seconds=1, state_dir=tmp_path)
    calls = []
    def request(client, query, project, limit, user, **kwargs):
        calls.append({"query": query, **kwargs})
        return {"facts": [], "injection_context": "相关线索\n- 配置目录 /code/config/，需核验。",
                "injection_context_status": "completed", "audit": {"stage_b": {"items": []}}}
    args = SimpleNamespace(query=raw, project="test", user_id=None, limit=6, max_chars=4000,
                           json=True, source="pi", session_id="s", write_result_file=True, audit_prompt_stdin=True)
    stdout = io.StringIO()
    with patch("memory_hook.read_hook_input", return_value={"text": raw, "source": "pi.input.interactive"}), \
         patch("memory_hook.request_user_profile", return_value=UserProfile("user-a", "Test", "Test")), \
         patch.object(HubClient, "search_response", request), patch("sys.stdout", stdout):
        assert command_search(args, config) == 0
    payload = json.loads(stdout.getvalue())
    from pathlib import Path
    with Path(payload["result_file"]).open(encoding="utf-8", newline="") as f:
        receipt = f.read()
    assert "\n".join(markdown_fenced_lines(raw, "text")) in receipt
    assert hashlib.sha256(raw.encode()).hexdigest() in receipt
    assert f'"input_chars": {len(raw)}' in receipt
    assert "## 原始用户 prompt" in receipt and "## 实际检索 query" in receipt
    assert len(calls[0]["query"]) <= 4000 and len(payload["context"]) <= 4000
    assert raw not in json.dumps(calls, ensure_ascii=False)
    assert "END_RAW_INPUT" not in payload["context"]
    assert "prompt_audit" not in payload and "input_sha256" not in stdout.getvalue()
    assert raw not in (tmp_path / "hook-trace.jsonl").read_text(encoding="utf-8")


def test_missing_input_is_not_query_and_transformations_are_labeled(tmp_path):
    config = Config("http://unit.invalid", "u", "a", "p", "secret-test-key", 1, tmp_path)
    missing = "\n".join(recall_prompt_audit_lines(recall_prompt_audit(None, config)))
    assert "未记录" in missing and "not_recorded" in missing
    text = '<skill name="x">system skill body</skill>\n  user code ```\npassword=secret-test-key\n```  '
    record = recall_prompt_audit({"text": text, "source": "test"}, config)
    assert "system skill body" not in record["text"] and "secret-test-key" not in record["text"]
    assert record["input_chars"] == len(text) and record["stored_chars"] == len(record["text"])
    assert "skill_wrapper_removed" in record["transformations"]
    assert "configured_api_key_redacted" in record["transformations"]
    assert record["text"].endswith("```  ")

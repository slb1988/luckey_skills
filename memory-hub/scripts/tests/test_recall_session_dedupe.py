import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from memory_hook import (
    Config, HubClient, HubError, UserProfile, build_parser, command_search,
    load_injected_memory_ids, remember_injected_memory_ids, rendered_memory_ids,
)


def _response(memory_id: str) -> dict:
    """search-v2 响应：一条记忆被渲染进 context。"""
    return {
        "results": [{"result_id": memory_id, "memory_ids": [memory_id], "text": "x"}],
        "injection_context": "已确认\n- 结论",
        "retrieval_id": "r", "query_hash": "h", "policy_version": "p",
        "quality": {"candidates": 1, "kept": 1, "stage_b": {"status": "completed"}},
        "scope": {"current_project_id": "project-a"},
        "audit": {"stage_a": {"status": "completed"}, "stage_b": {
            "status": "completed",
            "items": [{"slot_id": "s", "status": "known", "category": "confirmed",
                       "source_ids": ["e1"], "conclusion": "结论"}],
            "rendered_items": [{"source_ids": ["e1"], "rendered_text": "- 结论"}],
            "input_sources": [{"source_id": "e1", "result_id": memory_id,
                               "provenance": [{"memory_id": memory_id}]}],
        }},
    }


class RecallSessionDedupeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Config(
            hub_url="http://memory.test", default_user_id="user-a", agent_id="pi",
            archive_project_id="project-a", api_key="secret-test-key", timeout_seconds=8,
            state_dir=Path(self.temp.name),
        )
        self.profile = UserProfile("user-a", "User A", "Test profile")

    def search(self, response: dict, bodies: list) -> int:
        args = build_parser().parse_args([
            "search", "安装 rea", "--project", "project-a", "--json",
            "--source", "pi", "--session-id", "session-1",
        ])

        def fake_request(_self, method, path, project_id, user_id, json_body=None, **_kw):
            bodies.append(json_body)
            return response

        with patch("memory_hook.request_user_profile", return_value=self.profile), \
                patch.object(HubClient, "request", fake_request), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return command_search(args, self.config)

    def test_second_search_in_session_excludes_already_injected_memories(self):
        bodies: list = []
        self.assertEqual(self.search(_response("memory-a"), bodies), 0)
        self.assertNotIn("exclude_memory_ids", bodies[0])
        self.assertIn(bodies[0]["client_platform"], {"windows", "macos", "linux"})
        self.assertEqual(self.search(_response("memory-b"), bodies), 0)
        self.assertEqual(bodies[1]["exclude_memory_ids"], ["memory-a"])
        self.assertEqual(load_injected_memory_ids(self.config, "pi", "session-1"),
                         ["memory-a", "memory-b"])
        self.assertEqual(load_injected_memory_ids(self.config, "pi", "other-session"), [])

    def test_unrendered_candidates_are_not_recorded(self):
        response = _response("memory-a")
        response["audit"]["stage_b"]["rendered_items"] = []
        self.assertEqual(rendered_memory_ids(response["audit"], "已确认"), [])
        self.assertEqual(rendered_memory_ids(_response("memory-a")["audit"], ""), [])

    def test_ledger_is_bounded(self):
        remember_injected_memory_ids(self.config, "pi", "s", [f"m{i}" for i in range(100)])
        ids = load_injected_memory_ids(self.config, "pi", "s")
        self.assertEqual(len(ids), 64)
        self.assertEqual(ids[-1], "m99")

    def test_old_hub_rejecting_new_fields_is_retried_without_them(self):
        bodies: list = []

        def fake_request(_self, method, path, project_id, user_id, json_body=None, **_kw):
            bodies.append(json_body)
            if "client_platform" in json_body:
                raise HubError("HTTP 400: extra fields not permitted", error_code="VALIDATION_ERROR")
            return _response("memory-a")

        with patch.object(HubClient, "request", fake_request):
            result = HubClient(self.config).search_response(
                "q", "project-a", 10, "user-a", exclude_memory_ids=["m"], platform="windows",
            )
        self.assertEqual(len(bodies), 2)
        self.assertNotIn("exclude_memory_ids", bodies[1])
        self.assertNotIn("client_platform", bodies[1])
        self.assertEqual(result["injection_context"], "已确认\n- 结论")

    def test_service_errors_are_not_retried(self):
        calls = []

        def fake_request(_self, *args, **kwargs):
            calls.append(1)
            raise HubError("HTTP 503: judge unavailable", error_code="RETRIEVAL_JUDGE_UNAVAILABLE")

        with patch.object(HubClient, "request", fake_request), self.assertRaises(HubError):
            HubClient(self.config).search_response("q", "project-a", 10, "user-a", platform="macos")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()

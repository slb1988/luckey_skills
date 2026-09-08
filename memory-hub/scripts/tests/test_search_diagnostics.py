import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from memory_hook import Config, HubClient, UserProfile, build_parser, command_search


class SearchDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Config(
            hub_url="http://memory.test", default_user_id="user-a", agent_id="pi",
            archive_project_id="project-a", api_key="secret-test-key", timeout_seconds=8,
            state_dir=Path(self.temp.name),
        )
        self.profile = UserProfile("user-a", "User A", "Test profile")
        self.args = build_parser().parse_args(["search", "needle", "--project", "project-a", "--json"])

    def run_command(self, error):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("memory_hook.request_user_profile", return_value=self.profile), \
                patch("urllib.request.OpenerDirector.open", side_effect=error) as opened, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = command_search(self.args, self.config)
        return code, stdout.getvalue(), stderr.getvalue(), opened.call_count

    def test_503_preserves_trace_ids_without_raw_body_and_never_falls_back(self):
        body = {"error": {"code": "RETRIEVAL_CORRECTION_RESOLVER_UNAVAILABLE",
                          "message": "secret-test-key raw memory payload", "request_id": "request-test",
                          "retryable": True, "details": {"retrieval_id": "retrieval-test", "secret": "private"}}}
        error = urllib.error.HTTPError("http://memory.test", 503, "unavailable", {},
                                       io.BytesIO(json.dumps(body).encode()))
        code, output, stderr, calls = self.run_command(error)
        self.assertEqual((code, calls), (1, 1))
        expected = {"code": "RETRIEVAL_CORRECTION_RESOLVER_UNAVAILABLE", "http_status": 503,
                    "request_id": "request-test", "retrieval_id": "retrieval-test", "retryable": True}
        self.assertEqual(json.loads(output), {"outcome": "error", "error": expected})
        trace = (self.config.state_dir / "hook-trace.jsonl").read_text()
        self.assertIn("retrieval-test", trace)
        for unsafe in ("secret-test-key", "raw memory payload", "private"):
            self.assertNotIn(unsafe, output + stderr + trace)

    def test_non_json_http_error_uses_header_id_not_html(self):
        error = urllib.error.HTTPError("http://memory.test", 502, "bad gateway",
                                       {"X-Request-Id": "proxy-request"}, io.BytesIO(b"<html>secret</html>"))
        code, output, stderr, calls = self.run_command(error)
        self.assertEqual((code, calls), (1, 1))
        self.assertEqual(json.loads(output)["error"],
                         {"code": "HTTP_ERROR", "http_status": 502, "request_id": "proxy-request"})
        self.assertNotIn("secret", output + stderr)

    def test_untrusted_metadata_is_bounded_and_type_checked(self):
        body = {"error": {"code": "bad\nsecret", "request_id": "x" * 500,
                          "retryable": "true", "details": {"retrieval_id": "bad\nvalue"}}}
        error = urllib.error.HTTPError("http://memory.test", 401, "unauthorized", {},
                                       io.BytesIO(json.dumps(body).encode()))
        _, output, _, _ = self.run_command(error)
        self.assertEqual(json.loads(output)["error"], {"code": "HTTP_ERROR", "http_status": 401})

    def test_network_timeout_is_not_empty(self):
        for error in (TimeoutError("secret"), urllib.error.URLError(TimeoutError("secret"))):
            with self.subTest(error=type(error)):
                code, output, stderr, _ = self.run_command(error)
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(output), {"outcome": "timeout", "error": {
                    "code": "REQUEST_TIMEOUT", "retryable": True}})
                self.assertNotIn("secret", output + stderr)

    def test_bad_success_payload_is_failure_not_empty(self):
        for payload in ({}, {"results": "bad"}, {"results": ["bad"]}):
            with self.subTest(payload=payload), \
                    patch("memory_hook.request_user_profile", return_value=self.profile), \
                    patch.object(HubClient, "request", return_value=payload), \
                    redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()):
                self.assertEqual(command_search(self.args, self.config), 1)
                self.assertEqual(json.loads(stdout.getvalue())["error"]["code"], "BAD_RESPONSE")

    def test_successful_empty_retains_quality(self):
        quality = {"mode": "llm", "candidates": 10, "kept": 0, "min_rating": 2}
        with patch("memory_hook.request_user_profile", return_value=self.profile), \
                patch.object(HubClient, "request", return_value={"results": [], "quality": quality}), \
                redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(command_search(self.args, self.config), 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["facts"], [])
        self.assertEqual(result["quality"], quality)
        self.assertNotIn("error", result)

    def test_unconfigured_client_retains_exit_two_with_json_diagnostic(self):
        self.profile = None
        code, output, _, calls = self.run_command(RuntimeError("must not call HTTP"))
        self.assertEqual((code, calls), (2, 0))
        self.assertEqual(json.loads(output)["error"]["code"], "CLIENT_NOT_CONFIGURED")

    def test_plain_cli_has_safe_error_on_stderr(self):
        self.args.json = False
        code, output, stderr, _ = self.run_command(TimeoutError("secret"))
        self.assertEqual((code, output), (1, ""))
        self.assertIn("REQUEST_TIMEOUT", stderr)
        self.assertNotIn("secret", stderr)

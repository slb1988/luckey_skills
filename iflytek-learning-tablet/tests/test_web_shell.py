import argparse
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "web_shell", Path(__file__).resolve().parents[1] / "scripts" / "web_shell.py"
)
web_shell = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(web_shell)


class WebShellTests(unittest.TestCase):
    def capture(self, command):
        marker = "__TEST_EXIT__="
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result with spaces.txt"
            subprocess.run(
                ["sh", "-c", web_shell.capture_command(command, str(output), marker)],
                check=True,
            )
            return web_shell.parse_result(output.read_text(), marker)

    def test_quotes_and_unicode(self):
        output, status = self.capture("printf '%s\\n' '中文 $HOME & a;b \"quoted\"'")
        self.assertEqual(output, '中文 $HOME & a;b "quoted"\n')
        self.assertEqual(status, 0)

    def test_failure_and_stderr(self):
        output, status = self.capture("printf 'error\\n' >&2; exit 7")
        self.assertEqual(output, "error\n")
        self.assertEqual(status, 7)

    def test_empty_output_still_completes(self):
        self.assertEqual(self.capture("exit 0"), ("", 0))

    def test_incomplete_output_is_not_success(self):
        for text in ("OK", "hello", "hello\nMARK=0", "hello\nMARK=oops\n"):
            self.assertIsNone(web_shell.parse_result(text, "MARK="))

    def test_form_encoding(self):
        command = "printf '%s' 'a&b=中文'"
        for mode, prefix in (("adb", "1"), ("local", "0")):
            fields = urllib.parse.parse_qs(web_shell.form_data(mode, command).decode())
            self.assertEqual(fields, {"shareUrl": [prefix + command]})

    def test_origin_validation(self):
        self.assertEqual(web_shell.base_url("http://device.local:9898/"),
                         "http://device.local:9898")
        for value in ("file:///tmp/x", "http://device/cmd.html", "http://user:pass@device",
                      "http://device/?query=1", "http://device/#x"):
            with self.assertRaises(argparse.ArgumentTypeError):
                web_shell.base_url(value)

    def test_missing_file_then_completed(self):
        opener = Mock()
        opener.open.side_effect = [
            urllib.error.HTTPError("http://device/result", 500, "not ready", {}, None),
            io.BytesIO(b"result\nMARK=0\n"),
        ]
        with patch.object(web_shell.time, "sleep"):
            result = web_shell.wait_result(opener, "http://device/result", "MARK=", 2)
        self.assertEqual(result, ("result", 0))
        self.assertEqual(opener.open.call_count, 2)

    def test_wait_timeout_does_not_submit(self):
        opener = Mock()
        with self.assertRaises(TimeoutError):
            web_shell.wait_result(opener, "http://device/result", "MARK=", 0)
        opener.open.assert_not_called()

    def test_unexpected_acknowledgement_fails(self):
        opener = Mock()
        response = io.BytesIO(b"not the expected command endpoint")
        response.status = 200
        opener.open.return_value = response
        with self.assertRaises(RuntimeError):
            web_shell.post_command(opener, "http://device", "adb", "id")
        self.assertEqual(opener.open.call_count, 1)


if __name__ == "__main__":
    unittest.main()

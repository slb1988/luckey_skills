from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from insight_daily import (  # noqa: E402
    ClientConfig,
    InsightDailyError,
    canonical_json_bytes,
    execute_run,
    extract_sections,
    prepare_daily,
    sha256_bytes,
    verify_manifest,
)


DATE = "2026-09-06"
NOTE_TEXT = """---
id: daily-20260906
---
# 2026-09-06

```markdown
## 今日决策
- 这是 fenced 假标题
```

## DailySucc
- [x] 完成第一轮人物建模接口

## TODO
### 重要且紧急
- [ ] 补齐 deterministic tests

## 今日决策
- 保持日报与洞察 skill 解耦，先本地逐字校验。

## DailySucc
- [x] 修复中文（CJK）定位：你好，世界。

## 长期目标变动
- 人物画像必须可追溯、可撤销。

## App 使用时长
- 这段不应上传
"""

EMPTY_NOTE = """# 2026-09-06

## TODO
### 重要且紧急
- [ ]

## DailySucc
-

## 长期目标
<!-- 尚未填写 -->
"""


class VaultFixture:
    def __init__(self, root: Path, note_text: str = NOTE_TEXT) -> None:
        self.root = root
        (root / ".obsidian").mkdir(parents=True)
        (root / ".obsidian" / "daily-notes.json").write_text(
            json.dumps({"folder": "02_notes/daily"}), encoding="utf-8"
        )
        self.folder = root / "02_notes" / "daily"
        self.folder.mkdir(parents=True)
        self.note = self.folder / (DATE + ".md")
        self.note.write_text(note_text, encoding="utf-8")


class FakeHub:
    def __init__(self, mode: str = "done") -> None:
        self.mode = mode
        self.requests = []
        self.input_id = "input-test-1"
        self.run_id = "run-test-1"
        self.input_created = False
        self.run_created = False
        self.poll_count = 0
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format, *args):
                return

            def _json_body(self):
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b""
                return json.loads(raw.decode("utf-8")) if raw else None

            def _send(self, status, payload):
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _auth_or_error(self):
                if self.headers.get("Authorization") != "Bearer test-token":
                    self._send(
                        401,
                        {"error": {"code": "UNAUTHENTICATED", "message": "bad token"}},
                    )
                    return False
                return True

            def do_POST(self):
                body = self._json_body()
                fixture.requests.append(("POST", self.path, body))
                if not self._auth_or_error():
                    return
                if fixture.mode == "no-person" and self.path.endswith("/input"):
                    self._send(
                        404,
                        {
                            "error": {
                                "code": "PERSON_NOT_FOUND",
                                "message": "no active self persona",
                            }
                        },
                    )
                    return
                if self.path == "/v1/insights/daily/%s/input" % DATE:
                    created = not fixture.input_created
                    fixture.input_created = True
                    sections = body["sections_md"]
                    self._send(
                        201 if created else 200,
                        {
                            "created": created,
                            "input": {
                                "input_id": fixture.input_id,
                                "person_id": "person-test-1",
                                "local_date": DATE,
                                "revision": 1,
                                "note_path": body["note_path"],
                                "note_sha256": body["note_sha256"],
                                "content_sha256": hashlib.sha256(
                                    sections.encode("utf-8")
                                ).hexdigest(),
                                "created_by": "test-user",
                                "created_at": "2026-09-06T00:00:00Z",
                            },
                        },
                    )
                    return
                if self.path == "/v1/insights/daily/%s/run" % DATE:
                    created = not fixture.run_created
                    fixture.run_created = True
                    self._send(
                        202 if created else 200,
                        {
                            "created": created,
                            "run": fixture.run_payload("queued"),
                        },
                    )
                    return
                self._send(404, {"error": {"code": "RESOURCE_NOT_FOUND"}})

            def do_GET(self):
                fixture.requests.append(("GET", self.path, None))
                if not self._auth_or_error():
                    return
                if self.path != "/v1/insights/runs/%s" % fixture.run_id:
                    self._send(
                        404, {"error": {"code": "RESOURCE_NOT_FOUND"}}
                    )
                    return
                fixture.poll_count += 1
                if fixture.mode == "failed":
                    payload = fixture.run_payload("failed")
                    payload["error"] = "INSIGHT_LLM_FAILED"
                elif fixture.mode == "timeout":
                    payload = fixture.run_payload("queued")
                else:
                    payload = fixture.run_payload(
                        "running" if fixture.poll_count == 1 else "done"
                    )
                self._send(200, payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def run_payload(self, status: str):
        return {
            "run_id": self.run_id,
            "status": status,
            "sources_total": 3 if status != "queued" else 0,
            "sources_processed": 3 if status == "done" else 0,
            "proposals_created": 4 if status in {"done", "failed"} else 0,
            "error": None,
        }

    @property
    def url(self):
        host, port = self.server.server_address
        return "http://%s:%d" % (host, port)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class InsightDailyTest(unittest.TestCase):
    def test_heading_duplicates_fences_and_cjk_are_deterministic(self):
        sections, payload = extract_sections(NOTE_TEXT)
        self.assertEqual(
            [section.key for section in sections],
            [
                "daily_success",
                "todo",
                "decisions",
                "daily_success",
                "long_term_goals",
            ],
        )
        self.assertEqual([section.occurrence for section in sections if section.key == "daily_success"], [1, 2])
        self.assertIn("你好，世界", payload)
        self.assertNotIn("fenced 假标题", payload)
        self.assertNotIn("App 使用时长", payload)
        for section in sections:
            self.assertGreaterEqual(section.end_line, section.start_line)
            self.assertEqual(
                hashlib.sha256(section.source_text.encode("utf-8")).hexdigest(),
                section.manifest_dict()["source_sha256"],
            )
        second_sections, second_payload = extract_sections(NOTE_TEXT)
        self.assertEqual(sections, second_sections)
        self.assertEqual(payload, second_payload)

    def test_missing_and_empty_sections_have_distinct_errors(self):
        with self.assertRaises(InsightDailyError) as missing:
            extract_sections("# day\n\n## App 使用时长\n- 2h\n")
        self.assertEqual(missing.exception.code, "NO_RELEVANT_SECTIONS")
        with self.assertRaises(InsightDailyError) as empty:
            extract_sections(EMPTY_NOTE)
        self.assertEqual(empty.exception.code, "EMPTY_SECTIONS")

    def test_path_traversal_and_symlink_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "vault"
            fixture = VaultFixture(root)
            with self.assertRaises(InsightDailyError) as traversal:
                prepare_daily(root, DATE, "../outside.md")
            self.assertEqual(traversal.exception.code, "UNSAFE_PATH")

            outside = Path(directory) / "outside"
            outside.mkdir()
            outside_note = outside / (DATE + ".md")
            outside_note.write_text(NOTE_TEXT, encoding="utf-8")
            link = fixture.folder / "escape"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")
            with self.assertRaises(InsightDailyError) as symlink:
                prepare_daily(root, DATE, "02_notes/daily/escape/%s.md" % DATE)
            self.assertEqual(symlink.exception.code, "UNSAFE_PATH")

    def test_manifest_hash_locator_and_note_tampering_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "vault"
            fixture = VaultFixture(root)
            state = Path(directory) / "state"
            config = self.config(root, state, "http://127.0.0.1:1", api_key=None)
            result = execute_run(
                vault_root=root,
                local_date=DATE,
                note_argument=None,
                person_id=None,
                dry_run=True,
                timeout_seconds=1,
                config=config,
            )
            manifest_path = Path(result["manifest_path"])
            verified = verify_manifest(manifest_path, vault_root=root)
            self.assertTrue(verified["ok"])
            self.assertEqual(verified["network_requests"], 0)

            original = json.loads(manifest_path.read_text(encoding="utf-8"))
            original["hub"]["status"] = "tampered"
            manifest_path.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaises(InsightDailyError) as content_tamper:
                verify_manifest(manifest_path, vault_root=root)
            self.assertEqual(content_tamper.exception.code, "MANIFEST_HASH_MISMATCH")

            # Re-address the tampered object so filename integrity passes; locator verification must still fail.
            original["hub"]["status"] = "dry_run"
            original["extraction"]["sections"][0]["start_line"] += 1
            raw = canonical_json_bytes(original)
            locator_path = manifest_path.parent / (sha256_bytes(raw) + ".json")
            locator_path.write_bytes(raw + b"\n")
            with self.assertRaises(InsightDailyError) as locator_tamper:
                verify_manifest(locator_path, vault_root=root)
            self.assertEqual(locator_tamper.exception.code, "LOCATOR_MISMATCH")

            # Recreate the valid manifest, then mutate the source note.
            fixture.note.write_text(NOTE_TEXT + "\n补记\n", encoding="utf-8")
            valid_manifest = result["manifest_path"]
            # The previous file was modified above; make a newly addressed pristine copy.
            pristine = execute_run(
                vault_root=root,
                local_date=DATE,
                note_argument=None,
                person_id=None,
                dry_run=True,
                timeout_seconds=1,
                config=config,
            )["manifest_path"]
            fixture.note.write_text(NOTE_TEXT + "\n再次变更\n", encoding="utf-8")
            with self.assertRaises(InsightDailyError) as note_tamper:
                verify_manifest(Path(pristine), vault_root=root)
            self.assertEqual(note_tamper.exception.code, "NOTE_HASH_MISMATCH")
            self.assertTrue(valid_manifest)

    def test_dry_run_opens_no_network_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "vault"
            VaultFixture(root)
            config = self.config(
                root, Path(directory) / "state", "http://network.invalid", api_key=None
            )
            with patch.object(
                urllib.request.OpenerDirector,
                "open",
                side_effect=AssertionError("dry-run must not open a socket"),
            ):
                result = execute_run(
                    vault_root=root,
                    local_date=DATE,
                    note_argument=None,
                    person_id=None,
                    dry_run=True,
                    timeout_seconds=1,
                    config=config,
                )
            self.assertEqual(result["status"], "dry_run")
            self.assertIsNone(result["input_id"])
            self.assertIsNone(result["run_id"])

    def test_http_idempotency_and_queued_to_done(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "vault"
            VaultFixture(root)
            hub = FakeHub("done")
            try:
                config = self.config(root, Path(directory) / "state", hub.url)
                first = self.execute(root, config)
                second = self.execute(root, config)
            finally:
                hub.close()
            self.assertEqual(first["status"], "done")
            self.assertEqual(first["proposals_created"], 4)
            self.assertEqual(first["input_id"], second["input_id"])
            self.assertEqual(first["run_id"], second["run_id"])
            post_bodies = [body for method, _path, body in hub.requests if method == "POST"]
            input_body = next(body for body in post_bodies if body["schema_version"] == "insight-daily-input/1")
            run_body = next(body for body in post_bodies if body["schema_version"] == "insight-daily-run/1")
            self.assertEqual(run_body["input_id"], hub.input_id)
            self.assertNotIn("content", input_body)
            self.assertNotIn("full_note", input_body)
            self.assertIn("sections_md", input_body)
            manifest = json.loads(Path(first["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["hub"]["input_id"], hub.input_id)
            self.assertEqual(manifest["hub"]["run_id"], hub.run_id)

    def test_failed_and_timeout_runs_are_actionable(self):
        for mode, expected in (("failed", "RUN_FAILED"), ("timeout", "POLL_TIMEOUT")):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "vault"
                VaultFixture(root)
                hub = FakeHub(mode)
                try:
                    config = self.config(root, Path(directory) / "state", hub.url)
                    with self.assertRaises(InsightDailyError) as failure:
                        self.execute(
                            root,
                            config,
                            timeout=0.04 if mode == "timeout" else 1,
                        )
                finally:
                    hub.close()
                self.assertEqual(failure.exception.code, expected)
                self.assertEqual(failure.exception.details["run_id"], hub.run_id)
                self.assertTrue(Path(failure.exception.details["manifest_path"]).is_file())

    def test_http_401_and_no_active_self_404_are_stable(self):
        cases = (("done", "wrong-token", "UNAUTHENTICATED"), ("no-person", "test-token", "PERSON_NOT_FOUND"))
        for mode, token, expected in cases:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "vault"
                VaultFixture(root)
                hub = FakeHub(mode)
                try:
                    config = self.config(
                        root, Path(directory) / "state", hub.url, api_key=token
                    )
                    with self.assertRaises(InsightDailyError) as failure:
                        self.execute(root, config)
                finally:
                    hub.close()
                self.assertEqual(failure.exception.code, expected)
                self.assertNotIn(token, str(failure.exception))
                self.assertTrue(Path(failure.exception.details["manifest_path"]).is_file())

    @staticmethod
    def config(root: Path, state: Path, url: str, api_key: str | None = "test-token"):
        return ClientConfig(
            base_url=url,
            dashboard_url=url + "/dashboard/",
            api_key=api_key,
            user_id="test-user",
            project_id="obsidianvault-test",
            state_dir=state,
            request_timeout=0.2,
        )

    @staticmethod
    def execute(root: Path, config: ClientConfig, timeout: float = 1):
        return execute_run(
            vault_root=root,
            local_date=DATE,
            note_argument=None,
            person_id=None,
            dry_run=False,
            timeout_seconds=timeout,
            poll_seconds=0.005,
            config=config,
        )


if __name__ == "__main__":
    unittest.main()

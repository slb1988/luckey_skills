import gzip
import json
import tempfile
import unittest
from pathlib import Path

from memory_hook import Config, HubClient, StateStore, build_snapshot, flush_pending


class MemoryHookTest(unittest.TestCase):
    def test_capture_is_durable_and_idempotent_while_server_is_down(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "remember this"}})
                + "\n"
                + json.dumps(
                    {"type": "assistant", "message": {"content": "remembered"}}
                ),
                encoding="utf-8",
            )
            config = Config(
                hub_url="http://127.0.0.1:1",
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=0.1,
                state_dir=root / "state",
            )
            store = StateStore(config)
            first = store.enqueue("user-a", "codex", "session-1", str(root), transcript)
            second = store.enqueue("user-a", "codex", "session-1", str(root), transcript)

            self.assertTrue(first["inserted"])
            self.assertFalse(second["inserted"])
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["user_id"], "user-a")
            self.assertEqual(store.status()["counts"], {"queued": 1})

            transcript.write_text(
                transcript.read_text(encoding="utf-8")
                + "\n"
                + json.dumps({"type": "user", "message": {"content": "new turn"}}),
                encoding="utf-8",
            )
            third = store.enqueue("user-a", "codex", "session-1", str(root), transcript)
            self.assertTrue(third["inserted"])
            self.assertEqual(
                store.status()["counts"], {"queued": 1, "superseded": 1}
            )
            result = flush_pending(store, config, 10)
            self.assertEqual(result["failed"], 1)
            self.assertEqual(
                store.status()["counts"], {"queued": 1, "superseded": 1}
            )

    def test_snapshot_keeps_recent_messages_markdown_and_drops_fenced_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            records = [
                {"type": "user", "message": {"content": "message %d" % index}}
                for index in range(12)
            ]
            records.append(
                {
                    "type": "assistant",
                    "message": {
                        "content": "# Result\n\nKeep this.\n\n```python\nsecret = 1\n```\n\nDone."
                    },
                }
            )
            transcript.write_text(
                "\n".join(json.dumps(record) for record in records), encoding="utf-8"
            )
            snapshot = build_snapshot(
                transcript, "codex", "codex:session-1", str(root), root / "objects"
            )
            try:
                with gzip.open(snapshot.path, "rt", encoding="utf-8") as stored:
                    payload = json.load(stored)
                self.assertEqual(payload["schema_version"], "agent-session/2")
                self.assertEqual(len(payload["messages"]), 10)
                self.assertEqual(payload["messages"][0]["content"], "message 3")
                markdown = payload["messages"][-1]["content"]
                self.assertIn("# Result", markdown)
                self.assertNotIn("secret = 1", markdown)
            finally:
                snapshot.path.unlink(missing_ok=True)

    def test_hub_headers_use_request_user_not_process_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(
                hub_url="http://memory.test",
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=Path(directory),
            )
            headers = HubClient(config).headers("project-a", "user-b")
            self.assertEqual(headers["X-User-Id"], "user-b")
            self.assertEqual(headers["X-Agent-Id"], "test-agent")

    def test_spool_keeps_same_session_snapshot_separate_per_user(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "same"}}),
                encoding="utf-8",
            )
            config = Config(
                hub_url="http://memory.test",
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=root / "state",
            )
            store = StateStore(config)
            first = store.enqueue("user-a", "codex", "session-1", str(root), transcript)
            second = store.enqueue("user-b", "codex", "session-1", str(root), transcript)
            self.assertTrue(first["inserted"])
            self.assertTrue(second["inserted"])
            self.assertEqual(store.status()["counts"], {"queued": 2})
            rows = store.queued(10)
            self.assertEqual({row["user_id"] for row in rows}, {"user-a", "user-b"})
            self.assertEqual(len({row["snapshot_path"] for row in rows}), 2)

    def test_search_and_memory_write_carry_request_user(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "remember"}}),
                encoding="utf-8",
            )
            config = Config(
                hub_url="http://memory.test",
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=root / "state",
            )
            store = StateStore(config)
            store.enqueue("user-b", "codex", "session-1", str(root), transcript)
            job = store.queued(1)[0]
            client = HubClient(config)
            calls = []

            def fake_request(method, path, project_id, user_id, **kwargs):
                calls.append((method, path, project_id, user_id, kwargs))
                if path == "/v1/memories/search":
                    return {"facts": []}
                return {"memory_id": "memory-1", "status": "pending"}

            client.request = fake_request
            self.assertEqual(client.search("query", "project-a", 5, "user-b"), [])
            client.ensure_memory(job, 1, "file-1")

            search_call = calls[0]
            self.assertEqual(search_call[3], "user-b")
            self.assertEqual(search_call[4]["json_body"]["user_id"], "user-b")
            memory_call = calls[1]
            self.assertEqual(memory_call[3], "user-b")
            self.assertEqual(memory_call[4]["json_body"]["scope_type"], "user")
            self.assertEqual(memory_call[4]["json_body"]["user_id"], "user-b")


if __name__ == "__main__":
    unittest.main()

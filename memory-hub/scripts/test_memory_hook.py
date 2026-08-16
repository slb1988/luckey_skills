import json
import tempfile
import unittest
from pathlib import Path

from memory_hook import Config, StateStore, flush_pending


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
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=0.1,
                state_dir=root / "state",
            )
            store = StateStore(config)
            first = store.enqueue("codex", "session-1", str(root), transcript)
            second = store.enqueue("codex", "session-1", str(root), transcript)

            self.assertTrue(first["inserted"])
            self.assertFalse(second["inserted"])
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(store.status()["counts"], {"queued": 1})

            transcript.write_text(
                transcript.read_text(encoding="utf-8")
                + "\n"
                + json.dumps({"type": "user", "message": {"content": "new turn"}}),
                encoding="utf-8",
            )
            third = store.enqueue("codex", "session-1", str(root), transcript)
            self.assertTrue(third["inserted"])
            self.assertEqual(
                store.status()["counts"], {"queued": 1, "superseded": 1}
            )

            result = flush_pending(store, config, 10)
            self.assertEqual(result["failed"], 1)
            self.assertEqual(
                store.status()["counts"], {"queued": 1, "superseded": 1}
            )


if __name__ == "__main__":
    unittest.main()

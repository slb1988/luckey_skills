"""rotate_pi_trace.py 的单元测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rotate_pi_trace import main, rotate_trace


class RotatePiTraceTest(unittest.TestCase):
    def test_rotates_existing_trace_to_timestamped_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            trace = state_dir / "pi-trace.jsonl"
            trace.write_text('{"kind":"session_start"}\n', encoding="utf-8")
            result = rotate_trace(state_dir)
            self.assertTrue(result["rotated"])
            self.assertFalse(trace.exists())
            backup = Path(result["backup"])
            self.assertTrue(backup.is_file())
            self.assertEqual(backup.parent, state_dir / "trace-backups")
            self.assertTrue(backup.name.startswith("pi-trace-"))
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8").strip())["kind"], "session_start")

    def test_missing_trace_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = rotate_trace(Path(directory))
            self.assertFalse(result["rotated"])
            self.assertEqual(result["reason"], "missing")

    def test_same_second_rotation_gets_unique_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            trace = state_dir / "pi-trace.jsonl"
            trace.write_text("first\n", encoding="utf-8")
            first = rotate_trace(state_dir)
            trace.write_text("second\n", encoding="utf-8")
            second = rotate_trace(state_dir)
            self.assertTrue(first["rotated"] and second["rotated"])
            self.assertNotEqual(first["backup"], second["backup"])
            self.assertEqual(
                sorted(p.read_text(encoding="utf-8") for p in (state_dir / "trace-backups").iterdir()),
                ["first\n", "second\n"],
            )

    def test_main_include_hook_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            (state_dir / "pi-trace.jsonl").write_text("pi\n", encoding="utf-8")
            (state_dir / "hook-trace.jsonl").write_text("hook\n", encoding="utf-8")
            self.assertEqual(main(["--state-dir", directory, "--include-hook-trace"]), 0)
            backups = sorted(p.name for p in (state_dir / "trace-backups").iterdir())
            self.assertEqual(len(backups), 2)
            self.assertFalse((state_dir / "pi-trace.jsonl").exists())
            self.assertFalse((state_dir / "hook-trace.jsonl").exists())


if __name__ == "__main__":
    unittest.main()

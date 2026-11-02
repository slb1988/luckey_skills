import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import orca_session_backup as backup


def make_tab(name):
    cwd = f"D:/{name}"
    session = backup.Session("pi", f"session-{name}", Path("fixture.jsonl"), cwd,
                             prompts=[f"Task in {name}"])
    return backup.Tab(
        handle=f"term-{name}", pty_id=f"pty-{name}", title=name, agent="pi",
        worktree_id=name, worktree_path=cwd, branch="", started=None, preview="",
        sessions=[(session, ["启动时间吻合"])],
    )


class BackupScopeTests(unittest.TestCase):
    def run_backup(self, *options):
        tabs = [make_tab("MainDev"), make_tab("ObsidianVault")]
        with tempfile.TemporaryDirectory() as out, \
                patch.object(sys, "argv", ["backup", "backup", *options, "--out", out]), \
                patch.object(backup, "collect") as collect, \
                patch.object(backup, "resolve_worktree", return_value="path:D:/MainDev") as resolve, \
                contextlib.redirect_stdout(io.StringIO()):
            collect.side_effect = lambda selector: (tabs if selector is None else tabs[:1], {})
            backup.main()
            files = list(Path(out).glob("*.md"))
            self.assertEqual(len(files), 1)
            return files[0].name, files[0].read_text(encoding="utf-8"), collect, resolve

    def test_default_includes_all_workspaces(self):
        name, text, collect, resolve = self.run_backup()
        collect.assert_called_once_with(None)
        resolve.assert_not_called()
        self.assertTrue(name.startswith("orca-sessions-all-"))
        self.assertIn("scope: all", text)
        self.assertIn("## MainDev", text)
        self.assertIn("## ObsidianVault", text)

    def test_explicit_all_remains_supported(self):
        name, text, collect, resolve = self.run_backup("--all")
        collect.assert_called_once_with(None)
        resolve.assert_not_called()
        self.assertTrue(name.startswith("orca-sessions-all-"))
        self.assertIn("## MainDev", text)
        self.assertIn("## ObsidianVault", text)

    def test_explicit_worktree_limits_scope(self):
        name, text, collect, resolve = self.run_backup("--worktree", "MainDev")
        resolve.assert_called_once_with("MainDev")
        collect.assert_called_once_with("path:D:/MainDev")
        self.assertTrue(name.startswith("orca-sessions-MainDev-"))
        self.assertIn("## MainDev", text)
        self.assertNotIn("## ObsidianVault", text)

    def test_explicit_active_is_forwarded(self):
        _, _, collect, resolve = self.run_backup("--worktree", "active")
        resolve.assert_called_once_with("active")
        collect.assert_called_once_with("path:D:/MainDev")

    def test_all_and_worktree_are_mutually_exclusive(self):
        with patch.object(sys, "argv", ["backup", "backup", "--all", "--worktree", "MainDev"]), \
                patch.object(backup, "collect") as collect, \
                contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as error:
            backup.main()
        self.assertEqual(error.exception.code, 2)
        collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()

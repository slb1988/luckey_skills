import json
import tempfile
import unittest
from pathlib import Path

from install_hooks import (
    check_json_hooks,
    check_pi_extension,
    desired_hooks,
    install_json_hooks,
    install_pi_extension,
)


class InstallHooksTest(unittest.TestCase):
    def test_claude_install_preserves_unrelated_hooks_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".claude" / "settings.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "Stop": [
                                {
                                    "hooks": [
                                        {"type": "command", "command": "keep-me", "timeout": 5},
                                        {
                                            "type": "command",
                                            "command": "/old/memory-hub/scripts/memory_hook.py capture --source claude --flush-limit 0",
                                            "timeout": 120,
                                        },
                                    ]
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(install_json_hooks(path, "claude"))
            self.assertTrue(check_json_hooks(path, "claude")["ok"])
            data = json.loads(path.read_text())
            commands = [
                handler["command"]
                for group in data["hooks"]["Stop"]
                for handler in group["hooks"]
            ]
            self.assertIn("keep-me", commands)
            self.assertFalse(any("--flush-limit" in command for command in commands))
            self.assertFalse(install_json_hooks(path, "claude"))

    def test_codex_definition_uploads_each_turn_and_limits_session_end(self):
        hooks = desired_hooks("codex")
        self.assertNotIn("--flush-limit", hooks["Stop"]["command"])
        self.assertEqual(hooks["Stop"]["timeout"], 120)
        self.assertEqual(hooks["SessionEnd"]["timeout"], 3)

    def test_pi_install_debounces_agent_end_upload_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".pi" / "agent" / "extensions" / "memory-hub.ts"
            self.assertTrue(install_pi_extension(path))
            self.assertTrue(check_pi_extension(path)["ok"])
            content = path.read_text(encoding="utf-8")
            self.assertIn('pi.on("agent_end"', content)
            self.assertIn('pi.on("session_shutdown"', content)
            self.assertNotIn("--flush-limit", content)
            # agent_end 不再逐轮立即上传：空闲延时计时 + 新 prompt 取消 + 计时器不拖住退出
            self.assertIn("setTimeout", content)
            self.assertIn(".unref()", content)
            self.assertIn("MEMORY_HOOK_PI_CAPTURE_DELAY_MS", content)
            self.assertIn("cancelPendingCapture", content)
            self.assertFalse(install_pi_extension(path))

    def test_pi_check_rejects_extension_without_idle_debounce(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".pi" / "agent" / "extensions" / "memory-hub.ts"
            install_pi_extension(path)
            content = path.read_text(encoding="utf-8")
            # 模拟有人把模板改回逐轮立即上传：去掉防抖计时器与 unref
            degraded = content.replace("setTimeout", "deferUpload").replace(".unref()", ".noop()")
            path.write_text(degraded, encoding="utf-8")
            errors = check_pi_extension(path)["errors"]
            self.assertTrue(
                any("idle-debounced" in error and "setTimeout" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("idle-debounced" in error and ".unref()" in error for error in errors),
                errors,
            )


if __name__ == "__main__":
    unittest.main()

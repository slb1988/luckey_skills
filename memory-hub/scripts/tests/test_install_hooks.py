import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from install_hooks import (
    PI_TEMPLATE,
    apply_machine_project,
    check_json_hooks,
    check_machine_project,
    check_pi_extension,
    desired_hooks,
    install_json_hooks,
    install_machine_project,
    install_pi_extension,
    normalize_project,
    pi_extension_version,
    resolve_machine_project,
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

    def test_recall_hook_wired_for_claude_and_codex(self):
        for agent in ("claude", "codex"):
            hooks = desired_hooks(agent)
            recall = hooks["UserPromptSubmit"]
            self.assertIn("recall", recall["command"])
            self.assertIn("--source %s" % agent, recall["command"])
            # hook 超时必须高于 recall 内部的 120s 故障上限。
            self.assertGreaterEqual(recall["timeout"], 121)

    def test_pi_install_durable_enqueue_and_debounced_flush_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".pi" / "agent" / "extensions" / "memory-hub.ts"
            self.assertTrue(install_pi_extension(path))
            self.assertTrue(check_pi_extension(path)["ok"])
            content = path.read_text(encoding="utf-8")
            self.assertIn('pi.on("agent_end"', content)
            self.assertIn('pi.on("session_shutdown"', content)
            self.assertNotIn("--flush-limit", content)
            # v5：agent_end 立即 enqueue-only（write-ahead marker + --no-flush 严格契约），
            # flush 走空闲延时计时 + 新 prompt 取消 + 计时器不拖住退出；
            # session_start catch-up 补传遗留 marker。
            self.assertIn("pi-pending-enqueues", content)
            self.assertIn("writeMarker", content)
            self.assertIn('"--no-flush"', content)
            self.assertIn("setTimeout", content)
            self.assertIn(".unref()", content)
            self.assertIn("MEMORY_HOOK_PI_CAPTURE_DELAY_MS", content)
            self.assertIn("cancelPendingFlush", content)
            self.assertIn("catchupPending", content)
            # v27: manual command/tool are always present; automatic card injection is exact opt-in.
            self.assertIn('pi.registerCommand("memory-card"', content)
            self.assertIn('name: "memory_persona_card"', content)
            self.assertIn("MEMORY_HOOK_PI_PERSONA_CARD", content)
            self.assertIn("personaCardMaxChars = 2500", content)
            self.assertIn('trace("memory_persona_card"', content)
            self.assertFalse(install_pi_extension(path))

    def test_pi_template_v28_and_outdated_copy_are_detected(self):
        self.assertEqual(pi_extension_version(PI_TEMPLATE.read_text(encoding="utf-8")), "28")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory-hub.ts"
            install_pi_extension(path)
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    'const EXTENSION_VERSION = "28";',
                    'const EXTENSION_VERSION = "27";',
                    1,
                ),
                encoding="utf-8",
            )
            result = check_pi_extension(path)
            self.assertFalse(result["ok"])
            self.assertIn(
                "extension version 27 is outdated (managed 28); rerun install",
                result["errors"],
            )

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

    def test_normalize_project_lowercases_and_rejects_invalid(self):
        self.assertEqual(normalize_project(" NAS-453D.mini "), "nas-453d.mini")
        self.assertEqual(normalize_project("   "), "")
        self.assertEqual(normalize_project("-._:"), "")

    def test_install_and_check_machine_project(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertFalse(check_machine_project(home)["set"])
            result = install_machine_project("nas", home, {"source": "flag"})
            self.assertTrue(result["ok"])
            self.assertEqual(result["project_id"], "nas")
            self.assertEqual(result["aliases"], {"*": "nas"})
            check = check_machine_project(home)
            self.assertTrue(check["set"])
            self.assertEqual(check["project_id"], "nas")
            self.assertEqual(check["aliases"], {"*": "nas"})
            # 落盘为字典映射（"*" catch-all），非标量 project_id
            local_file = (
                home / ".local" / "state" / "memory-hub-hook" / "project-aliases.local.json"
            )
            self.assertEqual(
                json.loads(local_file.read_text(encoding="utf-8"))["aliases"],
                {"*": "nas"},
            )

    def test_resolve_machine_project_flag_wins_and_noninteractive_suggests(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            pid, meta = resolve_machine_project(
                SimpleNamespace(project=" My-NAS "), home
            )
            self.assertEqual(pid, "my-nas")
            self.assertEqual(meta["source"], "flag")
            # 未给 --project 且本机未设置、非交互（pytest stdin 非 tty）→ 不落盘只建议
            pid2, meta2 = resolve_machine_project(SimpleNamespace(project=None), home)
            self.assertIsNone(pid2)
            self.assertEqual(meta2["source"], "none")
            self.assertIn("suggestion", meta2)

    def test_resolve_machine_project_never_prompts_or_creates_catch_all(self):
        from types import SimpleNamespace

        class InteractiveStdin:
            def isatty(self):
                return True

            def readline(self):
                raise AssertionError("project resolution must not read stdin")

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            with patch("install_hooks.sys.stdin", InteractiveStdin()):
                project_id, meta = resolve_machine_project(
                    SimpleNamespace(project=None), home
                )

            self.assertIsNone(project_id)
            self.assertEqual(meta["source"], "none")
            self.assertFalse(check_machine_project(home)["set"])

    def test_existing_machine_project_is_reported_without_rewrite(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            install_machine_project("nas", home, {"source": "flag"})
            local_file = (
                home
                / ".local"
                / "state"
                / "memory-hub-hook"
                / "project-aliases.local.json"
            )
            before = local_file.read_bytes()

            result = apply_machine_project(SimpleNamespace(project=None), home)

            self.assertEqual(result["project_id"], "nas")
            self.assertFalse(result["changed"])
            self.assertEqual(local_file.read_bytes(), before)

    def test_existing_specific_aliases_are_reported_without_catch_all(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            local_file = (
                home
                / ".local"
                / "state"
                / "memory-hub-hook"
                / "project-aliases.local.json"
            )
            local_file.parent.mkdir(parents=True)
            local_file.write_text(
                json.dumps({"aliases": {"maindev": "maindev"}}), encoding="utf-8"
            )
            before = local_file.read_bytes()

            result = apply_machine_project(SimpleNamespace(project=None), home)

            self.assertTrue(result["set"])
            self.assertEqual(result["aliases"], {"maindev": "maindev"})
            self.assertIsNone(result["project_id"])
            self.assertFalse(result["changed"])
            self.assertEqual(local_file.read_bytes(), before)

    def test_pi_check_rejects_extension_without_durable_enqueue(self):
        # 模拟有人把 v5 退回纯防抖：去掉 write-ahead marker 与 --no-flush 立即入队
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".pi" / "agent" / "extensions" / "memory-hub.ts"
            install_pi_extension(path)
            content = path.read_text(encoding="utf-8")
            degraded = content.replace("writeMarker", "noteMarker").replace(
                '"--no-flush"', '"--defer"'
            )
            path.write_text(degraded, encoding="utf-8")
            errors = check_pi_extension(path)["errors"]
            self.assertTrue(
                any("writeMarker" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("--no-flush" in error for error in errors),
                errors,
            )


if __name__ == "__main__":
    unittest.main()

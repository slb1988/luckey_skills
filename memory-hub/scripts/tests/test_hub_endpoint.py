"""Public Hub base, local overrides, and subpath-safe requests (no network)."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import backfill_missed_pi_sessions as backfill
import install_hooks
import upload_sessions
from memory_hook import Config, HubClient


PUBLIC_HUB_URL = "https://luckeyhome.site/memory-hub/agent-api"


class HubEndpointTest(unittest.TestCase):
    def config(self, home, environment=None):
        env = {"MEMORY_HOOK_STATE_DIR": str(home / "state")}
        env.update(environment or {})
        with patch.dict(os.environ, env, clear=True), patch(
            "memory_hook.Path.home", return_value=home
        ):
            return Config.from_environment(cwd=str(home), default_agent_id="pi")

    def test_hook_defaults_to_public_https_base(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.config(Path(directory)).hub_url, PUBLIC_HUB_URL)

    def test_hook_reads_persisted_url_without_restarting_parent_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".profile").write_text(
                "export MEMORY_HUB_URL='https://custom.test/prefix/'\n",
                encoding="utf-8",
            )
            self.assertEqual(self.config(home).hub_url, "https://custom.test/prefix")

    def test_hook_explicit_environment_wins_and_private_override_still_works(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".profile").write_text(
                "export MEMORY_HUB_URL=" + PUBLIC_HUB_URL + "\n", encoding="utf-8"
            )
            config = self.config(home, {"MEMORY_HUB_URL": "http://127.0.0.1:9287/"})
            self.assertEqual(config.hub_url, "http://127.0.0.1:9287")

    def test_hook_empty_environment_uses_persisted_url(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".profile").write_text(
                "export MEMORY_HUB_URL=" + PUBLIC_HUB_URL + "/\n", encoding="utf-8"
            )
            self.assertEqual(
                self.config(home, {"MEMORY_HUB_URL": ""}).hub_url, PUBLIC_HUB_URL
            )

    def test_requests_preserve_public_prefix_identity_and_idempotency(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(
                Path(directory),
                {"MEMORY_HUB_URL": PUBLIC_HUB_URL, "MEMORY_HUB_API_KEY": "test-token"},
            )
            client = HubClient(config)
            client.opener = MagicMock()
            response = client.opener.open.return_value.__enter__.return_value
            response.read.return_value = b'{"ok":true}'
            body = {"schema_version": "file-upload/1", "size_bytes": 123}
            self.assertEqual(
                client.request(
                    "POST", "/v1/files/uploads", "test-project", "test-user",
                    json_body=body, idempotency_key="test-idempotency",
                ),
                {"ok": True},
            )
            request = client.opener.open.call_args.args[0]
            self.assertEqual(request.full_url, PUBLIC_HUB_URL + "/v1/files/uploads")
            self.assertEqual(request.get_method(), "POST")
            headers = {key.lower(): value for key, value in request.header_items()}
            self.assertEqual(headers["authorization"], "Bearer test-token")
            self.assertEqual(headers["x-project-id"], "test-project")
            self.assertEqual(headers["x-user-id"], "test-user")
            self.assertEqual(headers["idempotency-key"], "test-idempotency")
            self.assertEqual(json.loads(request.data), body)


class InstallerEndpointTest(unittest.TestCase):
    def test_installer_defaults_and_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(install_hooks.resolve_hub_url(home), PUBLIC_HUB_URL)
                (home / ".profile").write_text(
                    "export MEMORY_HUB_URL=https://custom.test/base/\n", encoding="utf-8"
                )
                self.assertEqual(
                    install_hooks.resolve_hub_url(home), "https://custom.test/base"
                )
            with patch.dict(os.environ, {"MEMORY_HUB_URL": "http://localhost:9287/"}):
                self.assertEqual(install_hooks.resolve_hub_url(home), "http://localhost:9287")

    def test_health_and_auth_use_the_same_persisted_base(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            url = "https://custom.test/agent-api"
            (home / ".profile").write_text(
                "export MEMORY_HUB_URL=" + url + "\n", encoding="utf-8"
            )
            opener = MagicMock()
            response = opener.open.return_value.__enter__.return_value
            response.read.return_value = json.dumps({
                "status": "ready", "write_degraded": False,
                "dependencies": {"graphiti": True, "metadata": True},
            }).encode()
            with patch.dict(os.environ, {"MEMORY_HUB_API_KEY": "test-token"}, clear=True), patch(
                "install_hooks.urllib.request.build_opener", return_value=opener
            ), patch("install_hooks._hub_probe", side_effect=[(401, None), (200, None)]) as probe:
                self.assertTrue(install_hooks.health_check(home)["ok"])
                self.assertEqual(opener.open.call_args.args[0], url + "/health/ready")
                self.assertTrue(install_hooks.auth_status(home, home)["token_accepted"])
                self.assertEqual([call.args[0] for call in probe.call_args_list], [url, url])

    def test_reinstall_preserves_url_identity_and_token_in_managed_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            url = "https://custom.test/persisted-prefix"
            (home / ".profile").write_text(
                install_hooks.PROFILE_BLOCK_BEGIN + "\n"
                "export MEMORY_HUB_CLIENT_USER_ID=test-user\n"
                "export MEMORY_HUB_API_KEY=test-token\n"
                "export MEMORY_HUB_URL=" + url + "\n" + install_hooks.PROFILE_BLOCK_END + "\n",
                encoding="utf-8",
            )
            argv = ["install_hooks.py", "install", "--agents", "pi", "--home", str(home),
                    "--cwd", str(home), "--user-id", "test-user"]
            with patch.dict(os.environ, {}, clear=True), patch("sys.argv", argv), patch(
                "install_hooks.run", return_value={"ok": True, "agents": {}}
            ), patch("install_hooks.install_project_aliases", return_value={"ok": True}), patch(
                "install_hooks.health_check", return_value={"ok": True}
            ) as health, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(install_hooks.main(), 0)
                health.assert_called_once_with(home)
            self.assertEqual(install_hooks._read_persisted_env_var(home, "MEMORY_HUB_URL"), url)
            self.assertEqual(install_hooks._read_persisted_env_var(home, "MEMORY_HUB_API_KEY"), "test-token")
            self.assertEqual(install_hooks._read_persisted_env_var(home, "MEMORY_HUB_CLIENT_USER_ID"), "test-user")
            self.assertFalse(install_hooks.machine_project_path(home).exists())


class ArchiveEndpointTest(unittest.TestCase):
    def test_archive_defaults_and_cli_env_overrides(self):
        with patch.dict(os.environ, {}, clear=True):
            args = upload_sessions.build_parser().parse_args(["session.jsonl"])
            self.assertEqual(args.hub_url, PUBLIC_HUB_URL)
            args = upload_sessions.build_parser().parse_args(
                ["session.jsonl", "--hub-url", "http://localhost:9287"]
            )
            self.assertEqual(args.hub_url, "http://localhost:9287")
        with patch.dict(os.environ, {"MEMORY_HUB_URL": "https://custom.test/base"}):
            args = upload_sessions.build_parser().parse_args(["session.jsonl"])
            self.assertEqual(args.hub_url, "https://custom.test/base")

    def test_archive_dashboard_base_preserves_public_prefix_and_private_port(self):
        for suffix in ("", "/"):
            self.assertEqual(
                upload_sessions.derive_dashboard_url(PUBLIC_HUB_URL + suffix),
                "https://luckeyhome.site/memory-hub",
            )
        self.assertEqual(
            upload_sessions.derive_dashboard_url("http://localhost:9287"),
            "http://localhost:9288",
        )

    def backfill_command(self, env, argv=None):
        with patch.dict(os.environ, env, clear=True), patch(
            "sys.argv", ["backfill_missed_pi_sessions.py", *(argv or [])]
        ), patch.object(backfill, "hub_uuids", return_value=set()), patch.object(
            backfill, "local_sessions", return_value={"test-uuid": "session.jsonl"}
        ), patch.object(backfill, "first_user_text", return_value="A real session"), patch.object(
            backfill.subprocess, "call", return_value=0
        ) as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(backfill.main(), 0)
            return run.call_args.args[0]

    def test_backfill_passes_https_base_and_leaves_dashboard_derivation_to_uploader(self):
        command = self.backfill_command({})
        self.assertEqual(command[command.index("--hub-url") + 1], PUBLIC_HUB_URL)
        self.assertNotIn("--dashboard-url", command)
        self.assertIn("--hook-namespace", command)

    def test_backfill_respects_env_and_explicit_dashboard_override(self):
        command = self.backfill_command(
            {"MEMORY_HUB_URL": "http://localhost:9287"},
            ["--dashboard-url", "http://localhost:9288"],
        )
        self.assertEqual(command[command.index("--hub-url") + 1], "http://localhost:9287")
        self.assertEqual(command[command.index("--dashboard-url") + 1], "http://localhost:9288")


if __name__ == "__main__":
    unittest.main()

import gzip
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from memory_hook import (
    Config,
    HubClient,
    StateStore,
    UNCONFIGURED_USER_ID,
    UserProfile,
    build_snapshot,
    command_capture,
    command_configure,
    command_recall,
    flush_pending,
    project_id_for_cwd,
    request_user_profile,
    save_client_profile,
    setup_reminder,
)


class MemoryHookTest(unittest.TestCase):
    @staticmethod
    def profile(user_id="user-a", display_name="User A"):
        return UserProfile(user_id, display_name, "Long-lived test user")

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
            profile = self.profile()
            first = store.enqueue(profile, "codex", "session-1", str(root), transcript)
            second = store.enqueue(profile, "codex", "session-1", str(root), transcript)

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
            third = store.enqueue(profile, "codex", "session-1", str(root), transcript)
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
                transcript,
                "codex",
                "codex:session-1",
                str(root),
                root / "objects",
                self.profile(),
            )
            try:
                with gzip.open(snapshot.path, "rt", encoding="utf-8") as stored:
                    payload = json.load(stored)
                self.assertEqual(payload["schema_version"], "agent-session/2")
                self.assertEqual(payload["user"]["user_id"], "user-a")
                self.assertEqual(payload["user"]["display_name"], "User A")
                self.assertEqual(len(payload["messages"]), 10)
                self.assertEqual(payload["messages"][0]["content"], "message 3")
                markdown = payload["messages"][-1]["content"]
                self.assertIn("# Result", markdown)
                self.assertNotIn("secret = 1", markdown)
            finally:
                snapshot.path.unlink(missing_ok=True)

    def test_project_id_for_cwd_uses_work_root_folder_name_lowercased(self):
        self.assertEqual(
            project_id_for_cwd("D:\\Github\\Memory-Hub", "agent-history"), "memory-hub"
        )
        self.assertEqual(project_id_for_cwd("D:\\MainDev", "agent-history"), "maindev")
        self.assertEqual(
            project_id_for_cwd("D:\\Github\\ObsidianVault", "agent-history"),
            "obsidianvault",
        )
        self.assertEqual(project_id_for_cwd("/home/sun/My App", "agent-history"), "my-app")
        self.assertEqual(project_id_for_cwd("", "agent-history"), "agent-history")

    def test_upload_uses_job_project_and_source_agent(self):
        # 归档归属跟随 job：project 取捕获时的工作目录名，agent 取捕获来源，
        # 不随当前进程 config（默认 claude-code-mac / agent-history）漂移。
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "hi"}}),
                encoding="utf-8",
            )
            config = Config(
                hub_url="http://memory.test",
                default_user_id="user-a",
                agent_id="claude-code-mac",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=root / "state",
            )
            store = StateStore(config)
            store.enqueue(
                self.profile(), "pi", "session-1", str(root), transcript, "memory-hub"
            )
            job = store.queued(1)[0]
            client = HubClient(config)
            calls = []

            def fake_request(method, path, project_id, user_id, **kwargs):
                calls.append((method, path, project_id, user_id, kwargs))
                if method == "GET" and path.startswith("/v1/sessions/"):
                    return None if kwargs.get("allow_404") else {}
                if path == "/v1/files/uploads":
                    return {"upload_id": "u-1", "file_id": "f-1"}
                if path.startswith("/v1/files/"):
                    return {"status": "available"}
                if method == "PUT" and path.endswith("/versions"):
                    return {"version": 1}
                if path == "/v1/memories":
                    return {"memory_id": "m-1", "status": "dry_run"}
                return {}

            client.request = fake_request
            result = client.upload_job(job)
            self.assertEqual(result["status"], "captured")
            self.assertTrue(calls)
            for _, _, project_id, _, kwargs in calls:
                self.assertEqual(project_id, "memory-hub")
                self.assertEqual(kwargs.get("agent_id"), "pi")
            memory_call = calls[-1]
            self.assertEqual(memory_call[4]["json_body"]["agent_id"], "pi")
            self.assertEqual(memory_call[4]["json_body"]["project_id"], "memory-hub")

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
            first = store.enqueue(
                self.profile("user-a", "User A"),
                "codex",
                "session-1",
                str(root),
                transcript,
            )
            second = store.enqueue(
                self.profile("user-b", "User B"),
                "codex",
                "session-1",
                str(root),
                transcript,
            )
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
            store.enqueue(
                self.profile("user-b", "User B"),
                "codex",
                "session-1",
                str(root),
                transcript,
            )
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
            # user_id 通过位置参数传入并体现在 X-User-Id 头，不再放在请求体。
            self.assertEqual(search_call[3], "user-b")
            self.assertNotIn("user_id", search_call[4]["json_body"])
            memory_call = calls[1]
            self.assertEqual(memory_call[3], "user-b")
            self.assertEqual(memory_call[4]["json_body"]["scope_type"], "project")
            self.assertNotIn("user_id", memory_call[4]["json_body"])

    def test_environment_without_profile_falls_back_to_legacy_default_user(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"MEMORY_HOOK_STATE_DIR": directory}, clear=True
        ):
            config = Config.from_environment(cwd=directory)
            # 未配置身份时统一归属默认用户 sun（旧数据兼容）。
            self.assertEqual(config.default_user_id, "sun")
            self.assertTrue(config.configured)
            self.assertEqual(config.identity_source, "legacy-default")

    def test_team_current_member_precedes_local_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            nested = project / "src" / "feature"
            team_dir = project / ".team"
            team_dir.mkdir(parents=True)
            nested.mkdir(parents=True)
            (team_dir / "settings.local.json").write_text(
                json.dumps({"currentMember": "team-user"}), encoding="utf-8"
            )
            state_dir = root / "state"
            save_client_profile(
                state_dir,
                UserProfile("profile-user", "Profile User", "Stored profile"),
            )
            with patch.dict(
                os.environ, {"MEMORY_HOOK_STATE_DIR": str(state_dir)}, clear=True
            ):
                config = Config.from_environment(cwd=str(nested))
            self.assertEqual(config.default_user_id, "team-user")
            self.assertEqual(config.identity_source, "team")
            # 指定 user_id 即视为就绪（多用户按 user_id 区分）。
            self.assertTrue(config.configured)

    def test_environment_user_precedes_team_current_member(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            team_dir = root / ".team"
            team_dir.mkdir()
            (team_dir / "settings.local.json").write_text(
                json.dumps({"currentMember": "team-user"}), encoding="utf-8"
            )
            environment = {
                "MEMORY_HOOK_STATE_DIR": str(root / "state"),
                "MEMORY_HUB_CLIENT_USER_ID": "environment-user",
            }
            with patch.dict(os.environ, environment, clear=True):
                config = Config.from_environment(cwd=str(root))
            self.assertEqual(config.default_user_id, "environment-user")
            self.assertEqual(config.identity_source, "environment")
            # 环境身份只携带 user_id；display_name/summary 仅来自本机 profile。
            self.assertEqual(config.display_name, "")
            self.assertEqual(config.profile_summary, "")
            self.assertTrue(config.configured)

    def test_team_current_member_reuses_matching_stored_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            team_dir = root / ".team"
            team_dir.mkdir()
            (team_dir / "settings.local.json").write_text(
                json.dumps({"currentMember": "team-user"}), encoding="utf-8"
            )
            state_dir = root / "state"
            save_client_profile(
                state_dir,
                UserProfile("team-user", "Team User", "Matching stored profile"),
            )
            with patch.dict(
                os.environ, {"MEMORY_HOOK_STATE_DIR": str(state_dir)}, clear=True
            ):
                config = Config.from_environment(cwd=str(root))
            self.assertEqual(config.identity_source, "team")
            self.assertEqual(config.display_name, "Team User")
            self.assertTrue(config.configured)

    def test_hook_cwd_team_member_precedes_profile_loaded_elsewhere(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            team_dir = root / ".team"
            team_dir.mkdir()
            (team_dir / "settings.local.json").write_text(
                json.dumps({"currentMember": "team-user"}), encoding="utf-8"
            )
            config = Config(
                hub_url="http://memory.test",
                default_user_id="profile-user",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=root / "state",
                display_name="Profile User",
                profile_summary="Stored profile",
                identity_source="profile",
            )
            profile = request_user_profile(config, {"cwd": str(root)})
            self.assertEqual(profile.user_id, "team-user")
            # 未提供显示名/概要时回退为 user_id 本身。
            self.assertEqual(profile.display_name, "team-user")
            self.assertEqual(profile.summary, "")
            self.assertIn(
                "configure --user-id team-user", setup_reminder(config, profile)
            )

    def test_explicit_user_can_supply_a_complete_request_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(
                hub_url="http://memory.test",
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=Path(directory),
                display_name="User A",
                profile_summary="Default user",
            )
            profile = request_user_profile(
                config,
                explicit_user_id="user-b",
                explicit_display_name="User B",
                explicit_summary="Second request user",
            )
            self.assertEqual(
                profile, UserProfile("user-b", "User B", "Second request user")
            )

    def test_first_recall_prompts_for_identity_without_contacting_hub(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(
                hub_url="http://memory.test",
                default_user_id=None,
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=Path(directory),
            )
            args = SimpleNamespace(user_id=None, limit=8, max_chars=6000)
            hook = {"hook_event_name": "SessionStart", "cwd": directory}
            stdout = io.StringIO()
            with patch("sys.stdin", io.StringIO(json.dumps(hook))), patch(
                "sys.stdout", stdout
            ), patch.object(
                HubClient,
                "search",
                side_effect=AssertionError("unconfigured recall must not search"),
            ):
                self.assertEqual(command_recall(args, config), 0)
            output = json.loads(stdout.getvalue())
            context = output["hookSpecificOutput"]["additionalContext"]
            self.assertEqual(
                output["hookSpecificOutput"]["hookEventName"], "SessionStart"
            )
            self.assertIn("尚未完成用户身份配置", context)
            self.assertIn("configure --user-id <user-id>", context)
            self.assertIn("不要替用户臆造", context)

    def test_unconfigured_capture_stays_local_until_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "remember"}}),
                encoding="utf-8",
            )
            config = Config(
                hub_url="http://127.0.0.1:1",
                default_user_id=None,
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=0.1,
                state_dir=root / "state",
            )
            store = StateStore(config)
            args = SimpleNamespace(
                user_id=None, source="codex", flush_limit=10, verbose=False
            )
            hook = {
                "session_id": "session-1",
                "transcript_path": str(transcript),
                "cwd": str(root),
            }
            with patch("sys.stdin", io.StringIO(json.dumps(hook))):
                self.assertEqual(command_capture(args, config, store), 0)
            self.assertEqual(store.status()["unconfigured_jobs"], 1)
            self.assertEqual(store.queued(10), [])
            self.assertEqual(
                flush_pending(store, config, 10),
                {"busy": False, "completed": 0, "failed": 0},
            )
            with store.connect() as connection:
                row = connection.execute("SELECT * FROM jobs").fetchone()
            self.assertEqual(row["user_id"], UNCONFIGURED_USER_ID)
            with gzip.open(row["snapshot_path"], "rt", encoding="utf-8") as stored:
                self.assertIsNone(json.load(stored)["user"])

    def test_configure_persists_profile_and_claims_local_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "remember"}}),
                encoding="utf-8",
            )
            config = Config(
                hub_url="http://memory.test",
                default_user_id=None,
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=root / "state",
            )
            store = StateStore(config)
            store.enqueue(
                UserProfile(UNCONFIGURED_USER_ID),
                "codex",
                "session-1",
                str(root),
                transcript,
            )
            args = SimpleNamespace(
                user_id="jane-123",
                display_name="Jane Smith",
                summary="Prefers concise technical answers",
                flush_limit=0,
            )
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                self.assertEqual(command_configure(args, config), 0)
            output = json.loads(stdout.getvalue())
            self.assertTrue(output["configured"])
            self.assertEqual(output["assigned_jobs"], 1)
            profile_path = Path(output["profile_path"])
            self.assertEqual(stat.S_IMODE(profile_path.stat().st_mode), 0o600)
            with patch.dict(
                os.environ, {"MEMORY_HOOK_STATE_DIR": str(config.state_dir)}, clear=True
            ):
                reloaded = Config.from_environment(cwd=str(root))
            self.assertTrue(reloaded.configured)
            self.assertEqual(reloaded.default_user_id, "jane-123")
            self.assertEqual(reloaded.display_name, "Jane Smith")
            claimed = StateStore(reloaded).queued(10)
            self.assertEqual(len(claimed), 1)
            self.assertEqual(claimed[0]["user_id"], "jane-123")


if __name__ == "__main__":
    unittest.main()

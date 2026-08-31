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
    HubError,
    StateStore,
    UNCONFIGURED_USER_ID,
    UserProfile,
    build_snapshot,
    classify_snapshot,
    command_capture,
    command_configure,
    command_recall,
    command_search,
    flush_pending,
    format_context,
    head_tail_sample,
    load_session_texts,
    pi_memory_draft_path,
    project_id_for_cwd,
    read_hook_input,
    request_user_profile,
    save_client_profile,
    session_user_texts,
    setup_reminder,
    strip_skill_wrapper,
    transcript_tail_interrupted,
)


class MemoryHookTest(unittest.TestCase):
    @staticmethod
    def profile(user_id="user-a", display_name="User A"):
        return UserProfile(user_id, display_name, "Long-lived test user")

    def test_online_search_uses_two_minute_timeout_and_exposes_frontend_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(
                hub_url="http://memory.test",
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=8,
                state_dir=Path(directory),
            )
            seen = []

            def fake_search_response(client, query, project_id, limit, user_id):
                seen.append(client.config.timeout_seconds)
                return {
                    "facts": [{"summary": "历史决策", "text": "先小范围验证。"}],
                    "retrieval": {
                        "retrieval_id": "r1",
                        "query_hash": "a" * 64,
                        "policy_version": "v2-fts-top3-llm",
                    },
                    "quality": {"mode": "llm", "candidates": 3, "kept": 1},
                }

            args = SimpleNamespace(
                query="过去怎么决定的",
                project="maindev",
                limit=3,
                max_chars=4000,
                json=True,
                source="pi",
                user_id=None,
                display_name=None,
                summary=None,
            )
            stdout = io.StringIO()
            with patch("memory_hook.request_user_profile", return_value=self.profile()), patch.object(
                HubClient, "search_response", fake_search_response
            ), patch("sys.stdout", stdout):
                self.assertEqual(command_search(args, config), 0)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(seen, [120.0])
            self.assertEqual(payload["project_id"], "maindev")
            self.assertEqual(payload["quality"]["kept"], 1)
            self.assertIn("先小范围验证", payload["context"])

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

    def test_status_explains_terminal_failed_jobs(self):
        # StateStore 旧方法大量使用 sqlite context manager（只 commit 不 close），
        # Windows 测试进程退出前可能仍持数据库句柄；这里关注返回契约而非临时文件清理。
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "remember"}}),
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
            enqueued = store.enqueue(
                self.profile(), "pi", "failed-session", str(root), transcript
            )
            connection = store.connect()
            try:
                connection.execute(
                    "UPDATE jobs SET state='failed', last_error=?, updated_at=? WHERE job_id=?",
                    ("manual drop for validation", 1234.5, enqueued["job_id"]),
                )
                connection.commit()
            finally:
                connection.close()

            status = store.status()
            self.assertEqual(status["counts"], {"failed": 1})
            self.assertEqual(
                status["terminal_failed"],
                {
                    "count": 1,
                    "latest_failed_at": 1234.5,
                    "latest_error": "manual drop for validation",
                },
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
                full_session={"object_name": "codex/session.jsonl", "content_sha256": "ab" * 32},
            )
            try:
                with gzip.open(snapshot.path, "rt", encoding="utf-8") as stored:
                    payload = json.load(stored)
                self.assertEqual(payload["schema_version"], "agent-session/3")
                self.assertEqual(payload["user"]["user_id"], "user-a")
                self.assertEqual(payload["user"]["display_name"], "User A")
                self.assertEqual(len(payload["messages"]), 10)
                self.assertEqual(payload["messages"][0]["content"], "message 3")
                markdown = payload["messages"][-1]["content"]
                self.assertIn("# Result", markdown)
                self.assertNotIn("secret = 1", markdown)
                # 双资产：快照内嵌完整 session 文件指针，不携带 events
                self.assertNotIn("events", payload)
                self.assertEqual(
                    payload["full_session"],
                    {"object_name": "codex/session.jsonl", "content_sha256": "ab" * 32},
                )
            finally:
                snapshot.path.unlink(missing_ok=True)

    def test_project_id_for_cwd_uses_work_root_folder_name_lowercased(self):
        # 隔离 state dir（空临时目录）：本机 project 覆盖与别名都会影响派生，
        # 测试纯 cwd 派生时必须排除这两者，保证跨机器确定性。
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"MEMORY_HOOK_STATE_DIR": directory}, clear=True
        ):
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

    def test_machine_project_overrides_cwd_derivation(self):
        # 本机级 project 别名一旦写入 state dir/project-aliases.local.json，
        # 覆盖共享模板的 cwd 派生（"*" 为 catch-all），与其他机器的项目完全隔离。
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"MEMORY_HOOK_STATE_DIR": directory}, clear=True
        ):
            self.assertEqual(
                project_id_for_cwd("/work/maindev", "agent-history"), "maindev"
            )
            (Path(directory) / "project-aliases.local.json").write_text(
                json.dumps({"aliases": {"*": "nas"}}), encoding="utf-8"
            )
            self.assertEqual(project_id_for_cwd("/work/maindev", "agent-history"), "nas")
            self.assertEqual(project_id_for_cwd("/work/whatever", "agent-history"), "nas")

    def test_local_project_aliases_specific_entry_wins_over_catch_all(self):
        # 本机映射是字典：具体条目优先，未命中才落到 "*" catch-all。
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"MEMORY_HOOK_STATE_DIR": directory}, clear=True
        ):
            (Path(directory) / "project-aliases.local.json").write_text(
                json.dumps({"aliases": {"memory-hub": "memory-hub", "*": "nas"}}),
                encoding="utf-8",
            )
            self.assertEqual(
                project_id_for_cwd("/work/memory-hub", "agent-history"), "memory-hub"
            )
            self.assertEqual(project_id_for_cwd("/work/other", "agent-history"), "nas")

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

    def test_upload_sends_full_file_and_snapshot_with_pointer(self):
        # 双资产（ADR-009）：enqueue 时构建 full 包 + 快照；upload 时先传 full
        # （命名对象覆盖写）再传快照（CAS），commit 关联 full_file_id。
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "2026-08-18T00-00-00-000Z_abc-123.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "session", "version": 3, "id": "abc-123"}),
                        json.dumps({"type": "message", "message": {"role": "user", "content": "帮我修复登录接口的鉴权问题，token 过期后没有自动刷新"}}),
                        json.dumps({"type": "message", "message": {"role": "assistant", "content": "已在 refresh 拦截器里补上重试逻辑，并加了回归测试"}}),
                    ]
                ),
                encoding="utf-8",
            )
            config = Config(
                hub_url="http://memory.test",
                default_user_id="user-a",
                agent_id="pi",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=root / "state",
            )
            store = StateStore(config)
            store.enqueue(
                self.profile(), "pi", "abc-123", str(root), transcript, "maindev"
            )
            job = store.queued(1)[0]
            # spool 里固化了 full 副本
            self.assertTrue(job["full_path"])
            self.assertTrue(Path(job["full_path"]).is_file())

            client = HubClient(config)
            uploads = []

            def fake_request(method, path, project_id, user_id, **kwargs):
                if method == "GET" and path.startswith("/v1/sessions/"):
                    return None if kwargs.get("allow_404") else {}
                if path == "/v1/files/uploads":
                    body = kwargs.get("json_body") or {}
                    uploads.append(body)
                    return {"upload_id": "u-%d" % len(uploads), "file_id": "f-%d" % len(uploads)}
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
            self.assertEqual(result["full_file_id"], "f-1")
            # 两次上传：full（带 object_name）在前，快照（CAS）在后
            self.assertEqual(len(uploads), 2)
            self.assertEqual(uploads[0]["object_name"], "pi/2026-08-18T00-00-00-000Z_abc-123.jsonl")
            self.assertNotIn("object_name", uploads[1])
            # 快照 /3 内嵌指针指向 full 的内容 sha
            import gzip as _gzip
            snapshot_payload = json.loads(
                _gzip.decompress(Path(job["snapshot_path"]).read_bytes()).decode("utf-8")
            )
            self.assertEqual(snapshot_payload["schema_version"], "agent-session/3")
            self.assertEqual(
                snapshot_payload["full_session"]["object_name"],
                "pi/2026-08-18T00-00-00-000Z_abc-123.jsonl",
            )
            self.assertEqual(
                snapshot_payload["full_session"]["content_sha256"], job["full_sha256"]
            )
            self.assertNotIn("events", snapshot_payload)
            # 完整包携带全量 events（含 session 元事件）
            full_payload = json.loads(
                _gzip.decompress(Path(job["full_path"]).read_bytes()).decode("utf-8")
            )
            self.assertEqual(full_payload["schema_version"], "agent-session-full/1")
            self.assertEqual(full_payload["event_count"], 3)
            self.assertEqual(full_payload["source"]["format"], "jsonl")

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
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
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
                if path == "/v1/memories/search-v2":
                    return {"results": []}
                return {"memory_id": "memory-1", "status": "pending"}

            client.request = fake_request
            self.assertEqual(client.search("query", "project-a", 5, "user-b"), [])
            client.ensure_memory(job, 1, "file-1")

            search_call = calls[0]
            # user_id 通过位置参数传入并体现在 X-User-Id 头，不再放在请求体。
            self.assertEqual(search_call[3], "user-b")
            self.assertEqual(search_call[1], "/v1/memories/search-v2")
            self.assertEqual(search_call[4]["json_body"]["schema_version"], "memory-search/2")
            self.assertEqual(search_call[4]["json_body"]["quality_mode"], "llm")
            self.assertNotIn("user_id", search_call[4]["json_body"])
            memory_call = calls[1]
            self.assertEqual(memory_call[3], "user-b")
            self.assertEqual(memory_call[4]["json_body"]["scope_type"], "project")
            self.assertNotIn("user_id", memory_call[4]["json_body"])

    def test_search_falls_back_to_v1_during_server_rollout(self):
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
            client = HubClient(config)
            paths = []

            def fake_request(method, path, project_id, user_id, **kwargs):
                paths.append(path)
                if path == "/v1/memories/search-v2":
                    raise HubError("HTTP 404: endpoint not found")
                return {"facts": [{"fact": "legacy exact fact"}]}

            client.request = fake_request
            self.assertEqual(
                client.search("query", "project-a", 5, "user-a"),
                [{"fact": "legacy exact fact"}],
            )
            self.assertEqual(paths, ["/v1/memories/search-v2", "/v1/memories/search"])

    def test_search_does_not_bypass_llm_gate_on_v2_failure(self):
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
            client = HubClient(config)
            paths = []

            def fake_request(method, path, project_id, user_id, **kwargs):
                paths.append(path)
                raise HubError("HTTP 503: RETRIEVAL_JUDGE_UNAVAILABLE")

            client.request = fake_request
            with self.assertRaises(HubError):
                client.search("query", "project-a", 5, "user-a")
            self.assertEqual(paths, ["/v1/memories/search-v2"])

    def test_search_response_exposes_retrieval_metadata(self):
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
            client = HubClient(config)
            client.request = lambda *args, **kwargs: {
                "results": [{"result_id": "memory-1", "text": "answer"}],
                "retrieval_id": "retrieval-1",
                "query_hash": "a" * 64,
                "policy_version": "v2-fts-top3-llm",
                "quality": {"mode": "llm", "candidates": 2, "kept": 1},
            }

            response = client.search_response("query", "project-a", 5, "user-a")

            self.assertEqual(response["facts"][0]["result_id"], "memory-1")
            self.assertEqual(response["retrieval"]["retrieval_id"], "retrieval-1")
            self.assertEqual(response["quality"]["kept"], 1)

    def test_feedback_v2_falls_back_to_v1_for_old_hub(self):
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
            client = HubClient(config)
            bodies = []

            def fake_request(method, path, project_id, user_id, **kwargs):
                body = kwargs["json_body"]
                bodies.append(body)
                if body["schema_version"] == "memory-feedback/2":
                    raise HubError("HTTP 400: unsupported schema")
                return {"accepted": True, "feedback_id": "feedback-1"}

            client.request = fake_request
            result = client.feedback(
                "memory-1",
                "irrelevant",
                "project-a",
                "user-a",
                session_id="session-1",
                retrieval_id="retrieval-1",
                query_hash="a" * 64,
                policy_version="v2-fts-top3",
                candidate_rank=2,
                rating=0,
            )

            self.assertTrue(result["accepted"])
            self.assertEqual(
                [body["schema_version"] for body in bodies],
                ["memory-feedback/2", "memory-feedback/1"],
            )
            self.assertEqual(bodies[0]["rating"], 0)
            self.assertEqual(bodies[1]["feedback_type"], "irrelevant")

    def _recall_args(self, source="claude"):
        return SimpleNamespace(
            source=source,
            user_id=None,
            display_name=None,
            summary=None,
            limit=6,
            max_chars=4000,
            timeout_seconds=120,
        )

    @staticmethod
    def _recall_payload(root, session_id="sess-1", prompt="怎么配置 recall 钩子"):
        return json.dumps(
            {
                "session_id": session_id,
                "cwd": str(root),
                "prompt": prompt,
                "hook_event_name": "UserPromptSubmit",
            }
        )

    def test_read_hook_input_decodes_utf8_bytes_with_chinese(self):
        # 真实 hook 经管道写入 UTF-8 字节；Windows 上 sys.stdin 默认本地代码页，
        # 中文 prompt 必须按 UTF-8 显式解码，否则 read_hook_input 返回 {}。
        payload = json.dumps(
            {"session_id": "s-utf8", "cwd": "D:/x", "prompt": "显式关闭 thinking"}
        ).encode("utf-8")

        class FakeStdin:
            def __init__(self, data):
                self.buffer = io.BytesIO(data)

        with patch("sys.stdin", FakeStdin(payload)):
            hook = read_hook_input()
        self.assertEqual(hook.get("prompt"), "显式关闭 thinking")

    def test_recall_injects_on_first_prompt_and_dedupes_session(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            config = Config(
                hub_url="http://memory.test",
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=root / "state",
            )
            fact = {
                "source_type": "memory_document",
                "summary": "recall 配置方法",
                "text": "在 UserPromptSubmit 挂 recall 子命令。",
                "provenance": [
                    {"project_id": "memory-hub", "session_id": "s1", "memory_id": "m1"}
                ],
            }
            calls = []

            def fake_search_response(self_client, query, project_id, limit, user_id):
                calls.append((query, project_id, limit, user_id))
                return {
                    "facts": [fact],
                    "retrieval": {"retrieval_id": "r1"},
                    "quality": {"mode": "llm", "candidates": 3, "kept": 1},
                }

            with patch.object(HubClient, "search_response", fake_search_response):
                stdout = io.StringIO()
                with patch("sys.stdin", io.StringIO(self._recall_payload(root))), patch(
                    "sys.stdout", stdout
                ):
                    self.assertEqual(command_recall(self._recall_args(), config), 0)
                first = stdout.getvalue()
                self.assertIn("自动首轮预热", first)
                self.assertIn("LLM 审核通过 1/3 条历史记忆", first)
                self.assertIn("recall 配置方法", first)
                self.assertEqual(len(calls), 1)
                query, project_id, limit, user_id = calls[0]
                self.assertIn(root.name, query)
                self.assertIn("怎么配置 recall 钩子", query)
                self.assertEqual(limit, 6)
                self.assertEqual(user_id, "user-a")
                # 同 session 第二个 prompt：不再查询、不再注入。
                stdout2 = io.StringIO()
                with patch("sys.stdin", io.StringIO(self._recall_payload(root))), patch(
                    "sys.stdout", stdout2
                ):
                    self.assertEqual(command_recall(self._recall_args(), config), 0)
                self.assertEqual(stdout2.getvalue(), "")
                self.assertEqual(len(calls), 1)

    def test_recall_disabled_env_skips_before_marker(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            config = Config(
                hub_url="http://memory.test",
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=root / "state",
            )
            stdout = io.StringIO()
            with patch.dict(os.environ, {"MEMORY_HOOK_RECALL": "0"}), patch(
                "sys.stdin", io.StringIO(self._recall_payload(root))
            ), patch("sys.stdout", stdout):
                self.assertEqual(command_recall(self._recall_args(), config), 0)
            self.assertEqual(stdout.getvalue(), "")
            # disabled 不登记 marker：恢复后首个 prompt 仍会召回。
            self.assertFalse((root / "state" / "recall-markers").exists())

    def test_recall_hub_error_fails_open_silently(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            config = Config(
                hub_url="http://memory.test",
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=root / "state",
            )

            def failing_search(self_client, query, project_id, limit, user_id):
                raise HubError("HTTP 503: GRAPHITI_UNAVAILABLE")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.object(HubClient, "search_response", failing_search), patch(
                "sys.stdin", io.StringIO(self._recall_payload(root))
            ), patch("sys.stdout", stdout), patch("sys.stderr", stderr):
                # 恒 exit 0：非零会阻塞 UserPromptSubmit。
                self.assertEqual(command_recall(self._recall_args(), config), 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("GRAPHITI_UNAVAILABLE", stderr.getvalue())
            # 失败也登记 marker，同 session 后续 prompt 不重试。
            markers = list((root / "state" / "recall-markers").iterdir())
            self.assertEqual(len(markers), 1)

    def test_recall_short_prompt_falls_back_to_topics(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            config = Config(
                hub_url="http://memory.test",
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=1,
                state_dir=root / "state",
            )
            calls = []

            def fake_search_response(self_client, query, project_id, limit, user_id):
                calls.append(query)
                return {"facts": [], "retrieval": None, "quality": {"candidates": 0, "kept": 0}}

            with patch.object(HubClient, "search_response", fake_search_response):
                stdout = io.StringIO()
                with patch(
                    "sys.stdin",
                    io.StringIO(self._recall_payload(root, session_id="sess-2", prompt="hi")),
                ), patch("sys.stdout", stdout):
                    self.assertEqual(command_recall(self._recall_args(), config), 0)
                self.assertEqual(stdout.getvalue(), "")  # 空结果不注入
                self.assertEqual(len(calls), 1)
                self.assertIn("项目概况", calls[0])
                self.assertIn(root.name, calls[0])

    def test_format_context_exposes_structured_provenance_with_bounded_text(self):
        output = format_context(
            [
                {
                    "source_type": "memory_document",
                    "summary": "DT 静态网格同步",
                    "text": "删除 10 条，最终 214 行。",
                    "provenance": [
                        {
                            "project_id": "maindev",
                            "session_id": "pi:maindev:session-a",
                            "memory_id": "memory-a",
                        }
                    ],
                }
            ],
            2000,
        )
        self.assertIn("source=memory_document", output)
        self.assertIn("project=maindev", output)
        self.assertIn("session=pi:maindev:session-a", output)
        self.assertIn("摘要：DT 静态网格同步", output)
        self.assertIn("删除 10 条，最终 214 行", output)

    def test_strip_skill_wrapper_recovers_real_user_text(self):
        wrapped = (
            '<skill name="memory-hub" location="x">\n整份 SKILL.md 模板内容\n</skill>\n\n'
            "check & install"
        )
        self.assertEqual(strip_skill_wrapper(wrapped), "check & install")
        self.assertEqual(strip_skill_wrapper("普通消息"), "普通消息")
        self.assertEqual(strip_skill_wrapper('<skill name="x">只有模板</skill>'), "")

    def test_head_tail_sample_keeps_goal_and_tail(self):
        seq = ["msg-%d" % i for i in range(12)]
        self.assertEqual(
            head_tail_sample(seq),
            ["msg-0", "msg-1", "msg-2", "msg-3", "msg-8", "msg-9", "msg-10", "msg-11"],
        )
        self.assertEqual(head_tail_sample(["a", "b"]), ["a", "b"])

    def test_classify_snapshot_uses_whole_session_not_tail(self):
        # 整会话判定：结尾的「commit」不能盖掉前段的真实任务。
        with tempfile.TemporaryDirectory() as directory:
            config = Config(
                hub_url="http://127.0.0.1:1",
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=0.1,
                state_dir=Path(directory) / "state",
            )
            user_texts = ["帮我排查并修复内存泄漏", "再补个回归测试", "commit"]
            captured = {}

            def fake_llm(texts, last_assistant):
                captured["texts"] = list(texts)
                return {"title": "修复内存泄漏", "meaningful": True}

            with patch("memory_hook.llm_classify_session", fake_llm):
                title, meaningful = classify_snapshot(
                    config, "sha-whole-1", user_texts, "已提交。"
                )
            self.assertTrue(meaningful)
            self.assertEqual(title, "修复内存泄漏")
            # LLM 必须拿到整个会话的用户消息，而不是只有尾部一条。
            self.assertEqual(captured["texts"], user_texts)

            # LLM 不可用时启发式同样基于整会话：标题取首个非噪声消息（目标），
            # 而不是尾部例行消息。
            with patch.dict(os.environ, {"MEMORY_HUB_TITLE_LLM": "0"}):
                title, meaningful = classify_snapshot(
                    config, "sha-whole-2", user_texts, "已提交。"
                )
            self.assertTrue(meaningful)
            self.assertEqual(title, "帮我排查并修复内存泄漏")

    def test_ensure_memory_distilled_keeps_first_user_goal(self):
        # 用户目标必须保留：取整会话首个真实用户消息（skill 包装剥离），
        # 尾部「commit」只能进「最近用户目标」。
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                "\n".join(
                    json.dumps(event)
                    for event in (
                        {
                            "type": "user",
                            "message": {
                                "content": '<skill name="x" location="l">模板</skill>\n\n帮我排查并修复内存泄漏'
                            },
                        },
                        {"type": "assistant", "message": {"content": "已定位并修复。"}},
                        {"type": "user", "message": {"content": "commit"}},
                        {"type": "assistant", "message": {"content": "已提交。"}},
                    )
                ),
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
            store.enqueue(self.profile(), "pi", "session-goal", str(root), transcript)
            job = store.queued(1)[0]
            # 整会话文本从 full 包重取：首条目标必须在，尽管它是 10 条窗口外的旧消息也能取到。
            user_texts, first_user, last_user, last_assistant = load_session_texts(job)
            self.assertEqual(first_user, "帮我排查并修复内存泄漏")
            self.assertEqual(last_user, "commit")
            self.assertEqual(last_assistant, "已提交。")

            client = HubClient(config)
            calls = []

            def fake_request(method, path, project_id, user_id, **kwargs):
                calls.append(kwargs.get("json_body") or {})
                return {"memory_id": "memory-1", "status": "pending"}

            client.request = fake_request
            client.ensure_memory(job, 1, "file-1", "修复内存泄漏")
            distilled = calls[0]["distilled_content"]
            self.assertIn("首个用户目标：帮我排查并修复内存泄漏", distilled)
            self.assertIn("最近用户目标：commit", distilled)
            self.assertIn("会话结果：已提交。", distilled)

            draft_path = pi_memory_draft_path(config, job)
            self.assertTrue(draft_path.is_file())
            draft = draft_path.read_text(encoding="utf-8")
            self.assertIn("## 首个用户目标（提取源", draft)
            self.assertIn("帮我排查并修复内存泄漏", draft)
            self.assertIn("## 实际提交 Hub 的 distilled_content", draft)

    def test_pi_memory_draft_is_complete_and_exists_before_hub_post(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            goal_tail = "GOAL_TAIL_MUST_REMAIN_LOCAL"
            result_tail = "RESULT_TAIL_MUST_REMAIN_LOCAL"
            long_goal = "用户目标" + ("甲" * 800) + goal_tail
            long_result = "会话结果" + ("乙" * 1500) + result_tail
            transcript.write_text(
                "\n".join(
                    json.dumps(event, ensure_ascii=False)
                    for event in (
                        {"type": "user", "message": {"content": long_goal}},
                        {"type": "assistant", "message": {"content": long_result}},
                    )
                ),
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
                self.profile(), "pi", "session:with/windows-invalid", str(root), transcript,
                project_id="sample-project",
            )
            job = store.queued(1)[0]
            client = HubClient(config)
            observed = {}

            def fake_request(method, path, project_id, user_id, **kwargs):
                self.assertEqual(path, "/v1/memories")
                draft_path = pi_memory_draft_path(config, job)
                # 顺序门禁：request 被调用时，可读草稿必须已经完成原子落盘。
                self.assertTrue(draft_path.is_file())
                observed["draft"] = draft_path.read_text(encoding="utf-8")
                observed["outbound"] = kwargs["json_body"]["distilled_content"]
                return {"memory_id": "memory-1", "status": "pending"}

            client.request = fake_request
            result = client.ensure_memory(job, 3, "file-3", "长会话测试")

            self.assertEqual(result["memory_draft_path"], str(pi_memory_draft_path(config, job)))
            self.assertIn(goal_tail, observed["draft"])
            self.assertIn(result_tail, observed["draft"])
            self.assertNotIn(goal_tail, observed["outbound"])
            self.assertNotIn(result_tail, observed["outbound"])
            self.assertNotIn(":", pi_memory_draft_path(config, job).name)

            request_called = False

            def must_not_request(*args, **kwargs):
                nonlocal request_called
                request_called = True
                return {"memory_id": "unexpected", "status": "pending"}

            client.request = must_not_request
            with patch("memory_hook.write_pi_memory_draft", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    client.ensure_memory(job, 4, "file-4", "落盘失败门禁")
            self.assertFalse(request_called)

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
                {"busy": False, "completed": 0, "failed": 0, "recovered": 0},
            )
            with store.connect() as connection:
                row = connection.execute("SELECT * FROM jobs").fetchone()
            self.assertEqual(row["user_id"], UNCONFIGURED_USER_ID)
            with gzip.open(row["snapshot_path"], "rt", encoding="utf-8") as stored:
                self.assertIsNone(json.load(stored)["user"])

    def test_capture_skips_when_skip_env_set(self):
        # MEMORY_HUB_SKIP_CAPTURE=1（auto-skill extraction 子 session 等 opt-out
        # 场景）→ capture 直接返回，不入队任何 job。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "remember"}}),
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
            args = SimpleNamespace(
                user_id=None, source="pi", flush_limit=10, verbose=False
            )
            with patch.dict(os.environ, {"MEMORY_HUB_SKIP_CAPTURE": "1"}):
                self.assertEqual(command_capture(args, config, store), 0)
            self.assertEqual(store.status()["counts"], {})
            self.assertEqual(store.status()["unconfigured_jobs"], 0)

    def test_capture_skips_extraction_subsession_transcript(self):
        # env 标记失效时的兜底：首条 user 消息以 extraction 签名开头 → 跳过。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "content": "You are the Skill extraction sub-agent. Analyze the ~5 messages above."
                        },
                    }
                )
                + "\n"
                + json.dumps(
                    {"type": "assistant", "message": {"content": "done"}}
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
            args = SimpleNamespace(
                user_id=None, source="pi", flush_limit=10, verbose=False
            )
            hook = {
                "session_id": "session-1",
                "transcript_path": str(transcript),
                "cwd": str(root),
            }
            with patch("sys.stdin", io.StringIO(json.dumps(hook))):
                with patch.dict(os.environ) as env:
                    env.pop("MEMORY_HUB_SKIP_CAPTURE", None)
                    self.assertEqual(command_capture(args, config, store), 0)
            self.assertEqual(store.status()["counts"], {})
            self.assertEqual(store.status()["unconfigured_jobs"], 0)

    def test_capture_keeps_session_that_only_quotes_extraction_prompt(self):
        # 首条消息是真实提问、后续消息才出现签名（如开发 auto-skill 本身的会话）
        # → 不属于 extraction 子 session，必须正常归档。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps(
                    {"type": "user", "message": {"content": "优化 extractPrompt.ts"}}
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": "首行是 You are the Skill extraction sub-agent. ..."
                        },
                    }
                ),
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
                user_id=None, source="pi", flush_limit=10, verbose=False
            )
            hook = {
                "session_id": "session-1",
                "transcript_path": str(transcript),
                "cwd": str(root),
            }
            with patch("sys.stdin", io.StringIO(json.dumps(hook))):
                with patch.dict(os.environ) as env:
                    env.pop("MEMORY_HUB_SKIP_CAPTURE", None)
                    self.assertEqual(command_capture(args, config, store), 0)
            self.assertEqual(store.status()["unconfigured_jobs"], 1)

    def test_capture_skips_stop_with_interrupted_tail(self):
        # Esc 中断触发的 Stop：transcript 尾部最新消息是中断标记（其后还可能有
        # file-history-snapshot 等非消息记录）→ 不入队不上传。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "user",
                                "message": {
                                    "role": "user",
                                    "content": [{"type": "text", "text": "做点什么"}],
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "assistant",
                                "message": {
                                    "role": "assistant",
                                    "content": [{"type": "text", "text": "半成品输出"}],
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "user",
                                "message": {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": "[Request interrupted by user]"}
                                    ],
                                },
                            }
                        ),
                        json.dumps({"type": "file-history-snapshot", "messageId": "x"}),
                    ]
                ),
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
                user_id=None, source="claude", flush_limit=10, verbose=False
            )
            hook = {
                "hook_event_name": "Stop",
                "session_id": "session-1",
                "transcript_path": str(transcript),
                "cwd": str(root),
            }
            with patch("sys.stdin", io.StringIO(json.dumps(hook))):
                with patch.dict(os.environ) as env:
                    env.pop("MEMORY_HUB_SKIP_CAPTURE", None)
                    self.assertEqual(command_capture(args, config, store), 0)
            self.assertEqual(store.status()["counts"], {})
            self.assertEqual(store.status()["unconfigured_jobs"], 0)

    def test_capture_session_end_archives_despite_interrupted_tail(self):
        # 同样的中断尾部，但由 SessionEnd 触发 → 最终快照必须归档（幂等），不跳过。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "user",
                                "message": {
                                    "role": "user",
                                    "content": [{"type": "text", "text": "做点什么"}],
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "user",
                                "message": {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": "[Request interrupted by user]"}
                                    ],
                                },
                            }
                        ),
                    ]
                ),
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
                user_id=None, source="claude", flush_limit=10, verbose=False
            )
            hook = {
                "hook_event_name": "SessionEnd",
                "session_id": "session-1",
                "transcript_path": str(transcript),
                "cwd": str(root),
            }
            with patch("sys.stdin", io.StringIO(json.dumps(hook))):
                with patch.dict(os.environ) as env:
                    env.pop("MEMORY_HUB_SKIP_CAPTURE", None)
                    self.assertEqual(command_capture(args, config, store), 0)
            self.assertEqual(store.status()["unconfigured_jobs"], 1)

    def test_capture_stop_with_normal_tail_still_captures(self):
        # Stop 事件但尾部是正常 assistant 消息 → 不受影响，正常入队。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "user",
                                "message": {
                                    "role": "user",
                                    "content": [{"type": "text", "text": "提问"}],
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "assistant",
                                "message": {
                                    "role": "assistant",
                                    "content": [{"type": "text", "text": "完整回答"}],
                                },
                            }
                        ),
                    ]
                ),
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
                user_id=None, source="claude", flush_limit=10, verbose=False
            )
            hook = {
                "hook_event_name": "Stop",
                "session_id": "session-1",
                "transcript_path": str(transcript),
                "cwd": str(root),
            }
            with patch("sys.stdin", io.StringIO(json.dumps(hook))):
                with patch.dict(os.environ) as env:
                    env.pop("MEMORY_HUB_SKIP_CAPTURE", None)
                    self.assertEqual(command_capture(args, config, store), 0)
            self.assertEqual(store.status()["unconfigured_jobs"], 1)

    def test_transcript_tail_interrupted_marker_variants(self):
        # 标记变体（for tool use）/ 尾部无消息 / 文件缺失 的 fail-open 行为。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            variant = root / "variant.jsonl"
            variant.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "[Request interrupted by user for tool use]",
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(transcript_tail_interrupted(variant))
            empty = root / "empty.jsonl"
            empty.write_text("{\n", encoding="utf-8")
            self.assertFalse(transcript_tail_interrupted(empty))
            self.assertFalse(transcript_tail_interrupted(root / "missing.jsonl"))

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


    def test_capture_no_flush_json_strict_contract(self):
        # --no-flush --json：只入队不触网（hub 不可达也秒回 0），stdout 恒为一行
        # 机器可读结果；同内容重复 capture → already_present。
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "remember"}})
                + "\n",
                encoding="utf-8",
            )
            config = Config(
                hub_url="http://127.0.0.1:1",  # 不可达：若误 flush 会慢/失败
                default_user_id="user-a",
                agent_id="test-agent",
                archive_project_id="agent-history",
                api_key=None,
                timeout_seconds=0.1,
                state_dir=root / "state",
            )
            store = StateStore(config)
            args = SimpleNamespace(
                user_id=None, source="pi", flush_limit=10, verbose=False,
                no_flush=True, json=True,
            )
            hook = {
                "hook_event_name": "SessionEnd",
                "session_id": "session-1",
                "transcript_path": str(transcript),
                "cwd": str(root),
            }
            stdin = io.StringIO(json.dumps(hook))
            stdout = io.StringIO()
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
                self.assertEqual(command_capture(args, config, store), 0)
            first = json.loads(stdout.getvalue())
            self.assertEqual(first["result"], "enqueued")
            self.assertTrue(first["job_id"])
            self.assertTrue(first["sha256"])
            self.assertNotIn("flush", first)
            self.assertEqual(store.status()["counts"], {"queued": 1})

            stdin.seek(0)
            stdout = io.StringIO()
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
                self.assertEqual(command_capture(args, config, store), 0)
            second = json.loads(stdout.getvalue())
            self.assertEqual(second["result"], "already_present")
            self.assertEqual(store.status()["counts"], {"queued": 1})

            # 异常契约：enqueue 抛错 → exit 1 + result=error（不再静默 exit 0）。
            def boom(*_args, **_kwargs):
                raise RuntimeError("disk full")

            transcript.write_text(
                transcript.read_text(encoding="utf-8")
                + json.dumps({"type": "user", "message": {"content": "more"}}) + "\n",
                encoding="utf-8",
            )
            stdin.seek(0)
            stdout = io.StringIO()
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout), patch.object(
                store, "enqueue", boom
            ):
                self.assertEqual(command_capture(args, config, store), 1)
            self.assertEqual(json.loads(stdout.getvalue())["result"], "error")

    def test_capture_json_reports_skip_reasons(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
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
            args = SimpleNamespace(
                user_id=None, source="pi", flush_limit=10, verbose=False,
                no_flush=True, json=True,
            )

            def run(hook):
                stdout = io.StringIO()
                with patch("sys.stdin", io.StringIO(json.dumps(hook))), patch(
                    "sys.stdout", stdout
                ):
                    code = command_capture(args, config, store)
                return code, json.loads(stdout.getvalue())

            code, payload = run({"session_id": "s", "cwd": str(root)})
            self.assertEqual((code, payload["result"]), (0, "skipped_no_fields"))
            code, payload = run(
                {
                    "session_id": "s",
                    "transcript_path": str(root / "missing.jsonl"),
                    "cwd": str(root),
                }
            )
            self.assertEqual((code, payload["result"]), (0, "skipped_missing_file"))
            extraction = root / "extraction.jsonl"
            extraction.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "content": "You are the Skill extraction sub-agent. go"
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            code, payload = run(
                {
                    "session_id": "s",
                    "transcript_path": str(extraction),
                    "cwd": str(root),
                }
            )
            self.assertEqual((code, payload["result"]), (0, "skipped_extraction"))
            self.assertEqual(store.status()["counts"], {})

    def test_concurrent_enqueue_lock_prevents_reverse_supersede(self):
        # 并发回归（评审 C2）：A 持锁读到 v1 后停在构建阶段，transcript 长到 v2，
        # B 再 capture。有锁：B 等 A 完成后读到 v2 → 最终 queued 是 v2；
        # 无锁：A 后提交会把 B 的 v2 反向 supersede 并删对象（应失败）。
        import threading
        import time as _time

        import memory_hook

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "turn-1"}}) + "\n",
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
            args = SimpleNamespace(
                user_id=None, source="pi", flush_limit=0, verbose=False,
                no_flush=True, json=False,
            )
            hook = {
                "hook_event_name": "SessionEnd",
                "session_id": "s-1",
                "transcript_path": str(transcript),
                "cwd": str(root),
            }
            original_build = memory_hook.build_full_package
            first_entered = threading.Event()
            release_first = threading.Event()
            stalled: list = []

            def stalling_build(*f_args, **f_kwargs):
                if not stalled:
                    stalled.append(True)
                    first_entered.set()
                    release_first.wait(10)
                return original_build(*f_args, **f_kwargs)

            def capture():
                with patch("sys.stdin", io.StringIO(json.dumps(hook))):
                    command_capture(args, config, store)

            with patch.object(memory_hook, "build_full_package", stalling_build):
                thread_a = threading.Thread(target=capture)
                thread_a.start()
                self.assertTrue(first_entered.wait(5))
                transcript.write_text(
                    transcript.read_text(encoding="utf-8")
                    + json.dumps({"type": "user", "message": {"content": "turn-2"}})
                    + "\n",
                    encoding="utf-8",
                )
                thread_b = threading.Thread(target=capture)
                thread_b.start()
                _time.sleep(0.5)  # B 应阻塞在 enqueue 锁上
                release_first.set()
                thread_a.join(10)
                thread_b.join(10)
            self.assertFalse(thread_a.is_alive())
            self.assertFalse(thread_b.is_alive())
            rows = store.queued(10)
            self.assertEqual(len(rows), 1)
            with gzip.open(rows[0]["full_path"], "rt", encoding="utf-8") as stored:
                events = json.load(stored)["events"]
            self.assertEqual(
                len(events), 2, "最终 queued 必须是较新的 v2 快照（含 turn-2）"
            )

    def test_flush_claim_preserves_uploading_objects_under_concurrent_enqueue(self):
        # 评审 M4：uploading 的 job 在上传期间不得被并发 enqueue 的 supersede 删对象。
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "turn-1"}}) + "\n",
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
            store.enqueue(self.profile(), "pi", "s-1", str(root), transcript)
            claimed = store.claim_for_upload(10)
            self.assertEqual(len(claimed), 1)
            snapshot_path = claimed[0]["snapshot_path"]
            full_path = claimed[0]["full_path"]
            # 上传进行中，同 session 新快照入队：supersede 只碰 queued
            transcript.write_text(
                transcript.read_text(encoding="utf-8")
                + json.dumps({"type": "user", "message": {"content": "turn-2"}})
                + "\n",
                encoding="utf-8",
            )
            store.enqueue(self.profile(), "pi", "s-1", str(root), transcript)
            self.assertTrue(Path(snapshot_path).is_file())
            self.assertTrue(Path(full_path).is_file())
            self.assertEqual(
                store.status()["counts"], {"queued": 1, "uploading": 1}
            )
            store.complete(
                claimed[0]["job_id"], {"version": 1, "memory_id": "m-1"}
            )
            self.assertEqual(
                store.status()["counts"], {"completed": 1, "queued": 1}
            )
            self.assertFalse(Path(snapshot_path).exists())

    def test_stale_uploading_recovers_and_stale_complete_cannot_resurrect(self):
        # 崩溃回收：uploading 超租约 → queued 并可被重新认领；
        # 回收后被 supersede 的行不得被陈旧写者的 complete 复活。
        import time as _time

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "turn-1"}}) + "\n",
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
            store.enqueue(self.profile(), "pi", "s-1", str(root), transcript)
            job = store.queued(10)[0]
            claimed = store.claim_for_upload(10)
            self.assertEqual([row["job_id"] for row in claimed], [job["job_id"]])
            # 模拟持锁进程崩溃：updated_at 拨到租约之前
            with store.connect() as connection:
                connection.execute(
                    "UPDATE jobs SET updated_at=? WHERE job_id=?",
                    (_time.time() - 3600, job["job_id"]),
                )
            reclaimed = store.claim_for_upload(10)
            self.assertEqual([row["job_id"] for row in reclaimed], [job["job_id"]])
            # 复活防护：回收为 queued 后被新快照 supersede → complete 不再生效
            with store.connect() as connection:
                connection.execute(
                    "UPDATE jobs SET state='queued' WHERE job_id=?", (job["job_id"],)
                )
            transcript.write_text(
                transcript.read_text(encoding="utf-8")
                + json.dumps({"type": "user", "message": {"content": "turn-2"}})
                + "\n",
                encoding="utf-8",
            )
            store.enqueue(self.profile(), "pi", "s-1", str(root), transcript)
            store.complete(job["job_id"], {"version": 9, "memory_id": "m-x"})
            with store.connect() as connection:
                row = connection.execute(
                    "SELECT state, remote_version FROM jobs WHERE job_id=?",
                    (job["job_id"],),
                ).fetchone()
            self.assertEqual(row["state"], "superseded")
            self.assertIsNone(row["remote_version"])

    def test_fail_returns_job_to_queued_for_retry(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "turn-1"}}) + "\n",
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
            store.enqueue(self.profile(), "pi", "s-1", str(root), transcript)
            job = store.claim_for_upload(10)[0]
            store.fail(job["job_id"], Exception("boom"))
            self.assertEqual(store.status()["counts"], {"queued": 1})
            self.assertEqual(store.queued(10)[0]["attempts"], 1)

    def test_flush_recovers_fresh_claims_from_crashed_flush(self):
        # 评审修复：flush 进程刚认领（updated_at 很新）就崩溃，租约回收等 10 分钟；
        # flush.lock 在手即证明无其他 flush 存活 → 全量回收 uploading 后重新认领。
        import memory_hook

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "turn"}}) + "\n",
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
            store.enqueue(self.profile(), "pi", "s-1", str(root), transcript)
            store.enqueue(self.profile(), "pi", "s-2", str(root), transcript)
            # 模拟崩溃：认领后进程死亡，updated_at 新鲜（租约回收不会碰）
            claimed = store.claim_for_upload(10)
            self.assertEqual(len(claimed), 2)
            self.assertEqual(store.status()["counts"], {"uploading": 2})
            attempts = []

            def boom(_client, job):
                attempts.append(job["job_id"])
                raise RuntimeError("hub still down")

            with patch.object(memory_hook.HubClient, "upload_job", boom):
                result = flush_pending(store, config, 10)
            # 回收 2 个；重新认领后第 1 个上传失败即 break，未处理的归还 queued
            self.assertEqual(result["recovered"], 2)
            self.assertEqual(len(attempts), 1)
            self.assertEqual(store.status()["counts"], {"queued": 2})

    def test_flush_releases_unvisited_claims_on_failure(self):
        # 批量认领后首个上传失败即 break：未处理的认领必须归还 queued，
        # 不得留在 uploading 吃满整个租约（对后续 flush / supersede 不可见）。
        import memory_hook

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps({"type": "user", "message": {"content": "turn"}}) + "\n",
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
            store.enqueue(self.profile(), "pi", "s-1", str(root), transcript)
            store.enqueue(self.profile(), "pi", "s-2", str(root), transcript)

            def boom(_client, _job):
                raise RuntimeError("hub down")

            with patch.object(memory_hook.HubClient, "upload_job", boom):
                result = flush_pending(store, config, 10)
            self.assertEqual(result["failed"], 1)
            self.assertEqual(store.status()["counts"], {"queued": 2})


if __name__ == "__main__":
    unittest.main()

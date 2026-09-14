import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location("review_queue", Path(__file__).with_name("review_queue.py"))
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def detail(review_id="review-a"):
    return {
        "review_id": review_id,
        "memory_id": "memory-a",
        "project_id": "project-a",
        "group_id": "project:project-a",
        "scope_type": "project",
        "session_id": "session-a",
        "session_version": 3,
        "status": "review",
        "memory_status": "pending_extraction",
        "preview_attempts": 0,
        "updated_at": "2026-09-14T00:00:00Z",
        "snapshot_token": "opaque-A/+==",
        "distilled_content": "System knowledge and confirmed implementation evidence. " * 3,
        "novelty": {"status": "completed", "admission": "evolution"},
        "proposed": {
            "entities": [
                {"name": "project-a", "type": "Project", "summary": "Project A"},
                {"name": "rule-a", "type": "Convention", "summary": "Rule A"},
            ],
            "edges": [{"source": "rule-a", "name": "APPLIES_TO", "target": "project-a", "fact": "Confirmed rule."}],
        },
    }


def approval(review_id="review-a", mode="curated", token="opaque-A/+=="):
    return {"review_id": review_id, "content_mode": mode, "snapshot_token": token, "rationale": "checked evidence"}


def response(review_id="review-a", status="approved"):
    return 200, {"results": [{"review_id": review_id, "status": status}]}


class ReviewQueueTests(unittest.TestCase):
    def run_apply(self, decisions, client=None, dry_run=False):
        if client is None:
            client = Mock()
            client.post.return_value = response()
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.json"
            path.write_text(json.dumps(decisions), encoding="utf-8")
            args = SimpleNamespace(decisions=str(path), dry_run=dry_run)
            with patch.object(review, "make_client", return_value=client) as factory:
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    result = review.cmd_apply(args)
        return result, output.getvalue(), client, factory

    def run_scan(self, item):
        client = Mock()
        client.get.side_effect = [{"items": [{"review_id": item["review_id"]}]}, item]
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            with patch.object(review, "make_client", return_value=client), contextlib.redirect_stdout(output):
                result = review.cmd_scan(SimpleNamespace(output=str(path)))
            packet = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        return packet[0], output.getvalue(), client

    def test_scan_preserves_token_and_lifecycle_metadata(self):
        item = detail()
        item.update(status="preview_failed", preview_attempts=3, proposed=None)
        packet, output, client = self.run_scan(item)
        for key in ("memory_id", "session_id", "session_version", "scope_type", "group_id", "status",
                    "memory_status", "preview_attempts", "updated_at", "snapshot_token"):
            self.assertEqual(packet[key], item[key])
        self.assertIn("preview_failed/3", output)
        self.assertIn("preview_failed", {f["check"] for f in packet["flags"]})
        self.assertEqual(client.get.call_count, 2)
        client.post.assert_not_called()

    def test_scan_does_not_invent_missing_group_version_or_token(self):
        item = detail()
        for key in ("group_id", "session_version", "snapshot_token"):
            del item[key]
        packet, _, _ = self.run_scan(item)
        for key in ("group_id", "session_version", "snapshot_token"):
            self.assertIsNone(packet[key])
        self.assertFalse(packet["suggestion"]["auto"])
        self.assertIn("snapshot_missing", {f["check"] for f in packet["flags"]})

    def test_empty_preview_representations_have_same_flags(self):
        left, right = detail(), detail()
        left["proposed"], right["proposed"] = None, {}
        self.assertEqual(review.check_item(left), review.check_item(right))

    def test_scan_passes_server_token_unchanged_when_hints_differ(self):
        first = detail()
        second = copy.deepcopy(first)
        second["proposed"]["entities"][0]["suggested_canonical"] = "Project A"
        second["proposed"]["entity_resolution"] = {"resolution_status": "ok"}
        self.assertEqual(self.run_scan(first)[0]["snapshot_token"], self.run_scan(second)[0]["snapshot_token"])

    def test_preview_pending_is_not_an_auto_approval(self):
        item = detail()
        item["status"] = "preview_pending"
        flags = review.check_item(item)
        self.assertIn("preview_pending", {f["check"] for f in flags})
        self.assertFalse(review.suggest_decision(item, flags)["auto"])

    def test_missing_invalid_tokens_fail_before_any_request(self):
        for token in (None, "", "  ", 7, [], {}):
            for mode in ("original", "curated"):
                with self.subTest(token=token, mode=mode):
                    decisions = {
                        "removals": [{"review_id": "unrelated", "entities": ["wrong"]}],
                        "approvals": [approval(mode=mode, token=token)],
                    }
                    result, output, client, factory = self.run_apply(decisions)
                    self.assertEqual(result, 1)
                    self.assertIn("snapshot_token", output)
                    factory.assert_not_called()
                    client.get.assert_not_called()
                    client.post.assert_not_called()

    def test_legacy_approval_without_token_is_not_upgraded_automatically(self):
        item = approval()
        del item["snapshot_token"]
        result, _, client, factory = self.run_apply({"approvals": [item]})
        self.assertEqual(result, 1)
        factory.assert_not_called()
        client.get.assert_not_called()
        client.post.assert_not_called()

    def test_batched_tokens_are_bound_to_each_review(self):
        client = Mock()
        client.post.return_value = (200, {"results": [
            {"review_id": "review-a", "status": "approved"},
            {"review_id": "review-b", "status": "approved"},
        ]})
        items = [approval(), approval("review-b", token="opaque-B")]
        result, _, client, _ = self.run_apply({"approvals": items}, client)
        self.assertEqual(result, 0)
        client.post.assert_called_once_with("/review/extraction/actions", {
            "review_ids": ["review-a", "review-b"], "action": "approve",
            "acknowledge_novelty_warning": False, "content_mode": "curated",
            "expected_snapshot_tokens": {"review-a": "opaque-A/+==", "review-b": "opaque-B"},
            "rationale": "checked evidence",
        })
        client.get.assert_not_called()

    def test_original_and_curated_both_send_tokens(self):
        client = Mock()
        client.post.side_effect = [response(), response("review-b")]
        items = [approval(), approval("review-b", "original", "opaque-B")]
        result, _, _, _ = self.run_apply({"approvals": items}, client)
        self.assertEqual(result, 0)
        bodies = [c.args[1] for c in client.post.call_args_list]
        self.assertEqual([b["content_mode"] for b in bodies], ["curated", "original"])
        self.assertEqual(bodies[1]["expected_snapshot_tokens"], {"review-b": "opaque-B"})

    def test_rejection_does_not_require_or_send_token(self):
        client = Mock()
        client.post.return_value = response(status="rejected")
        result, _, _, _ = self.run_apply({"rejections": [{"review_id": "review-a", "rationale": "no value"}]}, client)
        self.assertEqual(result, 0)
        self.assertNotIn("expected_snapshot_tokens", client.post.call_args.args[1])
        client.get.assert_not_called()

    def test_same_review_remove_then_approve_is_rejected_before_writes(self):
        decisions = {"removals": [{"review_id": "review-a", "entities": ["wrong"]}], "approvals": [approval()]}
        result, _, client, factory = self.run_apply(decisions)
        self.assertEqual(result, 1)
        factory.assert_not_called()
        client.post.assert_not_called()

    def test_failed_removal_stops_all_later_actions(self):
        client = Mock()
        client.post.return_value = (500, {"error": "cleanup failed"})
        decisions = {"removals": [{"review_id": "different", "entities": ["wrong"]}], "approvals": [approval()]}
        result, output, client, _ = self.run_apply(decisions, client)
        self.assertEqual(result, 1)
        client.post.assert_called_once_with("/review/extraction/different/remove", {"entities": ["wrong"], "edges": []})
        self.assertIn("未发送批准或拒绝", output)

    def test_remove_only_keeps_existing_payload(self):
        client = Mock()
        client.post.return_value = (200, {"removed_entities": 1})
        result, _, _, _ = self.run_apply({"removals": [{"review_id": "review-a", "entities": ["wrong"]}]}, client)
        self.assertEqual(result, 0)
        client.post.assert_called_once_with("/review/extraction/review-a/remove", {"entities": ["wrong"], "edges": []})

    def test_dry_run_checks_tokens_without_writes(self):
        result, _, client, _ = self.run_apply({"approvals": [approval()]}, dry_run=True)
        self.assertEqual(result, 0)
        client.get.assert_not_called()
        client.post.assert_not_called()
        result, _, _, factory = self.run_apply({"approvals": [approval(token=None)]}, dry_run=True)
        self.assertEqual(result, 1)
        factory.assert_not_called()

    def test_review_changed_stops_without_refetch_or_retry(self):
        client = Mock()
        client.post.return_value = response(status="review_changed")
        decisions = {"approvals": [approval(), approval("review-b", "original", "opaque-B")]}
        result, output, _, _ = self.run_apply(decisions, client)
        self.assertEqual(result, 1)
        self.assertIn("不会自动换 token", output)
        self.assertEqual(client.post.call_count, 1)
        self.assertEqual(client.post.call_args.args[1]["expected_snapshot_tokens"], {"review-a": "opaque-A/+=="})
        client.get.assert_not_called()

    def test_required_snapshot_server_error_is_not_retried(self):
        client = Mock()
        client.post.return_value = (422, {"error": {"code": "REVIEW_SNAPSHOT_REQUIRED"}})
        result, output, _, _ = self.run_apply({"approvals": [approval()]}, client)
        self.assertEqual(result, 1)
        self.assertIn("REVIEW_SNAPSHOT_REQUIRED", output)
        self.assertEqual(client.post.call_count, 1)
        client.get.assert_not_called()

    def test_already_processed_is_a_benign_skip(self):
        client = Mock()
        client.post.return_value = response(status="already_processed")
        result, _, _, _ = self.run_apply({"approvals": [approval()]}, client)
        self.assertEqual(result, 0)
        self.assertEqual(client.post.call_count, 1)
        client.get.assert_not_called()

    def test_group_admission_block_is_not_retried(self):
        client = Mock()
        client.post.return_value = response(status="entity_admission_blocked")
        result, _, _, _ = self.run_apply({"approvals": [approval()]}, client)
        self.assertEqual(result, 1)
        self.assertEqual(client.post.call_count, 1)
        client.get.assert_not_called()

    def test_partial_batch_keeps_approved_result_and_reports_stale(self):
        client = Mock()
        client.post.return_value = (200, {"results": [
            {"review_id": "review-a", "status": "approved"},
            {"review_id": "review-b", "status": "review_changed"},
        ]})
        result, output, _, _ = self.run_apply({"approvals": [approval(), approval("review-b", token="opaque-B")]}, client)
        self.assertEqual(result, 1)
        self.assertIn("-> approved", output)
        self.assertIn("-> review_changed", output)
        self.assertEqual(client.post.call_count, 1)

    def test_duplicate_or_conflicting_decisions_fail_before_writes(self):
        decisions_list = [
            {"approvals": [approval(), approval(token="another-token")]},
            {"approvals": [approval()], "rejections": [{"review_id": "review-a"}]},
            {"approvals": [approval(mode="unknown")]},
        ]
        for decisions in decisions_list:
            with self.subTest(decisions=decisions):
                result, _, client, factory = self.run_apply(decisions)
                self.assertEqual(result, 1)
                factory.assert_not_called()
                client.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

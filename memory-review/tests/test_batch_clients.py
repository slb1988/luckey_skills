"""memory-review 批量客户端（scan 并发/回执/驱动）定向离线测试。

全部使用虚构 ID/token、fake client、临时目录与模拟子进程；setUp 拦截 urllib 真实网络调用。
禁止加载历史决策文件或访问生产地址。
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


review = _load("review_queue", SCRIPTS / "review_queue.py")
drive = _load("drive_approvals", SCRIPTS / "drive_approvals.py")


def rid(n):  # 虚构完整 review ID
    return f"fakefake-0000-4000-8000-{n:012d}"


def mid(n):
    return f"memfake0-0000-4000-8000-{n:012d}"


def tok(n):
    return "rs1:" + f"{n:064x}"


def detail(rid_, group="project:fake-a", memory=None, status="review",
           memory_status="pending_extraction", token=None):
    return {"review_id": rid_, "memory_id": memory or mid(1), "group_id": group,
            "status": status, "memory_status": memory_status,
            "snapshot_token": token if token is not None else tok(1)}


class FakeClient:
    """脚本化只读 client：queue/detail 响应按序列出队（最后一个重复）；记录调用；禁止 POST。"""

    def __init__(self, queue=None, details=None):
        self.queue = list(queue if queue is not None else [{"items": []}])
        self.details = {k: list(v) for k, v in (details or {}).items()}
        self.get_log = []
        self.peak = 0
        self.detail_delay = 0.0
        self._lock = threading.Lock()
        self._in_flight = 0

    def _next(self, seq):
        return seq.pop(0) if len(seq) > 1 else seq[0]

    def get(self, path):
        with self._lock:
            self.get_log.append(path)
        if path.startswith("/review/extraction?"):
            with self._lock:
                resp = self._next(self.queue)
            if isinstance(resp, Exception):
                raise resp
            return resp
        rid_ = path.rsplit("/", 1)[-1]
        with self._lock:
            self._in_flight += 1
            self.peak = max(self.peak, self._in_flight)
        try:
            if self.detail_delay:
                time.sleep(self.detail_delay)
            with self._lock:
                resp = self._next(self.details[rid_])
            if isinstance(resp, Exception):
                raise resp
            return resp
        finally:
            with self._lock:
                self._in_flight -= 1

    def post(self, *args, **kwargs):
        raise AssertionError("离线测试禁止 POST")


def write_entries(path, entries):
    with open(path, "a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def intent_entry(payload):
    ids = [a["review_id"] for a in payload["approvals"]]
    return {"kind": "intent", "action": "approve", "review_ids": ids,
            "expected_snapshot_tokens": {a["review_id"]: a["snapshot_token"] for a in payload["approvals"]}}


def approved_entries(payload):
    return [intent_entry(payload),
            {"kind": "receipt", "action": "approve", "http_status": 200,
             "results": [{"review_id": a["review_id"], "status": "approved"}
                         for a in payload["approvals"]]}]


class FakeApply:
    """模拟 apply 子进程：handler(payload, receipt_path, 第几次调用) -> (rc, stdout)。"""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def run(self, cmd, **kwargs):
        self.calls.append(cmd)
        decisions_path = Path(cmd[cmd.index("apply") + 1])
        receipt_path = Path(cmd[cmd.index("--receipt-file") + 1])
        payload = json.loads(decisions_path.read_text(encoding="utf-8"))
        rc, out = self.handler(payload, receipt_path, len(self.calls))
        return SimpleNamespace(returncode=rc, stdout=out, stderr="")


def refuse_apply(payload, receipt_path, n):
    raise AssertionError("不应提交任何 apply")


class OfflineGuard(unittest.TestCase):
    def setUp(self):
        net = mock.patch("urllib.request.urlopen",
                         side_effect=AssertionError("离线测试禁止真实网络调用"))
        net.start()
        self.addCleanup(net.stop)


class ScanTests(OfflineGuard):
    def run_scan(self, client):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            out_path = Path(directory) / "packet.json"
            with mock.patch.object(review, "make_client", return_value=client), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                result = review.cmd_scan(SimpleNamespace(output=str(out_path)))
            formal = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else None
            diag_path = Path(str(out_path) + ".incomplete.json")
            diag = json.loads(diag_path.read_text(encoding="utf-8")) if diag_path.exists() else None
        return result, output.getvalue(), formal, diag

    def test_bounded_concurrency_order_and_per_id_reconciliation(self):
        n = 54
        ids = [rid(i) for i in range(n)]
        client = FakeClient(queue=[{"items": [{"review_id": i} for i in ids]}],
                            details={i: [detail(i)] for i in ids})
        client.detail_delay = 0.02
        t0 = time.monotonic()
        result, output, formal, diag = self.run_scan(client)
        elapsed = time.monotonic() - t0
        self.assertEqual(result, 0)
        self.assertIsNone(diag)
        self.assertEqual([p["review_id"] for p in formal], ids)  # 成功结果按原列表顺序
        self.assertGreaterEqual(client.peak, 2)  # 并发生效
        self.assertLessEqual(client.peak, 8)  # 有限并发上限
        self.assertLess(elapsed, n * 0.02)  # 非串行耗时
        self.assertIn("成功 54，失败 0", output)
        self.assertIn("[54/54]", output)
        for i in ids:  # 逐完整 ID 进度可对账
            self.assertIn(i, output)
        self.assertNotIn("覆盖未确定", output)

    def test_at_limit_200_reports_coverage_uncertain(self):
        n = review.SCAN_LIMIT
        ids = [rid(i) for i in range(n)]
        client = FakeClient(queue=[{"items": [{"review_id": i} for i in ids]}],
                            details={i: [detail(i)] for i in ids})
        result, output, formal, diag = self.run_scan(client)
        self.assertEqual(result, 0)
        self.assertIsNone(diag)
        self.assertEqual(len(formal), n)
        self.assertIn("覆盖未确定", output)  # 即使详情全成功也不得声称全队列完成

    def test_partial_detail_failure_publishes_no_formal_packet(self):
        ids = [rid(i) for i in range(6)]
        bad = {ids[2], ids[5]}
        client = FakeClient(queue=[{"items": [{"review_id": i} for i in ids]}],
                            details={i: [RuntimeError("boom") if i in bad else detail(i)] for i in ids})
        result, output, formal, diag = self.run_scan(client)
        self.assertEqual(result, 1)  # 失败运行非成功退出
        self.assertIsNone(formal)  # 不发布正式审核包
        self.assertFalse(diag["complete"])
        self.assertEqual(sorted(diag["errors"]), sorted(bad))  # 逐完整 ID 错误
        self.assertEqual([i["review_id"] for i in diag["items"]],
                         [i for i in ids if i not in bad])  # 保留成功详情，顺序不丢
        self.assertIn("不发布正式审核包", output)
        for i in bad:
            self.assertIn(i, output)

    def test_list_failure_is_not_an_empty_queue(self):
        client = FakeClient(queue=[OSError("connection reset")])
        result, output, formal, diag = self.run_scan(client)
        self.assertEqual(result, 1)
        self.assertIsNone(formal)
        self.assertIsNone(diag)
        self.assertIn("不能当作空队列", output)


class ApplyReceiptTests(OfflineGuard):
    def run_apply(self, decisions, client, receipt_path):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.json"
            path.write_text(json.dumps(decisions), encoding="utf-8")
            args = SimpleNamespace(decisions=str(path), dry_run=False, receipt_file=str(receipt_path))
            with mock.patch.object(review, "make_client", return_value=client), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                result = review.cmd_apply(args)
        entries = [json.loads(l) for l in Path(receipt_path).read_text(encoding="utf-8").splitlines()
                   if l.strip()]
        return result, output.getvalue(), entries

    def test_intent_persisted_before_post_then_receipt_with_full_ids(self):
        a, b = rid(1), rid(2)
        client = mock.Mock()
        client.post.return_value = (200, {"results": [
            {"review_id": a, "status": "approved"}, {"review_id": b, "status": "approved"}]})
        with tempfile.TemporaryDirectory() as directory:
            result, output, entries = self.run_apply(
                {"approvals": [
                    {"review_id": a, "content_mode": "curated", "snapshot_token": tok(1), "rationale": "r"},
                    {"review_id": b, "content_mode": "curated", "snapshot_token": tok(2), "rationale": "r"}]},
                client, Path(directory) / "receipts.jsonl")
        self.assertEqual(result, 0)
        self.assertEqual([e["kind"] for e in entries], ["intent", "receipt"])  # 先意图后回执
        self.assertEqual(entries[0]["review_ids"], [a, b])
        self.assertEqual(entries[0]["expected_snapshot_tokens"], {a: tok(1), b: tok(2)})
        self.assertEqual([r["review_id"] for r in entries[1]["results"]], [a, b])
        self.assertIn(f"APPROVE {a} -> approved", output)  # 完整 ID 输出

    def test_transport_error_is_recorded_unknown_and_stops_new_writes(self):
        a, b = rid(1), rid(2)
        client = mock.Mock()
        client.post.side_effect = TimeoutError("timed out")  # 服务端可能已提交
        with tempfile.TemporaryDirectory() as directory:
            result, output, entries = self.run_apply(
                {"approvals": [
                    {"review_id": a, "content_mode": "curated", "snapshot_token": tok(1), "rationale": "r1"},
                    {"review_id": b, "content_mode": "original", "snapshot_token": tok(2), "rationale": "r2"}]},
                client, Path(directory) / "receipts.jsonl")
        self.assertEqual(result, 1)
        self.assertEqual(client.post.call_count, 1)  # 不重发，也不继续后续组
        self.assertEqual([e["kind"] for e in entries], ["intent", "unknown"])
        self.assertEqual(entries[1]["review_ids"], [a])
        self.assertIn("结果未知", output)


class DriveTests(OfflineGuard):
    def setUp(self):
        super().setUp()
        saved = {k: getattr(drive, k) for k in ("POLL_INTERVAL", "WAIT_BUDGET", "STALL_DUMP_AFTER")}
        drive.POLL_INTERVAL = 0.01
        drive.WAIT_BUDGET = 0.3
        drive.STALL_DUMP_AFTER = 0.1
        self.addCleanup(lambda: [setattr(drive, k, v) for k, v in saved.items()])

    @staticmethod
    def payload(items):
        """items: (n, group, mode) → 顶层 approvals 结构（含必填 memory_id/group_id）。"""
        return {"approvals": [
            {"review_id": rid(n), "memory_id": mid(n), "group_id": group, "content_mode": mode,
             "snapshot_token": tok(n), "rationale": f"checked {n}"}
            for n, group, mode in items]}

    def run_drive(self, decisions, client, fake_apply, decisions_path=None, run_dir=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        if decisions_path is None:
            decisions_path = directory / "decisions.json"
            decisions_path.write_text(json.dumps(decisions), encoding="utf-8")
        run_dir = Path(run_dir) if run_dir else directory / "run"
        output = io.StringIO()
        with mock.patch.object(drive, "build_client", return_value=client), \
                mock.patch.object(drive.subprocess, "run", side_effect=fake_apply.run), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = drive.main([str(decisions_path), "--run-dir", str(run_dir)])
        return code, output.getvalue(), run_dir

    @staticmethod
    def states(run_dir):
        return {i["review_id"]: i["state"]
                for i in json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))["items"]}

    def test_input_requires_memory_and_group_metadata(self):
        decisions = {"approvals": [{"review_id": rid(1), "content_mode": "curated",
                                    "snapshot_token": tok(1), "rationale": "r"}]}
        code, output, _ = self.run_drive(decisions, FakeClient(), FakeApply(refuse_apply))
        self.assertEqual(code, 1)  # POST 前阻塞
        self.assertIn("memory_id", output)

        code, output, _ = self.run_drive({"approvals": []}, FakeClient(), FakeApply(refuse_apply))
        self.assertEqual(code, 1)
        self.assertIn("空批不是完成条件", output)

        bad = self.payload([(1, "project:fake-a", "curated")])
        bad["removals"] = [{"review_id": rid(9), "entities": ["x"]}]
        code, output, _ = self.run_drive(bad, FakeClient(), FakeApply(refuse_apply))
        self.assertEqual(code, 1)
        self.assertIn("驱动只执行 approvals", output)

    def test_group_gate_serializes_same_group_and_skips_final_rescan(self):
        decisions = self.payload([(1, "project:fake-a", "curated"), (2, "project:fake-a", "original"),
                                  (3, "project:fake-b", "curated")])
        client = FakeClient(details={
            rid(1): [detail(rid(1), "project:fake-a", mid(1), token=tok(1)),
                     detail(rid(1), "project:fake-a", mid(1), "approved", "submitted", tok(1)),
                     detail(rid(1), "project:fake-a", mid(1), "approved", "indexed", tok(1))],
            rid(2): [detail(rid(2), "project:fake-a", mid(2), token=tok(2)),
                     detail(rid(2), "project:fake-a", mid(2), "approved", "indexed", tok(2))],
            rid(3): [detail(rid(3), "project:fake-b", mid(3), token=tok(3)),
                     detail(rid(3), "project:fake-b", mid(3), "approved", "indexed", tok(3))],
        })

        def handler(payload, receipt_path, n):
            write_entries(receipt_path, approved_entries(payload))
            return 0, "ok"

        apply = FakeApply(handler)
        code, output, run_dir = self.run_drive(decisions, client, apply)
        self.assertEqual(code, 0)
        self.assertIn("本批已对账结束", output)
        self.assertEqual(len(apply.calls), 2)
        round1 = json.loads((run_dir / "round-001.decisions.json").read_text(encoding="utf-8"))
        round2 = json.loads((run_dir / "round-002.decisions.json").read_text(encoding="utf-8"))
        # 组间交错；同组 rid2 在 rid1 indexed 之前零 POST
        self.assertEqual([a["review_id"] for a in round1["approvals"]], [rid(1), rid(3)])
        self.assertEqual([a["review_id"] for a in round2["approvals"]], [rid(2)])
        # 最后在途项 indexed 后无额外全队列扫描
        self.assertEqual(client.get_log[-1], f"/review/extraction/{rid(2)}")
        states = self.states(run_dir)
        self.assertEqual(states, {rid(1): "done", rid(2): "done", rid(3): "done"})

    def test_terminal_head_does_not_end_batch_with_tail_pending(self):
        decisions = self.payload([(1, "project:fake-a", "curated"), (2, "project:fake-a", "curated")])
        client = FakeClient(queue=[{"items": []}], details={  # 缺席 open 列表须定点直读核实
            rid(1): [detail(rid(1), "project:fake-a", mid(1), "approved", "indexed", tok(1))],
            rid(2): [detail(rid(2), "project:fake-a", mid(2), token=tok(2)),
                     detail(rid(2), "project:fake-a", mid(2), "approved", "indexed", tok(2))],
        })

        def handler(payload, receipt_path, n):
            write_entries(receipt_path, approved_entries(payload))
            return 0, "ok"

        apply = FakeApply(handler)
        code, output, run_dir = self.run_drive(decisions, client, apply)
        self.assertEqual(code, 0)  # 不因首轮空批结束
        self.assertEqual(len(apply.calls), 1)  # 尾部仍被执行
        self.assertEqual([a["review_id"] for a in json.loads(
            (run_dir / "round-001.decisions.json").read_text(encoding="utf-8"))["approvals"]], [rid(2)])
        states = self.states(run_dir)
        self.assertEqual(states[rid(1)], "done")
        self.assertEqual(states[rid(2)], "done")
        self.assertIn("并发/先前已批准", output)  # 组头终态单独归因，不计本次批准
        self.assertNotIn("本次批准回执 → indexed：2", output)

    def test_all_preview_pending_waits_with_budget_then_blocks(self):
        decisions = self.payload([(1, "project:fake-a", "curated")])
        client = FakeClient(queue=[{"items": [{"review_id": rid(1)}]}],
                            details={rid(1): [detail(rid(1), "project:fake-a", mid(1),
                                                     "preview_pending", token=tok(1))]})
        code, output, run_dir = self.run_drive(decisions, client, FakeApply(refuse_apply))
        self.assertEqual(code, 2)  # 有限等待到期，非成功退出
        self.assertIn(rid(1), output)  # 完整 ID 出现在阻塞报告
        self.assertIn("等待/阻塞", output)
        self.assertEqual(self.states(run_dir)[rid(1)], "pending")  # pending 保留

    def test_head_read_failure_is_blocked_not_skipped(self):
        decisions = self.payload([(1, "project:fake-a", "curated")])
        client = FakeClient(queue=[{"items": []}],
                            details={rid(1): [RuntimeError("connection reset")]})
        code, output, run_dir = self.run_drive(decisions, client, FakeApply(refuse_apply))
        self.assertEqual(code, 4)  # 读取失败类别
        self.assertIn("读取失败", output)
        self.assertEqual(self.states(run_dir)[rid(1)], "pending")  # 不记 skip/完成

    def test_token_change_goes_to_rereview_without_post(self):
        decisions = self.payload([(1, "project:fake-a", "curated")])
        changed = detail(rid(1), "project:fake-a", mid(1), token="rs1:" + "f" * 64)
        client = FakeClient(queue=[{"items": [{"review_id": rid(1)}]}],
                            details={rid(1): [changed]})
        code, output, run_dir = self.run_drive(decisions, client, FakeApply(refuse_apply))
        self.assertEqual(code, 2)
        self.assertIn("待重审", output)
        self.assertEqual(self.states(run_dir)[rid(1)], "needs_rereview")  # 不自动换 token

    def test_group_mismatch_blocked_before_post(self):
        decisions = self.payload([(1, "project:fake-a", "curated")])
        client = FakeClient(queue=[{"items": [{"review_id": rid(1)}]}],
                            details={rid(1): [detail(rid(1), "project:OTHER", mid(1), token=tok(1))]})
        code, output, run_dir = self.run_drive(decisions, client, FakeApply(refuse_apply))
        self.assertEqual(code, 2)
        self.assertIn("不一致", output)
        self.assertEqual(self.states(run_dir)[rid(1)], "needs_rereview")

    def test_unknown_submit_timeout_is_verified_not_resent(self):
        decisions = self.payload([(1, "project:fake-a", "curated")])
        client = FakeClient(details={
            rid(1): [detail(rid(1), "project:fake-a", mid(1), token=tok(1)),
                     detail(rid(1), "project:fake-a", mid(1), "approved", "submitted", tok(1)),
                     detail(rid(1), "project:fake-a", mid(1), "approved", "indexed", tok(1))],
        })

        def handler(payload, receipt_path, n):
            write_entries(receipt_path, [intent_entry(payload)])  # 有意图无回执
            raise subprocess.TimeoutExpired(cmd="fake", timeout=600)  # 客户端超时，服务端已提交

        apply = FakeApply(handler)
        code, output, run_dir = self.run_drive(decisions, client, apply)
        self.assertEqual(code, 0)
        self.assertEqual(len(apply.calls), 1)  # 未知回执不重发
        self.assertIn("未知回执核对后已批准", output)  # 与本次批准回执分开统计

    def test_unknown_submit_still_open_stays_unknown(self):
        decisions = self.payload([(1, "project:fake-a", "curated")])
        client = FakeClient(details={
            rid(1): [detail(rid(1), "project:fake-a", mid(1), token=tok(1)),
                     detail(rid(1), "project:fake-a", mid(1), "review", "pending_extraction", tok(1))],
        })

        def handler(payload, receipt_path, n):
            write_entries(receipt_path, [intent_entry(payload)])
            raise subprocess.TimeoutExpired(cmd="fake", timeout=600)

        apply = FakeApply(handler)
        code, output, run_dir = self.run_drive(decisions, client, apply)
        self.assertEqual(code, 3)  # 一次 open 不是未提交证明：保持未知暂停
        self.assertEqual(len(apply.calls), 1)
        self.assertIn("未知提交结果", output)
        self.assertEqual(self.states(run_dir)[rid(1)], "submitted_unknown")

    def test_restart_replays_receipts_and_never_reposts_attempted(self):
        decisions = self.payload([(1, "project:fake-a", "curated"), (2, "project:fake-a", "curated")])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        decisions_path = Path(tmp.name) / "decisions.json"
        decisions_path.write_text(json.dumps(decisions), encoding="utf-8")
        run_dir = Path(tmp.name) / "run"

        def crash_handler(payload, receipt_path, n):  # 回执已写、状态未更新处崩溃
            write_entries(receipt_path, approved_entries(payload))
            raise RuntimeError("simulated crash")

        client1 = FakeClient(details={rid(1): [detail(rid(1), "project:fake-a", mid(1), token=tok(1))]})
        with mock.patch.object(drive, "build_client", return_value=client1), \
                mock.patch.object(drive.subprocess, "run", side_effect=FakeApply(crash_handler).run), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(RuntimeError):
                drive.main([str(decisions_path), "--run-dir", str(run_dir)])
        before = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual([i["state"] for i in before["items"]], ["pending", "pending"])

        client2 = FakeClient(details={
            rid(1): [detail(rid(1), "project:fake-a", mid(1), "approved", "indexed", tok(1))],
            rid(2): [detail(rid(2), "project:fake-a", mid(2), token=tok(2)),
                     detail(rid(2), "project:fake-a", mid(2), "approved", "indexed", tok(2))],
        })

        def ok_handler(payload, receipt_path, n):
            write_entries(receipt_path, approved_entries(payload))
            return 0, "ok"

        apply2 = FakeApply(ok_handler)
        code, output, _ = self.run_drive(decisions, client2, apply2,
                                         decisions_path=decisions_path, run_dir=run_dir)
        self.assertEqual(code, 0)
        self.assertEqual(len(apply2.calls), 1)  # 已尝试项不重复审批
        round2 = json.loads((run_dir / "round-002.decisions.json").read_text(encoding="utf-8"))
        self.assertEqual([a["review_id"] for a in round2["approvals"]], [rid(2)])  # 轮次追加不覆盖
        self.assertEqual(self.states(run_dir), {rid(1): "done", rid(2): "done"})  # 未尝试项不丢失

    def test_restart_with_intent_only_verifies_readonly_without_resend(self):
        decisions = self.payload([(1, "project:fake-a", "curated")])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        decisions_path = Path(tmp.name) / "decisions.json"
        decisions_path.write_text(json.dumps(decisions), encoding="utf-8")
        run_dir = Path(tmp.name) / "run"

        def crash_handler(payload, receipt_path, n):  # 提交意图已持久化但无回执
            write_entries(receipt_path, [intent_entry(payload)])
            raise RuntimeError("simulated crash")

        client1 = FakeClient(details={rid(1): [detail(rid(1), "project:fake-a", mid(1), token=tok(1))]})
        with mock.patch.object(drive, "build_client", return_value=client1), \
                mock.patch.object(drive.subprocess, "run", side_effect=FakeApply(crash_handler).run), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(RuntimeError):
                drive.main([str(decisions_path), "--run-dir", str(run_dir)])

        client2 = FakeClient(details={
            rid(1): [detail(rid(1), "project:fake-a", mid(1), "approved", "indexed", tok(1))]})
        apply2 = FakeApply(refuse_apply)  # 恢复后不需要任何新提交
        code, output, _ = self.run_drive(decisions, client2, apply2,
                                         decisions_path=decisions_path, run_dir=run_dir)
        self.assertEqual(code, 0)
        self.assertEqual(apply2.calls, [])
        self.assertEqual(self.states(run_dir)[rid(1)], "done")
        self.assertIn("未知回执核对后已批准", output)

    def test_existing_lock_refuses_second_writer(self):
        decisions = self.payload([(1, "project:fake-a", "curated")])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name) / "run"
        run_dir.mkdir()
        (run_dir / "run.lock").write_text("{}", encoding="utf-8")
        code, output, _ = self.run_drive(decisions, FakeClient(), FakeApply(refuse_apply),
                                         run_dir=run_dir)
        self.assertEqual(code, 4)  # 陈旧标记不自动抢占
        self.assertIn("run.lock", output)

    def test_corrupt_state_is_not_reset_as_empty_batch(self):
        decisions = self.payload([(1, "project:fake-a", "curated")])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name) / "run"
        run_dir.mkdir()
        (run_dir / "state.json").write_text("not json{", encoding="utf-8")
        code, output, _ = self.run_drive(decisions, FakeClient(), FakeApply(refuse_apply),
                                         run_dir=run_dir)
        self.assertEqual(code, 4)
        self.assertIn("不当空批重置", output)

    def test_full_id_attribution_with_same_8char_prefix(self):
        a = "deadbeef-0000-4000-8000-000000000001"
        b = "deadbeef-0000-4000-8000-000000000002"  # 与 a 共享 8 字符前缀
        decisions = {"approvals": [
            {"review_id": a, "memory_id": mid(1), "group_id": "project:fake-a",
             "content_mode": "curated", "snapshot_token": tok(1), "rationale": "r"},
            {"review_id": b, "memory_id": mid(2), "group_id": "project:fake-b",
             "content_mode": "curated", "snapshot_token": tok(2), "rationale": "r"}]}
        client = FakeClient(details={
            a: [detail(a, "project:fake-a", mid(1), token=tok(1)),
                detail(a, "project:fake-a", mid(1), "approved", "indexed", tok(1))],
            b: [detail(b, "project:fake-b", mid(2), token=tok(2))],
        })

        def handler(payload, receipt_path, n):
            write_entries(receipt_path, [intent_entry(payload),
                                         {"kind": "receipt", "action": "approve", "http_status": 200,
                                          "results": [{"review_id": a, "status": "approved"},
                                                      {"review_id": b, "status": "review_changed"}]}])
            return 1, ""

        code, output, run_dir = self.run_drive(decisions, client, FakeApply(handler))
        self.assertEqual(code, 2)
        states = self.states(run_dir)
        self.assertEqual(states[a], "done")  # 回执精确归属
        self.assertEqual(states[b], "needs_rereview")

    def test_already_processed_is_verified_and_not_counted_as_ours(self):
        decisions = self.payload([(1, "project:fake-a", "curated")])
        client = FakeClient(details={
            rid(1): [detail(rid(1), "project:fake-a", mid(1), token=tok(1)),
                     detail(rid(1), "project:fake-a", mid(1), "approved", "indexed", tok(1))],
        })

        def handler(payload, receipt_path, n):
            write_entries(receipt_path, [intent_entry(payload),
                                         {"kind": "receipt", "action": "approve", "http_status": 200,
                                          "results": [{"review_id": rid(1),
                                                       "status": "already_processed"}]}])
            return 0, ""

        code, output, run_dir = self.run_drive(decisions, client, FakeApply(handler))
        self.assertEqual(code, 0)
        self.assertIn("并发/先前已批准", output)  # 单独统计
        self.assertNotIn("本次批准回执 → indexed", output)

    def test_hub_only_does_not_release_group_gate(self):
        decisions = self.payload([(1, "project:fake-a", "curated"), (2, "project:fake-a", "curated")])
        client = FakeClient(details={
            rid(1): [detail(rid(1), "project:fake-a", mid(1), token=tok(1)),
                     detail(rid(1), "project:fake-a", mid(1), "approved", "hub_only", tok(1))],
        })

        def handler(payload, receipt_path, n):
            write_entries(receipt_path, approved_entries(payload))
            return 0, "ok"

        apply = FakeApply(handler)
        code, output, run_dir = self.run_drive(decisions, client, apply)
        self.assertEqual(code, 2)  # 有限等待到期，非成功退出
        self.assertIn("hub_only 不放行", output)
        self.assertEqual(len(apply.calls), 1)  # 同组下一条在前条 indexed 前零 POST
        self.assertFalse((run_dir / "round-002.decisions.json").exists())
        states = self.states(run_dir)
        self.assertEqual(states[rid(1)], "wait_indexed")
        self.assertEqual(states[rid(2)], "pending")

    def test_stall_dumps_stacks_to_independent_file(self):
        decisions = self.payload([(1, "project:fake-a", "curated")])
        client = FakeClient(details={
            rid(1): [detail(rid(1), "project:fake-a", mid(1), token=tok(1)),
                     detail(rid(1), "project:fake-a", mid(1), "approved", "indexed", tok(1))],
        })

        def handler(payload, receipt_path, n):
            time.sleep(0.25)  # 模拟子进程长时间无返回（阈值 0.1s）
            write_entries(receipt_path, approved_entries(payload))
            return 0, "ok"

        code, output, run_dir = self.run_drive(decisions, client, FakeApply(handler))
        self.assertEqual(code, 0)
        stacks = (run_dir / "stacks.txt").read_text(encoding="utf-8")
        self.assertIn("most recent call first", stacks)  # 栈转储落独立文件
        self.assertIn("run_apply_round", stacks)  # 能定位最后活动阶段
        log = (run_dir / "drive.log").read_text(encoding="utf-8")
        self.assertIn("[apply] round 1", log)  # 阶段日志定位最后活动与完整 ID
        self.assertIn(rid(1), log)


if __name__ == "__main__":
    unittest.main()

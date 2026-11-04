"""recall-metrics.jsonl：每次召回一行可聚合指标，不含 query/正文/模型输出。"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from memory_hook import recall_metrics_row, recall_origin, record_recall_metrics


@pytest.mark.parametrize("cwd,expected", [
    ("C:\\tmp\\dwa-iso-run", "eval"),
    ("/tmp/skill-eval/run1", "eval"),
    ("C:\\Users\\admin\\AppData\\Local\\Temp\\x", "eval"),
    ("D:\\Github\\ObsidianVault", "interactive"),
    ("D:\\MainDev", "interactive"),
])
def test_recall_origin_from_cwd(cwd, expected, monkeypatch) -> None:
    monkeypatch.delenv("MEMORY_HUB_RECALL_ORIGIN", raising=False)
    assert recall_origin(cwd) == expected


def test_recall_origin_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("MEMORY_HUB_RECALL_ORIGIN", "automation")
    assert recall_origin("D:\\MainDev") == "automation"


def test_metrics_row_counts_gates_and_omits_text(tmp_path) -> None:
    audit = {"stage_a": {
        "llm_calls": [{"stage": "correction_resolver", "latency_ms": 900, "usage": {"output_tokens": 12}},
                      {"stage": "judge", "latency_ms": 20000, "usage": {"output_tokens": 700}}],
        "correction_resolution": {"applies": False, "degraded": "RETRIEVAL_CORRECTION_RESOLVER_INVALID_RESPONSE"},
        "judgments": [
            {"rank": 1, "rating": 0, "conflict": "被结构化 SUPERSEDES 关系替代：x", "evidence": "旧事实",
             "supports_slots": ["a"], "superseded_reason": "old_quote_not_located"},
            {"rank": 2, "rating": 0, "conflict": "被结构化 SUPERSEDES 关系替代：y", "evidence": ""},
            {"rank": 3, "rating": 2, "history_note": "较早记录"},
            {"rank": 4, "rating": 1, "conflict": "related 缺少原始任务/所选证据的可核验锚点，已自动降级"},
        ]}}
    response = {"quality": {"candidates": 10, "kept": 3},
                "retrieval": {"retrieval_id": "r-1", "policy_version": "p"},
                "raw_response": {"fusion": {"fallback": None}}}
    row = recall_metrics_row(source="claude", project_id="obsidianvault", cwd="D:\\Github\\ObsidianVault",
                             outcome="injected", duration_ms=25000, response=response, audit=audit,
                             context="已确认\n■ 标题\n- 一条\n- 两条")
    assert row["judge_ms"] == 20000 and row["judge_out_tokens"] == 700 and row["judge_calls"] == 1
    assert row["resolver_degraded"] == "RETRIEVAL_CORRECTION_RESOLVER_INVALID_RESPONSE"
    assert row["supersede_kills"] == 2 and row["supersede_useful_reasons"] == {"old_quote_not_located": 1}
    assert row["supersede_partial"] == 1 and row["anchor_kills"] == 1
    assert row["context_lines"] == 2 and row["origin"] == "interactive"
    assert "旧事实" not in json.dumps(row, ensure_ascii=False)

    record_recall_metrics(SimpleNamespace(state_dir=tmp_path), row)
    record_recall_metrics(SimpleNamespace(state_dir=tmp_path), recall_metrics_row(
        source="pi", project_id="maindev", cwd="D:\\MainDev", outcome="error", duration_ms=110000,
        error_code="RETRIEVAL_JUDGE_UNAVAILABLE"))
    lines = (tmp_path / "recall-metrics.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["outcome"] for line in lines] == ["injected", "error"]
    assert json.loads(lines[1])["error_code"] == "RETRIEVAL_JUDGE_UNAVAILABLE"


def test_metrics_row_links_failures_and_execution_without_secrets() -> None:
    """失败行带 503 返回的 retrieval_id/request_id（可与服务端失败审计对账）；成功行带执行指纹/代码版本。"""
    from memory_hook import HubError

    error = HubError("HTTP 503: unavailable", status_code=503, error_code="RETRIEVAL_JUDGE_UNAVAILABLE",
                     request_id="req-1", retrieval_id="01a1a785-e2d0-7226-855e-3478638137e0")
    failed = recall_metrics_row(source="pi", project_id="maindev", cwd="D:\MainDev", outcome="error",
                                duration_ms=1000, error_code=error.error_code, error=error)
    assert failed["retrieval_id"] == "01a1a785-e2d0-7226-855e-3478638137e0"
    assert failed["request_id"] == "req-1"
    unsafe = HubError("x", retrieval_id="bad id with spaces", request_id="<script>")
    row = recall_metrics_row(source="pi", project_id="maindev", cwd="D:\MainDev", outcome="error",
                             duration_ms=1, error=unsafe)
    assert row["retrieval_id"] is None and row["request_id"] is None

    audit = {"execution": {"fingerprint": "f" * 64, "code_version": "abc123def456"},
             "stage_a": {"format_retries": 1, "correction_rejudgments": 0, "llm_calls": [
                 {"stage": "judge", "reason": "initial", "fallback_used": True, "latency_ms": 5,
                  "outcome": "invalid_json"},
                 {"stage": "judge", "reason": "format_retry", "fallback_used": False, "latency_ms": 5,
                  "outcome": "parsed"}]}}
    ok = recall_metrics_row(source="claude", project_id="obsidianvault", cwd="D:\Github\ObsidianVault",
                            outcome="injected", duration_ms=1000, audit=audit, context="- x")
    assert (ok["execution_fingerprint"], ok["code_version"]) == ("f" * 64, "abc123def456")
    assert (ok["judge_format_retries"], ok["correction_rejudgments"], ok["fallback_calls"]) == (1, 0, 1)
    assert ok["request_id"] is None

"""Input/feedback contract regressions, no live calls or automatic fact approval."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from memory_hook import extract_referenced_project_ids, rendered_context_stats
from recall_query import build_recall_query, compact_query_context
from recall_feedback import record_feedback, replay_feedback
from test_pi_extension_e2e import NODE, render_extension_for_test

PATH = "Main/Plugins/GASExtendedPL/Source/GASExtendedPL/Public/Debug/PLBuildVersion.h"
NAV_PATH = ".team/sunlaibing/feedback_env-read-guard.md"
SIGNALS = ["PL_BuildProjectWindows", "23069", "PrePackage.py", "WinBuilder1_MainDev", "MainDev", "13155", "PLBuildVersion.h", "file(s) not on client", "Traceback"]


def sample_prompt():
    real = os.environ.get("RECALL_SAMPLE_PROMPT")
    if real:
        return Path(real).read_text(encoding="utf-8")
    return ("PL_BuildProjectWindows build23069 Prepare Package 分析 TeamCity 错误\n"
            "Running PrePackage.py --workspace-name=WinBuilder1_MainDev --stream-name=MainDev --change-list=13155\n"
            + "ordinary log output and environment metadata\n" * 160
            + f"p4 edit {PATH} - file(s) not on client\nTraceback (most recent call last):\n"
            'File "PrePackage.py", line 74, in update_game_version\np4Client.checkout(header_path)\n'
            + f"P4.P4Exception: {PATH} - file(s) not on client\nStep Prepare Package failed")


def test_query_budget_keeps_real_task_identifiers_and_tail_not_only_prefix():
    prompt = sample_prompt()
    query, stats = build_recall_query(prompt, "obsidianvault")
    assert len(prompt) > 4000 and len(query) <= 4000
    assert stats["compacted"] and stats["max_chars"] == 4000
    assert "omitted" in query and "file(s) not on client" not in prompt[:1200]
    for signal in SIGNALS:
        assert signal in query
    assert "p4Client.checkout(header_path)" in query
    wrapped, _ = build_recall_query("Orca boilerplate " * 1000 + "\n=== TASK ===\n" + prompt, "obsidianvault")
    assert wrapped == query
    assert "Orca boilerplate" not in wrapped


@pytest.mark.skipif(not NODE, reason="node required")
def test_pi_and_shared_python_budget_same_input(tmp_path):
    extension = render_extension_for_test(tmp_path)
    prompt = sample_prompt()
    source = tmp_path / "query.json"
    source.write_text(json.dumps({"prompt": prompt}), encoding="utf-8")
    driver = tmp_path / "query.mjs"
    driver.write_text('import {readFileSync} from "node:fs";\n'
        f'import {{focusBootstrapPrompt}} from {json.dumps(extension.as_uri())};\n'
        f'const input=JSON.parse(readFileSync({json.dumps(str(source))}, "utf8"));\n'
        'const x=focusBootstrapPrompt(input.prompt,"obsidianvault");\n'
        'console.log(JSON.stringify({query:`obsidianvault 任务: ${x.intent}`+(x.context?`\\n上下文:\\n${x.context}`:""),x}));', encoding="utf-8")
    result = subprocess.run([NODE, str(driver)], capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["query"] == build_recall_query(prompt, "obsidianvault")[0]
    assert len(data["query"]) <= 4000


def test_unvisited_is_unknown_feedback_persists_and_next_similar_query_replays(tmp_path):
    query = "TeamCity PrePackage build23069 PLBuildVersion file(s) not on client"
    assert replay_feedback(tmp_path, project_id="obsidianvault", query=query, context="") == []
    record = record_feedback(tmp_path, {"project_id": "obsidianvault", "query": query,
        "retrieval_id": "sample-previous", "note": "Lost diagnostic tail; navigation requires verification, not a proven fix",
        "outcome": "unverified", "actor": "agent", "expected_signals": ["file(s) not on client"],
        "expected_navigation": [NAV_PATH]})
    checks = replay_feedback(tmp_path, project_id="obsidianvault", query="PrePackage TeamCity similar build PLBuildVersion file(s) not on client", context="")
    assert len(checks) == 1
    assert checks[0]["feedback_id"] == record["feedback_id"]
    assert checks[0]["outcome"] == "unverified"  # Not clicked does not mean useless.
    assert checks[0]["missing_signals"] == [] and checks[0]["missing_navigation"] == [NAV_PATH]
    assert checks[0]["answer_validation"] == "not_evaluated"
    present = replay_feedback(tmp_path, project_id="obsidianvault", query=query, context="历史导航：" + NAV_PATH)
    assert present[0]["missing_navigation"] == [] and present[0]["admission"] == "evaluation_only"
    assert replay_feedback(tmp_path, project_id="private", query=query, context="") == []


def test_counts_use_rendered_clues_and_sources_not_unknown_or_omitted():
    one = {"status": "known", "source_ids": ["e1"], "conclusion": "历史配置需核验"}
    unknown = {"status": "unknown", "source_ids": []}
    audit = {"stage_b": {"items": [one, *[unknown] * 4], "rendered_items": [one],
        "input_sources": [{"source_id": "e1", "result_id": "m1"}, {"source_id": "e2", "result_id": "not-rendered"}]}}
    stats = rendered_context_stats(audit, "已确认\n- 历史配置需核验", 1)
    assert stats == {"clue_items": 1, "source_memories": 1, "audit_items": 5, "unknown_items": 4}
    assert rendered_context_stats(audit, "", 0)["clue_items"] == 0


def test_short_queries_unchanged_and_no_scope_from_logs():
    query, stats = build_recall_query("ws:project-b 分析错误\n上下文只作日志 ws:forbidden", "project-a")
    assert not stats["compacted"]
    assert extract_referenced_project_ids(query, "project-a") == ["project-b"]
    assert compact_query_context("just a small context", 200) == "just a small context"
    # Oversized whitespace-delimited paths are omitted whole rather than invented prefixes.
    assert "/a/" + "x" * 1000 not in compact_query_context("/a/" + "x" * 1000, 100)

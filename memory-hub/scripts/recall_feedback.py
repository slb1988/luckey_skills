"""Local recall improvement ledger: explicit feedback, never automatic fact admission.

A later search evaluates matching feedback against its actual query and context.
No clicks/reads are monitored; absence is unknown, not a negative relevance label.
This standard-library module is also importable by offline regression runners.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

LEDGER_NAME = "recall-feedback.jsonl"


def record_feedback(state_dir: Path, record: dict) -> dict:
    for key in ("project_id", "query", "retrieval_id", "note"):
        if not isinstance(record.get(key), str) or not record[key].strip() or len(record[key]) > 4000:
            raise ValueError("feedback requires bounded " + key)
    if record.get("outcome") not in {"unverified", "helpful", "unhelpful"}:
        raise ValueError("explicit feedback outcome required")
    if record.get("actor") not in {"human", "agent"}:
        raise ValueError("explicit feedback actor required")
    for key in ("expected_signals", "expected_navigation"):
        values = record.get(key, [])
        if not isinstance(values, list) or len(values) > 16 or any(
            not isinstance(value, str) or not value.strip() or len(value) > 1000 for value in values
        ):
            raise ValueError("invalid " + key)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record = {**record, "schema_version": "recall-feedback/1", "recorded_at": now,
              "admission": "evaluation_only"}
    record["feedback_id"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:24]
    state_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(state_dir / LEDGER_NAME), os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


def _anchors(query: str) -> set[str]:
    # IDs/numbers alone cannot establish similar work; CJK bigrams support paraphrases.
    ascii_terms = {term.lower() for term in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", query)}
    chinese = {run[i:i+2] for run in re.findall(r"[\u3400-\u9fff]+", query) for i in range(len(run)-1)}
    return ascii_terms | chinese


def evaluate_feedback(record: dict, *, query: str, context: str) -> dict:
    normalize = lambda value: " ".join(value.lower().replace("\\", "/").split())
    query_text, context_text = normalize(query), normalize(context)
    return {
        "feedback_id": record["feedback_id"], "previous_retrieval_id": record["retrieval_id"],
        "outcome": record["outcome"], "actor": record["actor"], "admission": "evaluation_only",
        "missing_signals": [s for s in record.get("expected_signals", []) if normalize(s) not in query_text],
        "missing_navigation": [p for p in record.get("expected_navigation", []) if normalize(p) not in context_text],
        # Presence is NOT an answer-level judgment, path existence, or a proven fix.
        "answer_validation": "not_evaluated",
    }


def replay_feedback(state_dir: Path, *, project_id: str, query: str, context: str) -> list[dict]:
    path = state_dir / LEDGER_NAME
    try:
        # Bounded local I/O, no global/project expansion and no LLM/network call.
        with path.open("rb") as handle:
            size = handle.seek(0, 2)
            handle.seek(max(0, size - 1024 * 1024))
            if size > 1024 * 1024:
                handle.readline()
            lines = handle.read().decode("utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    current = _anchors(query)
    matches = []
    for line in reversed(lines):
        try:
            record = json.loads(line)
            if (record.get("schema_version") != "recall-feedback/1"
                    or record.get("project_id") != project_id
                    or record.get("admission") != "evaluation_only"):
                continue
            previous = _anchors(record["query"])
            common = current & previous
            signals = record.get("expected_signals") or []
            signal_hits = sum(signal.casefold() in query.casefold() for signal in signals)
            signal_match = signal_hits >= 2 and signal_hits / max(1, len(signals)) >= 0.5
            lexical_match = len(common) >= 2 and len(common) / max(1, min(len(current), len(previous))) >= 0.4
            if not (signal_match or lexical_match):
                continue
            matches.append(evaluate_feedback(record, query=query, context=context))
            if len(matches) >= 8:
                break
        except (KeyError, TypeError, ValueError):
            continue
    return matches

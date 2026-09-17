"""Bounded retrieval input, independent of the final 4000-character context budget.

No generated diagnoses: select complete original lines/whitespace-delimited units.
Keep task intent, then diagnostic/traceback and identifier lines ahead of log noise.
The Pi template mirrors this policy; both implementations have behavior tests.
"""
from __future__ import annotations

import re

QUERY_MAX_CHARS = 4000
OMITTED = "[… input omitted to fit query budget …]"
FAILURE = re.compile(r"error|exception|traceback|fail(?:ed|ure)?|not on client|not found|denied|报错|错误|失败", re.I)
IDENTIFIER = re.compile(r"--[\w-]+=|[\\/][\w.-]+|\b(?:build|change-list)\D*\d+", re.I)


def _units(text: str, budget: int) -> list[str]:
    """Oversized lines split at whitespace, never in a path/identifier."""
    result = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            continue
        if len(line) <= budget:
            result.append(line)
            continue
        part = ""
        for word in line.split():
            if len(part) + len(word) + 1 > budget:
                if part:
                    result.append(part)
                part = ""
            if len(word) <= budget:
                part = (part + " " + word).strip()
        if part:
            result.append(part)
    return result


def compact_query_context(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    room = max(0, budget - len(OMITTED) - 1)
    lines = _units(text, min(1000, room)) if room else []
    traceback_at = next((i for i, line in enumerate(lines) if "traceback" in line.lower()), len(lines))
    def score(index: int) -> int:
        line = lines[index]
        return (8 if FAILURE.search(line) else 0) + (4 if index >= traceback_at else 0) + (3 if IDENTIFIER.search(line) else 0) + (2 if index < 2 else 0)
    kept = {}
    seen = set()
    for index in sorted(range(len(lines)), key=lambda i: (-score(i), i)):
        line = lines[index]
        if line in seen or len(line) + 1 > room:
            continue
        kept[index] = line
        seen.add(line)
        room -= len(line) + 1
    return "\n".join([*(kept[i] for i in sorted(kept)), OMITTED]) if budget >= len(OMITTED) else ""


def build_recall_query(prompt: str, project_hint: str) -> tuple[str, dict]:
    selected = prompt.rsplit("=== TASK ===", 1)[-1].strip()
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in selected.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return "", {"input_chars": len(selected), "query_chars": 0, "max_chars": QUERY_MAX_CHARS, "compacted": False}
    # Keep the first task clause ahead of logs; overflow remains context, not lost.
    first = _units(lines[0], 1000)
    intent = first[0] if first else "[oversized task token omitted]"
    rest = "\n".join([*first[1:], *lines[1:]])
    prefix = "%s 任务: %s" % (project_hint[:128], intent)
    context = compact_query_context(rest, QUERY_MAX_CHARS - len(prefix) - len("\n上下文:\n"))
    query = prefix + ("\n上下文:\n" + context if context else "")
    return query, {"input_chars": len(selected), "query_chars": len(query), "max_chars": QUERY_MAX_CHARS,
                   "compacted": OMITTED in context or len(lines[0]) > 1000, "policy": "intent-diagnostic-lines/1"}

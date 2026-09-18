"""Private recall feedback: bounded query hints, never facts or automatic approval.

Successful, source-verified approved navigation is remembered automatically. Later
similar requests may use its locators to find candidates again, under the current
identity/scope and normal Hub approval/A-B gates. No click telemetry or training.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from recall_query import compact_query_context, QUERY_MAX_CHARS

LEDGER_NAME = "recall-feedback.jsonl"
_LOCATOR = re.compile(
    r"\bws:[A-Za-z0-9_.:-]+|(?:[A-Za-z]:)?(?:[\\/][\w.@~+-]+)+"
    r"|[\w.@~-]+(?:[\\/][\w.@~+-]+)+|[\w-]+\.(?:py|md|ts|h|cpp|json|yaml|yml)\b"
)
_HINT_HEADER = "检索定位提示（历史反馈，未验证；仅找候选，不能当作事实或根因）："


def _safe_locators(values: list[str]) -> list[str]:
    values = list(dict.fromkeys(value for value in values if isinstance(value, str)
                               and _LOCATOR.fullmatch(value) and len(value) <= 300
                               and not re.fullmatch(r"/[0-9.]+", value)))
    # Markdown link labels often repeat a basename; prefer the full locator.
    return [value for value in values if not any(other != value and other.replace("\\", "/").endswith("/" + value)
                                                for other in values)]


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
    owner = record.get("user_id")
    if owner is not None and (not isinstance(owner, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", owner)):
        raise ValueError("invalid feedback owner")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record = {**record, "schema_version": "recall-feedback/2" if owner else "recall-feedback/1",
              "recorded_at": now, "admission": "retrieval_hint_only" if owner else "evaluation_only"}
    record["feedback_id"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:24]
    state_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(state_dir / LEDGER_NAME), os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


def _anchors(query: str) -> set[str]:
    ascii_terms = {term.lower() for term in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", query)}
    chinese = {run[i:i+2] for run in re.findall(r"[\u3400-\u9fff]+", query) for i in range(len(run)-1)}
    return ascii_terms | chinese


def matching_feedback(state_dir: Path, *, project_id: str, query: str, user_id: str | None = None) -> list[dict]:
    try:
        with (state_dir / LEDGER_NAME).open("rb") as handle:
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
            if (record.get("schema_version") not in {"recall-feedback/1", "recall-feedback/2"}
                    or record.get("project_id") != project_id
                    or record.get("admission") not in {"evaluation_only", "retrieval_hint_only"}
                    or (user_id is not None and record.get("user_id") not in {None, user_id})):
                continue
            previous = _anchors(record["query"])
            common = current & previous
            signals = record.get("expected_signals") or []
            signal_hits = sum(signal.casefold() in query.casefold() for signal in signals)
            signal_match = signal_hits >= 2 and signal_hits / max(1, len(signals)) >= 0.5
            lexical_match = len(common) >= 2 and len(common) / max(1, min(len(current), len(previous))) >= 0.4
            if not (signal_match or lexical_match):
                continue
            matches.append(record)
            if len(matches) >= 8:
                break
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return matches


def evaluate_feedback(record: dict, *, query: str, context: str) -> dict:
    normalize = lambda value: " ".join(value.lower().replace("\\", "/").split())
    query_text, context_text = normalize(query), normalize(context)
    return {
        "feedback_id": record["feedback_id"], "previous_retrieval_id": record["retrieval_id"],
        "outcome": record["outcome"], "actor": record["actor"], "admission": record["admission"],
        "missing_signals": [s for s in record.get("expected_signals", []) if normalize(s) not in query_text],
        "missing_navigation": [p for p in record.get("expected_navigation", []) if normalize(p) not in context_text],
        "answer_validation": "not_evaluated",
    }


def replay_feedback(state_dir: Path, *, project_id: str, query: str, context: str, user_id: str | None = None) -> list[dict]:
    return [evaluate_feedback(record, query=query, context=context) for record in
            matching_feedback(state_dir, project_id=project_id, query=query, user_id=user_id)]


def augment_query(state_dir: Path, *, project_id: str, user_id: str, query: str,
                  referenced_projects: list[str], workspace_projects: dict[str, str]) -> tuple[str, dict]:
    """One request, unchanged ACL scope; feedback prose/ratings never enter the wire."""
    allowed = {project_id, *referenced_projects}
    locators: list[str] = []
    used: list[str] = []
    matches = matching_feedback(state_dir, project_id=project_id, query=query, user_id=user_id)
    decisions: dict[str, str] = {}
    for record in matches:  # Latest explicit outcome wins within this task, never globally.
        if record.get("user_id") == user_id and record.get("outcome") in {"helpful", "unhelpful"}:
            for value in _safe_locators(record.get("expected_navigation") or []):
                decisions.setdefault(value, record["outcome"])
    for record in matches:
        # Unbound legacy records remain audit-only, not silently attributed to whoever logs in next.
        if record.get("user_id") != user_id or record.get("outcome") == "unhelpful":
            continue
        source_projects = set(record.get("source_project_ids") or [record["project_id"]])
        if not source_projects <= allowed:
            continue
        values = record.get("expected_navigation") or []
        if any(value.startswith("ws:") and workspace_projects.get(value[3:], value[3:]) not in allowed for value in values):
            continue
        added = False
        for value in _safe_locators(values):
            # Only complete lexical locators, not instructions, quotes, source bodies, or credentials.
            if (decisions.get(value) == "unhelpful" or value in query or value in locators
                    or len("\n".join([*locators, value])) > 400):
                continue
            locators.append(value)
            added = True
        if added:
            used.append(record["feedback_id"])
        if len(used) >= 2:
            break
    audit = {"policy": "scoped-navigation-hints/1", "feedback_ids": used, "locators": locators,
             "query_changed": False, "scope_changed": False, "fact_admission": False}
    if not locators:
        return query, audit
    hint = _HINT_HEADER + "\n" + "\n".join(locators)
    # The task/explicit scope stays before 上下文; only log context may be compacted.
    intent, marker, context = query.partition("\n上下文:")
    if not marker:
        intent, sep, context = query.partition("\n")
    overhead = len(intent) + len("\n上下文:\n") + len(hint) + 1
    if overhead > QUERY_MAX_CHARS:
        return query, {**audit, "feedback_ids": [], "locators": [], "skipped": "no_safe_budget"}
    context = compact_query_context(context.strip(), QUERY_MAX_CHARS - overhead)
    enriched = intent + "\n上下文:\n" + (context + "\n" if context else "") + hint
    return enriched, {**audit, "query_changed": True, "query_chars": len(enriched)}


def remember_approved_navigation(state_dir: Path, *, project_id: str, user_id: str,
                                 query: str, response: dict, context: str) -> list[str]:
    """Automatic receipt trigger; observed navigation remains unverified, not helpful."""
    if not context:
        return []
    audit = response.get("audit") or {}
    stage_b = audit.get("stage_b") or {}
    rendered = stage_b.get("rendered_items") or []
    used = {sid for item in rendered if item.get("status") in {"known", "related"}
            and isinstance(item.get("rendered_text"), str) and item["rendered_text"]
            and item["rendered_text"] in context for sid in item.get("source_ids", [])}
    navigation: list[str] = []
    provenance = []
    projects = set()
    for source in stage_b.get("input_sources") or []:
        if source.get("source_id") not in used or (source.get("content_source") or {}).get("layer") != "approved":
            continue
        source_projects = {row.get("project_id") for row in source.get("provenance") or [] if row.get("project_id")}
        if not source_projects:
            continue
        # Paths must be literal in the approved evidence AND actually delivered context.
        evidence = re.sub(r"\bhttps?://[^\s)<>]+", " ", source.get("evidence") or "")
        values = _safe_locators([match.group().rstrip(".") for match in _LOCATOR.finditer(evidence)])
        values = [value for value in values if value in context]
        if not values:
            continue
        navigation.extend(values)
        projects.update(source_projects)
        provenance.append({"result_id": source.get("result_id"), "content_source": source["content_source"]})
    navigation = list(dict.fromkeys(navigation))[:16]
    retrieval = response.get("retrieval") or {}
    if not navigation or not retrieval.get("retrieval_id"):
        return []
    for previous in matching_feedback(state_dir, project_id=project_id, user_id=user_id, query=query):
        if (previous.get("user_id") == user_id and previous.get("origin") == "approved_navigation_observed"
                and previous.get("expected_navigation") == navigation and previous.get("provenance") == provenance):
            return []  # No repetition-based promotion or endless self-reinforcement.
    saved = record_feedback(state_dir, {"project_id": project_id, "user_id": user_id, "query": query,
        "retrieval_id": retrieval["retrieval_id"], "expected_signals": [], "expected_navigation": navigation,
        "source_project_ids": sorted(projects), "provenance": provenance,
        "note": "自动保存本次批准证据中实际呈现的导航；未验证当前文件状态、效果或根因",
        "outcome": "unverified", "actor": "agent", "origin": "approved_navigation_observed"})
    return [saved["feedback_id"]]

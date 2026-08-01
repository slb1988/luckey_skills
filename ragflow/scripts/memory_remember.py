#!/usr/bin/env python3
"""Curate RAGFlow memory entries and verify that retrieval changes."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import requests

DEFAULT_BASE_URL = "http://192.168.2.13:9386"
DEFAULT_MEMORY_ID = "c8ab35ca8cac11f19e4fdd2ab8bff472"
CURATOR_AGENT_ID = "ragflow-memory-curator"


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def find_project_env() -> Path:
    candidates = [Path.cwd() / ".env"]
    here = Path(__file__).resolve()
    candidates.extend(parent / ".env" for parent in here.parents)
    for candidate in candidates:
        if candidate.exists() and "RAGFLOW_TOKEN" in load_dotenv(candidate):
            return candidate
    raise FileNotFoundError("未找到包含 RAGFLOW_TOKEN 的项目 .env")


class RagflowMemory:
    def __init__(self, base_url: str, token: str, memory_id: str, timeout: int = 60):
        self.base = base_url.rstrip("/") + "/api/v1"
        self.memory_id = memory_id
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    @staticmethod
    def _json(response: requests.Response) -> dict[str, Any]:
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"RAGFlow API error: code={data.get('code')}, message={data.get('message')}")
        return data

    def config(self) -> dict[str, Any]:
        response = self.session.get(f"{self.base}/memories/{self.memory_id}/config", timeout=self.timeout)
        return self._json(response).get("data") or {}

    def search(self, query: str, threshold: float, keyword_weight: float, top_n: int) -> list[dict[str, Any]]:
        response = self.session.get(
            f"{self.base}/messages/search",
            params={
                "query": query,
                "memory_id": self.memory_id,
                "similarity_threshold": threshold,
                "keywords_similarity_weight": keyword_weight,
                "top_n": top_n,
            },
            timeout=self.timeout,
        )
        return self._json(response).get("data") or []

    def add(self, topic: str, content: str, session_id: str, user_id: str = "") -> None:
        response = self.session.post(
            f"{self.base}/messages",
            json={
                "memory_id": [self.memory_id],
                "agent_id": CURATOR_AGENT_ID,
                "session_id": session_id,
                "user_id": user_id,
                "user_input": topic,
                "agent_response": content,
            },
            timeout=self.timeout,
        )
        self._json(response)


def validate_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries = payload.get("entries")
    tests = payload.get("tests")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 5:
        raise ValueError("entries 必须包含 1～5 条记忆")
    if not isinstance(tests, list) or len(tests) < 2:
        raise ValueError("tests 至少需要 2 个验证查询")
    for item in entries:
        if not str(item.get("topic", "")).strip() or not str(item.get("content", "")).strip():
            raise ValueError("每条 entry 都必须包含 topic 和 content")
    for test in tests:
        expected = test.get("expected_any")
        if not str(test.get("query", "")).strip() or not isinstance(expected, list) or not expected:
            raise ValueError("每个 test 都必须包含 query 和非空 expected_any")
    return entries, tests


def compact_hit(hit: dict[str, Any], rank: int | None = None) -> dict[str, Any]:
    result = {
        "message_id": hit.get("message_id"),
        "message_type": hit.get("message_type"),
        "session_id": hit.get("session_id"),
        "source_id": hit.get("source_id"),
        "status": hit.get("status"),
        "content": hit.get("content", ""),
    }
    if rank is not None:
        result["rank"] = rank
    return result


def matching_new_hits(
    after: list[dict[str, Any]], baseline_ids: set[Any], session_id: str, expected_any: list[str]
) -> list[dict[str, Any]]:
    expected = [str(word).casefold() for word in expected_any]
    matches: list[dict[str, Any]] = []
    for rank, hit in enumerate(after, 1):
        content = str(hit.get("content") or "")
        is_new = hit.get("message_id") not in baseline_ids
        is_current = hit.get("session_id") == session_id
        has_expected = any(word in content.casefold() for word in expected)
        is_structured = hit.get("message_type") in {"semantic", "episodic", "procedural"}
        if is_new and is_current and has_expected and is_structured and hit.get("status", True):
            matches.append(compact_hit(hit, rank))
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="JSON payload path")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--memory-id", default=DEFAULT_MEMORY_ID)
    parser.add_argument("--poll-seconds", type=int, default=90)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--threshold", type=float, default=0.1)
    parser.add_argument("--keyword-weight", type=float, default=0.5)
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    entries, tests = validate_payload(payload)
    env_values = load_dotenv(find_project_env())
    token = os.environ.get("RAGFLOW_TOKEN") or env_values.get("RAGFLOW_TOKEN")
    base_url = args.base_url or os.environ.get("RAGFLOW_BASE_URL") or env_values.get("RAGFLOW_BASE_URL") or DEFAULT_BASE_URL
    if not token:
        raise RuntimeError("RAGFLOW_TOKEN 未配置")

    client = RagflowMemory(base_url, token, args.memory_id)
    config = client.config()
    enabled_types = set(config.get("memory_type") or [])
    required_types = {"raw", "semantic", "episodic", "procedural"}
    if not required_types.issubset(enabled_types):
        raise RuntimeError(f"Memory 类型配置不完整：{sorted(enabled_types)}")

    baseline: dict[str, list[dict[str, Any]]] = {}
    baseline_ids: dict[str, set[Any]] = {}
    for test in tests:
        query = test["query"]
        hits = client.search(query, args.threshold, args.keyword_weight, args.top_n)
        baseline[query] = [compact_hit(hit, rank) for rank, hit in enumerate(hits, 1)]
        baseline_ids[query] = {hit.get("message_id") for hit in hits}

    session_id = uuid.uuid4().hex
    for entry in entries:
        client.add(str(entry["topic"]).strip(), str(entry["content"]).strip(), session_id, str(payload.get("user_id", "")))

    deadline = time.monotonic() + args.poll_seconds
    test_results: list[dict[str, Any]] = []
    structured_types: set[str] = set()
    while True:
        test_results = []
        all_queries_passed = True
        structured_types = set()
        for test in tests:
            query = test["query"]
            after = client.search(query, args.threshold, args.keyword_weight, args.top_n)
            new_matches = matching_new_hits(after, baseline_ids[query], session_id, test["expected_any"])
            structured_types.update(
                str(hit["message_type"])
                for hit in new_matches
                if hit.get("message_type") in {"semantic", "episodic", "procedural"}
            )
            passed = bool(new_matches)
            all_queries_passed = all_queries_passed and passed
            test_results.append(
                {
                    "query": query,
                    "expected_any": test["expected_any"],
                    "passed": passed,
                    "baseline_hit_ids": sorted(x for x in baseline_ids[query] if x is not None),
                    "new_matches": new_matches,
                }
            )
        if (all_queries_passed and structured_types) or time.monotonic() >= deadline:
            break
        time.sleep(args.interval)

    overall_passed = all(result["passed"] for result in test_results) and bool(structured_types)
    report = {
        "passed": overall_passed,
        "memory": {"id": args.memory_id, "name": config.get("name"), "types": config.get("memory_type")},
        "session_id": session_id,
        "entries_submitted": len(entries),
        "structured_types_retrieved": sorted(structured_types),
        "tests": test_results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)

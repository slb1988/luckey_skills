#!/usr/bin/env python3
"""Re-distill rejected Orca sessions; default dry-run makes GET requests only."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from memory_hook import build_distilled_summary, is_noise_user_text, session_user_texts
from session_messages import (
    chat_hub_speakers_from_pairs,
    choose_session_result,
    extract_session_pairs,
    extract_worker_done_summary,
)

BASE_URL = "https://luckeyhome.site/memory-hub/"
AGENT_API = "agent-api"


class DownloadError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__("HTTP %s: %s" % (status, detail))
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("redirect refused: only the configured Memory Hub endpoint is allowed")


class Client:
    def __init__(self, api_key: str, user_id: str, *, apply: bool = False):
        self.api_key = api_key
        self.user_id = user_id
        self.apply = apply
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path: str, *, project_id: str = "memory-hub", user_id: str = "",
                body: dict | None = None, idempotency_key: str = "") -> tuple[int, bytes]:
        if path.startswith("/") or ".." in path.split("/") or ":" in path:
            raise ValueError("expected a relative Memory Hub API path")
        if body is not None and (not self.apply or path != AGENT_API + "/v1/memories"):
            raise RuntimeError("writes require --apply and the memories endpoint")
        headers = {
            "Authorization": "Bearer " + self.api_key,
            "X-User-Id": user_id or self.user_id,
            "X-Agent-Id": "pi",
            "X-Project-Id": project_id,
        }
        data = None
        if body is not None:
            headers.update({"Content-Type": "application/json", "Idempotency-Key": idempotency_key})
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(BASE_URL + path, data=data, headers=headers,
                                         method="POST" if body is not None else "GET")
        try:
            with self.opener.open(request, timeout=45) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            raise DownloadError(error.code, error.read(4096).decode("utf-8", errors="replace")) from error

    def get_json(self, path: str, **identity) -> dict:
        _, data = self.request(path, **identity)
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("expected JSON object")
        return value


def component(value) -> str:
    return urllib.parse.quote(str(value), safe="")


def created_at_key(item: dict) -> tuple[datetime, str]:
    value = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    return value.replace(tzinfo=value.tzinfo or timezone.utc), item["review_id"]


def rejected_reviews(client: Client) -> list[dict]:
    offset = 0
    matches = {}
    while True:
        page = client.get_json(
            "api/v1/review/intake?decision=rejected&decided_by=llm&limit=500&offset=%s" % offset
        )
        items = page["items"]
        if not items:
            break
        for item in items:
            if "派发模板" in (item.get("rationale") or ""):
                matches[item["review_id"]] = item
        offset += len(items)
        if offset >= page["total"]:
            break
    return sorted(matches.values(), key=created_at_key)


def decode_session(data: bytes) -> dict:
    if data.startswith(b"\x1f\x8b"):
        data = gzip.decompress(data)
    text = data.decode("utf-8-sig")
    try:
        payload = json.loads(text)
    except ValueError:
        payload = {"events": [json.loads(line) for line in text.splitlines() if line.strip()]}
    if isinstance(payload, dict) and ("events" in payload or "messages" in payload):
        return payload
    if isinstance(payload, dict) and "type" in payload:
        return {"events": [payload]}
    raise ValueError("unsupported session file: expected events, messages or JSONL")


def distill_session(payload: dict, memory: dict) -> dict:
    source = payload.get("source")
    source = source.get("agent") if isinstance(source, dict) else source
    source = source or memory.get("agent_id") or memory["session_id"].split(":", 1)[0]
    events = payload.get("events", [])
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise ValueError("invalid events array")
    pairs = extract_session_pairs(events, source=source)
    if not pairs:
        for message in payload.get("messages", []):
            if isinstance(message, dict) and message.get("role") in ("user", "assistant") and isinstance(message.get("content"), str):
                pairs.append((message["role"], message["content"]))
    _, first_user, last_user, last_assistant = session_user_texts(pairs)
    worker_result = extract_worker_done_summary(events)
    result, used_worker_done = choose_session_result(last_assistant, worker_result)
    has_goal = any(not is_noise_user_text(text) for text in (first_user, last_user))
    goal = first_user or last_user or "未提取到用户文本"
    distilled = build_distilled_summary(
        goal, last_user or goal, result or "未提取到助手最终文本", chat_hub_speakers_from_pairs(pairs)
    )[:16 * 1024]
    return {
        "distilled_content": distilled,
        "still_no_substantive_content": not (has_goal or result.strip()),
        "has_goal": has_goal,
        "has_result": bool(result.strip()),
        "used_worker_done": used_worker_done,
    }


def prepare_review(client: Client, review: dict, row: dict) -> tuple[dict, dict]:
    memory = client.get_json(AGENT_API + "/v1/memories/" + component(review["memory_id"]),
                             project_id=review["project_id"])
    for field in ("project_id", "user_id", "session_id", "session_version", "file_id"):
        if not memory.get(field):
            raise ValueError("memory is missing " + field)
    if memory.get("memory_type") != "session_summary":
        raise ValueError("memory is not a session_summary")
    identity = {"project_id": memory["project_id"], "user_id": memory["user_id"]}
    row.update(identity)
    row["old_preview"] = (memory.get("distilled_content") or "")[:120]
    version = client.get_json(AGENT_API + "/v1/sessions/" + component(memory["session_id"])
                              + "/versions/" + component(memory["session_version"]), **identity)
    full_file_id = version.get("full_file_id")
    file_id = full_file_id or memory["file_id"]
    row["full_download"] = "absent" if not full_file_id else "ok"
    try:
        _, data = client.request(AGENT_API + "/v1/files/" + component(file_id) + "/download", **identity)
    except (RuntimeError, OSError) as error:
        if not full_file_id or full_file_id == memory["file_id"]:
            raise
        row["full_download"] = "forbidden/fallback" if getattr(error, "status", None) == 403 else "failed/fallback"
        row["full_download_error"] = str(error)
        file_id = memory["file_id"]
        _, data = client.request(AGENT_API + "/v1/files/" + component(file_id) + "/download", **identity)
    row["downloaded_file_id"] = file_id
    distilled = distill_session(decode_session(data), memory)
    row.update({key: value for key, value in distilled.items() if key != "distilled_content"})
    row["new_preview"] = distilled["distilled_content"][:120]
    row["unchanged"] = distilled["distilled_content"] == memory.get("distilled_content")
    return memory, distilled


def apply_review(client: Client, review: dict, memory: dict, distilled: dict) -> tuple[int, dict]:
    # 幂等键绑定内容哈希：同内容重试幂等，内容改进后自动获得新键（避免 409 IDEMPOTENCY_CONFLICT）
    content_tag = hashlib.sha256(distilled["distilled_content"].encode("utf-8")).hexdigest()[:8]
    key = "rescue:%s:%s" % (review["review_id"], content_tag)
    body = {
        "schema_version": "memory-write/1",
        "agent_id": memory.get("agent_id") or "pi",
        "project_id": memory["project_id"],
        "session_id": memory["session_id"],
        "session_version": memory["session_version"],
        "file_id": memory["file_id"],
        "scope_type": memory["scope_type"],
        "memory_type": "session_summary",
        "distilled_content": distilled["distilled_content"],
        "summary": memory.get("summary"),
        "source_event_id": key,
        "dry_run": False,
    }
    status, data = client.request(AGENT_API + "/v1/memories", project_id=memory["project_id"],
                                user_id=memory["user_id"], body=body, idempotency_key=key)
    response = json.loads(data)
    if not isinstance(response, dict):
        raise ValueError("invalid memory write response")
    return status, response


def run(client: Client, *, apply: bool = False) -> dict:
    reviews = rejected_reviews(client)
    report = {"mode": "apply" if apply else "dry-run", "items": []}
    print("Matched %s rejected Orca session summaries" % len(reviews), flush=True)
    last_submission = None
    for index, review in enumerate(reviews, 1):
        row = {key: review[key] for key in ("review_id", "memory_id", "created_at", "project_id")}
        row.update(old_preview=(review.get("content_snapshot") or "")[:120], new_preview="",
                   still_no_substantive_content=None, status="failed")
        try:
            memory, distilled = prepare_review(client, review, row)
            row["status"] = "dry_run"
            if apply:
                if row.get("unchanged"):
                    row["status"] = "skipped_unchanged"
                    report["items"].append(row)
                    continue
                if row["still_no_substantive_content"]:
                    raise ValueError("no substantive content; submission withheld")
                if last_submission is not None:
                    time.sleep(max(0, 0.3 - (time.monotonic() - last_submission)))
                row["submitted"] = True
                try:
                    status, response = apply_review(client, review, memory, distilled)
                finally:
                    last_submission = time.monotonic()
                row.update(http_status=status, response=response, status="submitted")
                if status == 202 and response.get("deduplicated_from_memory_id") == review["memory_id"]:
                    raise ValueError("内容未变化：202 deduplicated to the original memory_id")
                if not 200 <= status < 300:
                    raise ValueError("unexpected write status %s" % status)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
            row.update(status="failed", error=str(error))
        report["items"].append(row)
        if index % 20 == 0 or index == len(reviews):
            print("Processed %s/%s" % (index, len(reviews)), flush=True)
    summary = Counter(total=len(reviews), substantive=0, still_empty=0, unknown=0,
                      submitted=0, accepted_202=0, failed=0, full_fallback=0, missing_result=0,
                      worker_done=0, skipped_unchanged=0)
    projects = {}
    errors = Counter()
    for row in report["items"]:
        content = row["still_no_substantive_content"]
        bucket = "unknown" if content is None else "still_empty" if content else "substantive"
        summary[bucket] += 1
        project = projects.setdefault(row["project_id"], Counter(total=0, substantive=0, still_empty=0, unknown=0))
        project["total"] += 1
        project[bucket] += 1
        summary["submitted"] += bool(row.get("submitted"))
        summary["accepted_202"] += row.get("http_status") == 202
        summary["failed"] += row["status"] == "failed"
        summary["full_fallback"] += row.get("full_download", "").endswith("/fallback")
        summary["missing_result"] += row.get("has_result") is False
        summary["worker_done"] += bool(row.get("used_worker_done"))
        summary["skipped_unchanged"] += row["status"] == "skipped_unchanged"
        if row.get("error"):
            errors[row["error"]] += 1
    report.update(summary=dict(summary), projects=projects, failures=dict(errors),
                  content_check="Non-noise goal or nonempty assistant/worker_done result; not a semantic quality verdict.")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="GET only (default)")
    mode.add_argument("--apply", action="store_true", help="resubmit serially; never approves reviews")
    parser.add_argument("--output", type=Path, help="default: /tmp/rescue-dryrun.json or /tmp/rescue-apply.json")
    args = parser.parse_args(argv)
    key = os.environ.get("MEMORY_HUB_API_KEY", "")
    user = os.environ.get("MEMORY_HUB_CLIENT_USER_ID", "")
    if not key or not user:
        parser.error("MEMORY_HUB_API_KEY and MEMORY_HUB_CLIENT_USER_ID are required")
    report = run(Client(key, user, apply=args.apply), apply=args.apply)
    output = args.output or Path("/tmp/rescue-apply.json" if args.apply else "/tmp/rescue-dryrun.json")
    with output.open("w", encoding="utf-8") as handle:
        os.chmod(output, 0o600)
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({key: report[key] for key in ("summary", "projects", "failures")}, ensure_ascii=False, indent=2))
    print("Report: %s" % output)
    return 1 if report["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

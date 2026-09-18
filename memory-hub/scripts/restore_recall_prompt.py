#!/usr/bin/env python3
"""Restore ONE legacy receipt from an explicit Pi user entry; no network or retrieval.

Require session identity and exact reconstructed query/hash agreement. Preserve the
original response/context bytes and keep an exclusive backup before atomic replace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from memory_hook import Config, markdown_fenced_lines, markdown_json_lines, recall_prompt_audit, recall_prompt_audit_lines
from recall_query import build_recall_query


def restore(receipt: Path, session: Path, entry_id: str, project_hint: str) -> dict:
    before = receipt.read_bytes()
    text = before.decode("utf-8")
    if "## 原始用户 prompt" in text:
        raise ValueError("receipt already has an input audit; refusing to overwrite")
    # Legacy v33 file format only. Never parse a model's summary as input.
    normalized = text.replace("\r\n", "\n")
    block = normalized.split("## 服务端完整响应（原样）\n\n```json\n", 1)[1].split("\n```", 1)[0]
    response = json.loads(block)
    client_block = normalized.split("## 客户端上下文与统计（JSON 审计）\n\n```json\n", 1)[1].split("\n```", 1)[0]
    hints = json.loads(client_block)["context_stats"].get("feedback_hints", {}).get("locators", [])
    source_bytes = session.read_bytes()
    lines = source_bytes.decode("utf-8").splitlines()
    header = json.loads(lines[0])
    if header.get("type") != "session" or f'- session_id: `{header["id"]}`' not in text:
        raise ValueError("session identity mismatch")
    entries = [(n, line, json.loads(line)) for n, line in enumerate(lines, 1)]
    found = [(n, line, row) for n, line, row in entries if row.get("id") == entry_id and row.get("type") == "message"]
    if len(found) != 1 or found[0][2].get("message", {}).get("role") != "user":
        raise ValueError("explicit user entry not found")
    number, entry_line, entry = found[0]
    content = entry["message"]["content"]
    if isinstance(content, list):
        # Do not invent joins for ambiguous multipart inputs.
        texts = [part["text"] for part in content if part.get("type") == "text"]
        if len(texts) != 1:
            raise ValueError("expected one original text block")
        raw = texts[0]
    elif isinstance(content, str):
        raw = content
    else:
        raise ValueError("no original input text")
    query, _ = build_recall_query(raw, project_hint)
    digest = lambda value: hashlib.sha256(value).hexdigest()
    if query != response["query"] or digest(query.encode()) != response["query_hash"]:
        raise ValueError("original input does not reproduce this receipt's query/hash")
    audit = recall_prompt_audit({"text": raw, "source": "recovered_pi_session_user_entry",
        "source_ref": {"path": str(session.resolve()), "session_id": header["id"], "entry_id": entry_id,
                       "line": number, "timestamp": entry.get("timestamp"),
                       "entry_sha256": digest(entry_line.encode()), "session_snapshot_sha256": digest(source_bytes)}},
        Config.from_environment())
    audit["recovery"] = {"original_receipt_sha256": digest(before), "query_reproduced": True,
                         "retrieval_rerun": False, "original_response_and_context_preserved": True}
    extra = "\n".join([*recall_prompt_audit_lines(audit), "## 实际检索 query（历史原请求）", "",
        *markdown_fenced_lines(query, "text"), "", *markdown_json_lines({"chars": len(query),
        "sha256": response["query_hash"], "retrieval_hints": hints, "hints_source": "original receipt feedback_hints"}), "", ""])
    # Addition only: original legacy body remains byte-for-byte intact, including its query.
    marker = "## 查询信息".encode()
    if before.count(marker) != 1:
        raise ValueError("ambiguous receipt sections")
    after = before.replace(marker, extra.encode("utf-8") + marker, 1)
    backup = receipt.with_suffix(receipt.suffix + ".before-prompt-audit.bak")
    with backup.open("xb") as handle:
        handle.write(before)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(backup, 0o600)
    fd, name = tempfile.mkstemp(dir=receipt.parent, prefix=".restore-recall-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(after)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        os.replace(name, receipt)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return {"receipt": str(receipt), "backup": str(backup), "input_chars": len(raw),
            "input_sha256": digest(raw.encode()), "query_chars": len(query),
            "context_chars": len(response.get("injection_context", "")), "retrieval_rerun": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--pi-session", type=Path, required=True)
    parser.add_argument("--entry-id", required=True)
    parser.add_argument("--project-hint", required=True)
    args = parser.parse_args()
    print(json.dumps(restore(args.receipt, args.pi_session, args.entry_id, args.project_hint), ensure_ascii=False))


if __name__ == "__main__":
    main()

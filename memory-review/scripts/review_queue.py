#!/usr/bin/env python3
"""memory-review: Memory Hub 关卡 2（抽取审核）队列的扫描与处置工具。

仅标准库。两条子命令：

  scan   拉取 open 队列 + 逐条详情，跑确定性质量检查，输出审核包（JSON + 表格）。
  apply  执行决策文件（removals → approve/reject，带 rationale 留痕）。--dry-run 预演。

认证（与 memory-hook 同一套身份）：
  MEMORY_HUB_API_KEY            必填（生产 Bearer）
  MEMORY_HUB_CLIENT_USER_ID     必填（默认 sunlaibing 从注册表环境变量继承）
  MEMORY_REVIEW_BASE_URL        可选，默认 https://luckeyhome.site/memory-hub
                                （dashboard BFF；**直连 Hub :9287 没有 /review 路由（404）**，本机直连用 http://10.77.77.6:9288）

决策文件格式（apply 的输入）：
{
  "removals":  [{"review_id": "...", "entities": ["name"], "edges": [{"source","name","target"}]}],
  "approvals": [{"review_id": "...", "content_mode": "curated|original",
                 "snapshot_token": "<审核时 detail/scan 返回的原值>", "rationale": "..."}],
  "rejections":[{"review_id": "...", "rationale": "..."}]
}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_BASE = "https://luckeyhome.site/memory-hub"

SCAN_LIMIT = 200   # open 队列单次请求上限；返回达到上限即覆盖未确定
DETAIL_WORKERS = 8  # 只读详情的有限并发上限；POST 不并发化

# 高置信敏感信息模式（宁漏勿错：命中只升级人工，不自动拒）
SENSITIVE_PATTERNS = [
    # sk- key：前置字符守卫防 task-management 类文件名误报；主体允许点号防漏报
    (re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_\-.]{20,}"), "API key 形态字符串"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "私钥材料"),
    (re.compile(r"(?i)\b(password|passwd|secret)\s*[:=]\s*['\"]?\S{6,}"), "口令赋值"),
    (re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"), "api_key 赋值"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-.]{20,}"), "Bearer token"),
]


# ---------------------------------------------------------------- HTTP 层


class Client:
    def __init__(self, base_url: str, api_key: str, user_id: str, agent_id: str, project_id: str):
        self.base = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "X-User-Id": user_id,
            "X-Agent-Id": agent_id,
            "X-Project-Id": project_id,
        }

    def _url(self, path: str) -> str:
        # base 已含 /memory-hub 前缀时，dashboard BFF 的 API 根是 <base>/api/v1；
        # 直连 Hub（:9287）时 API 根是 <base>/v1。
        if "/api/v1" in self.base or self.base.rstrip("/").endswith(":9287"):
            root = self.base if "/v1" in self.base else self.base + "/v1"
        else:
            root = self.base + "/api/v1"
        return root + path

    def get(self, path: str) -> dict:
        req = urllib.request.Request(self._url(path), headers=self.headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)

    def post(self, path: str, body: dict) -> tuple[int, dict]:
        headers = dict(self.headers, **{"Content-Type": "application/json"})
        req = urllib.request.Request(
            self._url(path), data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", "replace")
            try:
                return exc.code, json.loads(payload)
            except json.JSONDecodeError:
                return exc.code, {"raw_error": payload[:500]}


def make_client(args) -> Client:
    api_key = os.environ.get("MEMORY_HUB_API_KEY", "")
    if not api_key:
        sys.exit("MEMORY_HUB_API_KEY 未设置（注册表 HKCU\\Environment 应已持久化）")
    user_id = os.environ.get("MEMORY_HUB_CLIENT_USER_ID") or "sunlaibing"
    base = getattr(args, "base_url", None) or os.environ.get("MEMORY_REVIEW_BASE_URL") or DEFAULT_BASE
    return Client(base, api_key, user_id,
                  getattr(args, "agent_id", None) or "pi",
                  getattr(args, "project_id", None) or "ObsidianVault")


# ---------------------------------------------------------------- 确定性检查


def check_item(detail: dict) -> list[dict]:
    """对单条详情跑确定性检查，返回 flag 列表（agent 判断层的输入）。"""
    flags: list[dict] = []
    proposed = detail.get("proposed") or {}
    entities = proposed.get("entities") or []
    edges = proposed.get("edges") or []
    content = detail.get("distilled_content") or ""
    status = detail.get("status")
    if status in {"preview_pending", "preview_failed"}:
        flags.append({
            "check": status, "severity": "escalate",
            "detail": f"审核状态 {status}，preview_attempts={detail.get('preview_attempts')}；需核对预览生命周期",
        })

    token = detail.get("snapshot_token")
    if not isinstance(token, str) or not token.strip():
        flags.append({
            "check": "snapshot_missing", "severity": "escalate",
            "detail": "缺少服务端 snapshot_token，不能批准；需支持快照契约的服务端并重新扫描审核",
        })

    # 1) 自环边（LLM 预览常见畸形：source == target）
    for e in edges:
        if e.get("source") and e.get("source") == e.get("target"):
            flags.append({
                "check": "self_loop_edge",
                "severity": "remove",
                "detail": f"{e.get('source')} -[{e.get('name')}]-> {e.get('target')}",
                "remove_edge": {"source": e.get("source"), "name": e.get("name"), "target": e.get("target")},
            })

    # 2) 预览厚度
    if not entities and not edges:
        flags.append({"check": "empty_preview", "severity": "escalate",
                      "detail": "预览为空；curated 不可用，只能 original 或人工看正文"})
    elif not edges:
        flags.append({"check": "thin_preview", "severity": "suggest_original",
                      "detail": f"预览 {len(entities)} 实体 0 边；curated 渲染会很薄，建议 original"})

    # 3) 敏感信息（正文 + 全部 fact）
    haystack = content + "\n" + "\n".join(e.get("fact") or "" for e in edges)
    for pattern, label in SENSITIVE_PATTERNS:
        if pattern.search(haystack):
            flags.append({"check": "sensitive_pattern", "severity": "escalate",
                          "detail": f"命中敏感模式：{label}"})

    # 4) novelty 门禁状态
    novelty = detail.get("novelty") or {}
    if novelty:
        if novelty.get("status") != "completed":
            flags.append({"check": "novelty_not_completed", "severity": "escalate",
                          "detail": f"novelty 分析未完成：{novelty.get('status')}（批准会 fail-closed）"})
        elif novelty.get("admission") == "duplicate":
            flags.append({"check": "novelty_duplicate", "severity": "escalate",
                          "detail": "演进分析判 duplicate，需人工确认（acknowledge_novelty_warning）"})

    # 5) 内容过短（蒸馏正文几乎没有信息量）
    if len(content.strip()) < 80:
        flags.append({"check": "trivial_content", "severity": "escalate",
                      "detail": f"正文仅 {len(content.strip())} 字符，信息量存疑"})

    return flags


def suggest_decision(detail: dict, flags: list[dict]) -> dict:
    """基于确定性检查的默认建议；agent 判断层可以覆盖。无 escalate 且可自动处理时 auto=True。"""
    proposed = detail.get("proposed") or {}
    removals = [f["remove_edge"] for f in flags if f.get("remove_edge")]
    escalations = [f for f in flags if f["severity"] == "escalate"]
    if escalations:
        return {"action": "escalate", "auto": False,
                "reasons": [f["detail"] for f in escalations], "removals": removals}
    if removals:
        # 清掉畸形边后按预览厚度批准
        mode = "original" if any(f["severity"] == "suggest_original" for f in flags) else "curated"
        return {"action": "approve", "auto": True, "content_mode": mode,
                "removals": removals, "reasons": ["清除自环边后批准"]}
    if any(f["severity"] == "suggest_original" for f in flags):
        return {"action": "approve", "auto": True, "content_mode": "original",
                "removals": [], "reasons": ["预览过薄，按原蒸馏文批准"]}
    has_preview = bool(proposed.get("entities") or proposed.get("edges"))
    return {"action": "approve", "auto": True,
            "content_mode": "curated" if has_preview else "original",
            "removals": [], "reasons": ["确定性检查全过"]}


# ---------------------------------------------------------------- scan


def fetch_details(client, review_ids, progress=None):
    """有限并发拉取详情（只读）。返回 (按输入顺序的成功详情列表, {完整ID: 错误})；
    每个请求 ID 必居成功或错误集合之一，HTTP/解析失败不会变成“条目不在队列”。
    首版不自动重试，避免隐藏失败和放大不明等待。"""
    details: dict[str, dict] = {}
    errors: dict[str, str] = {}
    total = len(review_ids)
    if not total:
        return [], errors

    done = 0
    with ThreadPoolExecutor(max_workers=min(DETAIL_WORKERS, total)) as pool:
        futures = {pool.submit(client.get, f"/review/extraction/{rid}"): rid for rid in review_ids}
        for fut in as_completed(futures):
            rid = futures[fut]
            done += 1
            try:
                details[rid] = fut.result()
                if progress:
                    progress(done, total, rid, None)
            except Exception as exc:
                errors[rid] = f"{type(exc).__name__}: {exc}"
                if progress:
                    progress(done, total, rid, errors[rid])
    return [details[rid] for rid in review_ids if rid in details], errors


def build_packet_entry(d: dict) -> dict:
    flags = check_item(d)
    suggestion = suggest_decision(d, flags)
    proposed = d.get("proposed") or {}
    novelty = d.get("novelty") or {}
    return {
        **{field: d.get(field) for field in (
            "memory_id", "session_id", "session_version", "scope_type", "group_id",
            "status", "memory_status", "preview_attempts", "updated_at", "snapshot_token",
        )},
        "review_id": d["review_id"],
        "project_id": d.get("project_id"),
        "memory_type": d.get("memory_type"),
        "summary": d.get("summary"),
        "created_at": d.get("created_at"),
        "entity_count": len(proposed.get("entities") or []),
        "edge_count": len(proposed.get("edges") or []),
        "novelty": novelty,
        "distilled_content": d.get("distilled_content"),
        "proposed": proposed,
        "flags": flags,
        "suggestion": suggestion,
    }


def cmd_scan(args) -> int:
    client = make_client(args)
    t0 = time.monotonic()
    try:
        queue = client.get(f"/review/extraction?status=open&limit={SCAN_LIMIT}")
    except Exception as exc:
        print(f"队列列表请求失败：{type(exc).__name__}: {exc}；列表失败不能当作空队列，未产出审核包。",
              file=sys.stderr)
        return 1
    items = queue.get("items", [])
    ids = [it["review_id"] for it in items]
    coverage_certain = len(ids) < SCAN_LIMIT
    print(f"open 队列返回 {len(ids)} 条（单次请求 limit={SCAN_LIMIT}，非原子快照）。", flush=True)
    if not coverage_certain:
        print(f"⚠ 返回数量已达 limit={SCAN_LIMIT}：队列覆盖未确定，可能有更多 open 条目；"
              f"本次结果不能称为全队列扫描完成。", flush=True)

    def progress(done: int, total: int, rid: str, err) -> None:
        print(f"  [{done}/{total}] {rid} " + ("详情 OK" if err is None else f"详情失败：{err}"), flush=True)

    details, errors = fetch_details(client, ids, progress=progress)
    print(f"详情请求 {len(ids)}：成功 {len(details)}，失败 {len(errors)}，"
          f"耗时 {time.monotonic() - t0:.1f}s", flush=True)

    packet = [build_packet_entry(d) for d in details]
    out_path = args.output or "review_packet.json"
    if errors:
        diag = {"complete": False, "coverage_certain": coverage_certain,
                "requested": len(ids), "succeeded": len(details), "failed": len(errors),
                "errors": errors, "items": packet}
        diag_path = out_path + ".incomplete.json"
        with open(diag_path, "w", encoding="utf-8") as fh:
            json.dump(diag, fh, ensure_ascii=False, indent=1)
        print(f"部分详情失败（{len(errors)}/{len(ids)}）：不发布正式审核包；"
              f"诊断包（complete=false，含逐完整 ID 错误）已写 {diag_path}")
        print("失败 ID：" + ", ".join(errors))
        return 1

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(packet, fh, ensure_ascii=False, indent=1)

    auto = sum(1 for p in packet if p["suggestion"]["auto"])
    esc = len(packet) - auto
    print(f"open 队列 {len(packet)} 条：可自动处置 {auto}，需人工判断 {esc}")
    print(f"{'review':8s} {'project':24s} {'state/attempts':18s} {'ent/edge':9s} {'novelty':18s} 建议 / flags")
    for p in packet:
        nov = p["novelty"] or {}
        nov_s = f"{nov.get('status', '-')}/{nov.get('admission', '-')}"
        sg = p["suggestion"]
        act = sg["action"] + (f"({sg.get('content_mode', '')})" if sg["action"] == "approve" else "")
        flag_s = "; ".join(f["check"] for f in p["flags"]) or "-"
        attempts = p.get("preview_attempts")
        state_s = f"{p.get('status') or '-'}/{attempts if attempts is not None else '-'}"
        print(f"{p['review_id'][:8]:8s} {(p['project_id'] or '')[:24]:24s} {state_s:18s} "
              f"{p['entity_count']}/{p['edge_count']:<7d} {nov_s:18s} {act} | {flag_s}")
        print(f"         {(p['summary'] or '')[:80]}")
    print(f"\n审核包已写入 {out_path}——逐条阅读 proposed/distilled_content 做判断，"
          f"然后写决策文件用 apply 执行。")
    return 0


# ---------------------------------------------------------------- apply


def validate_decisions(decisions: dict) -> None:
    if not isinstance(decisions, dict):
        raise ValueError("决策文件必须是 JSON 对象")
    for key in ("removals", "approvals", "rejections"):
        items = decisions.get(key, [])
        if not isinstance(items, list):
            raise ValueError(f"{key} 必须是数组")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("review_id"), str) or not item["review_id"].strip():
                raise ValueError(f"{key} 每条必须包含非空 review_id")

    approved = set()
    for item in decisions.get("approvals", []):
        review_id = item["review_id"]
        token = item.get("snapshot_token")
        if not isinstance(token, str) or not token.strip():
            raise ValueError(f"APPROVE {review_id} 缺少有效 snapshot_token；必须复制已审核快照的原值，不能自动补取")
        if item.get("content_mode", "original") not in {"original", "curated"}:
            raise ValueError(f"APPROVE {review_id} 的 content_mode 必须为 original 或 curated")
        if review_id in approved:
            raise ValueError(f"重复 APPROVE {review_id}")
        approved.add(review_id)

    removed = {i["review_id"] for i in decisions.get("removals", []) if i.get("entities") or i.get("edges")}
    if approved & removed:
        raise ValueError("同条记忆不能在一份文件中 REMOVE 后 APPROVE；先清理，重新读取并审核，再用新 snapshot_token 批准")
    if approved & {i["review_id"] for i in decisions.get("rejections", [])}:
        raise ValueError("同条记忆不能同时 APPROVE 与 REJECT")


class ReceiptLedger:
    """（新接口）提交意图与回执的 JSONL 持久化：POST 前写意图，响应后立即追加回执。
    传输异常/超时记 kind=unknown（结果未知，不重发），不假定整批回滚。"""

    def __init__(self, path: str):
        self._fh = open(path, "a", encoding="utf-8")

    def record(self, **entry) -> None:
        entry.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        self._fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def close(self) -> None:
        self._fh.close()


def cmd_apply(args) -> int:
    with open(args.decisions, encoding="utf-8") as fh:
        decisions = json.load(fh)
    try:
        validate_decisions(decisions)
    except ValueError as exc:
        print(f"决策校验失败：{exc}；未发送任何请求。", file=sys.stderr)
        return 1
    client = make_client(args)
    dry = args.dry_run
    ledger = ReceiptLedger(args.receipt_file) if getattr(args, "receipt_file", None) and not dry else None

    failures = 0
    try:
        for rem in decisions.get("removals", []):
            body = {"entities": rem.get("entities", []), "edges": rem.get("edges", [])}
            if not body["entities"] and not body["edges"]:
                continue
            if dry:
                print(f"[dry-run] REMOVE {rem['review_id'][:8]}: {json.dumps(body, ensure_ascii=False)[:160]}")
                continue
            if ledger:
                ledger.record(kind="intent", action="remove", review_ids=[rem["review_id"]], body=body)
            try:
                status, resp = client.post(f"/review/extraction/{rem['review_id']}/remove", body)
            except Exception as exc:
                failures += 1
                if ledger:
                    ledger.record(kind="unknown", action="remove", review_ids=[rem["review_id"]],
                                  error=f"{type(exc).__name__}: {exc}")
                print(f"REMOVE {rem['review_id']} -> 请求异常（结果未知，不重发）：{exc}；已停止后续动作。")
                break
            if ledger:
                ledger.record(kind="receipt", action="remove", http_status=status,
                              results=[{"review_id": rem["review_id"],
                                        "status": "ok" if status == 200 else "failed"}],
                              **({} if status == 200 else {"error": json.dumps(resp, ensure_ascii=False)[:300]}))
            ok = status == 200
            failures += 0 if ok else 1
            print(f"REMOVE {rem['review_id']} -> {status}{'' if ok else ' ' + json.dumps(resp, ensure_ascii=False)[:200]}")
            if not ok:
                break

        if failures:
            print(f"清理失败 {failures} 项；已停止，未发送批准或拒绝请求。")
            return 1

        # 每组共用 action/mode/rationale，各 review 保留自己的已审核 token。
        tokens = {i["review_id"]: i["snapshot_token"] for i in decisions.get("approvals", [])}
        groups: dict[tuple, list[str]] = {}
        for item in decisions.get("approvals", []):
            key = ("approve", item.get("content_mode", "original"), item.get("rationale") or None)
            groups.setdefault(key, []).append(item["review_id"])
        for item in decisions.get("rejections", []):
            key = ("reject", None, item.get("rationale") or None)
            groups.setdefault(key, []).append(item["review_id"])

        counts = {"approved": 0, "rejected": 0, "already_processed": 0}
        unknown = 0
        for (action, mode, rationale), ids in groups.items():
            body = {"review_ids": ids, "action": action, "acknowledge_novelty_warning": False}
            if action == "approve":
                body["content_mode"] = mode or "original"
                body["expected_snapshot_tokens"] = {review_id: tokens[review_id] for review_id in ids}
            if rationale:
                body["rationale"] = rationale
            if dry:
                print(f"[dry-run] {action.upper()} x{len(ids)} mode={mode} rationale={str(rationale)[:60]}")
                continue
            if ledger:
                ledger.record(kind="intent", action=action, content_mode=mode, rationale=rationale,
                              review_ids=ids,
                              expected_snapshot_tokens=body.get("expected_snapshot_tokens"))
            try:
                status, resp = client.post("/review/extraction/actions", body)
            except Exception as exc:
                failures += 1
                unknown += 1
                if ledger:
                    ledger.record(kind="unknown", action=action, review_ids=ids,
                                  error=f"{type(exc).__name__}: {exc}")
                print(f"{action.upper()} 批量请求异常（{len(ids)} 条结果未知，不重发）：{exc}；已停止后续动作。")
                break
            results = resp.get("results", []) if isinstance(resp, dict) else []
            if ledger:
                ledger.record(kind="receipt", action=action, http_status=status, results=results,
                              **({} if results else {"error": json.dumps(resp, ensure_ascii=False)[:300]}))
            for r in results:
                st = r.get("status")
                ok = st in {"approved", "rejected", "already_processed"}
                if st in counts:
                    counts[st] += 1
                failures += 0 if ok else 1
                print(f"{action.upper()} {r.get('review_id', '?')} -> {st}"
                      + (f" | {r.get('error')}" if r.get("error") else ""))
                if st == "review_changed":
                    print("快照已变化：停止批准，重新 scan 并逐条审核；不会自动换 token 重试。")
            if not results:
                failures += 1
                unknown += 1
                print(f"{action.upper()} batch -> HTTP {status} {json.dumps(resp, ensure_ascii=False)[:300]}")
            elif status != 200:
                failures += 1
            if failures:
                print("已停止后续动作；保留已返回的逐项结果，不自动重试。")
                break

        tally = "，".join(f"{k}={v}" for k, v in counts.items() if v)
        if unknown:
            tally += f"，未知={unknown}"
        print("\n完成。" + ("（dry-run，未实际执行）" if dry else f"{tally or '无动作'}。失败 {failures} 项。"))
        return 1 if failures else 0
    finally:
        if ledger:
            ledger.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", help="dashboard BFF 或 Hub 根地址")
    parser.add_argument("--agent-id", help="X-Agent-Id（默认 pi）")
    parser.add_argument("--project-id", help="X-Project-Id（默认 ObsidianVault）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="拉取 open 队列并生成审核包")
    p_scan.add_argument("--output", "-o", help="审核包输出路径（默认 review_packet.json）")

    p_apply = sub.add_parser("apply", help="执行决策文件")
    p_apply.add_argument("decisions", help="决策 JSON 文件路径")
    p_apply.add_argument("--dry-run", action="store_true", help="只打印不执行")
    p_apply.add_argument("--receipt-file",
                         help="（新接口）JSONL 结构化回执：POST 前持久化提交意图，响应后追加逐项回执；"
                              "异常记 unknown 不重发")

    args = parser.parse_args()
    if args.command == "scan":
        return cmd_scan(args)
    return cmd_apply(args)


if __name__ == "__main__":
    sys.exit(main())

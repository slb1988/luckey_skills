#!/usr/bin/env python3
"""memory-review: Memory Hub 关卡 2（抽取审核）队列的扫描与处置工具。

仅标准库。两条子命令：

  scan   拉取 open 队列 + 逐条详情，跑确定性质量检查，输出审核包（JSON + 表格）。
  apply  执行决策文件（removals → approve/reject，带 rationale 留痕）。--dry-run 预演。

认证（与 memory-hook 同一套身份）：
  MEMORY_HUB_API_KEY            必填（生产 Bearer）
  MEMORY_HUB_CLIENT_USER_ID     必填（默认 sunlaibing 从注册表环境变量继承）
  MEMORY_REVIEW_BASE_URL        可选，默认 https://luckeyhome.site/memory-hub
                                （dashboard BFF；直连 Hub 用 http://10.77.77.6:9287，前缀自动处理）

决策文件格式（apply 的输入）：
{
  "removals":  [{"review_id": "...", "entities": ["name"], "edges": [{"source","name","target"}]}],
  "approvals": [{"review_id": "...", "content_mode": "curated|original", "rationale": "..."}],
  "rejections":[{"review_id": "...", "rationale": "..."}]
}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "https://luckeyhome.site/memory-hub"

# 高置信敏感信息模式（宁漏勿错：命中只升级人工，不自动拒）
SENSITIVE_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "API key 形态字符串"),
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


def cmd_scan(args) -> int:
    client = make_client(args)
    queue = client.get("/review/extraction?status=open&limit=200")
    items = queue.get("items", [])
    details = []
    for it in items:
        details.append(client.get(f"/review/extraction/{it['review_id']}"))

    packet = []
    for d in details:
        flags = check_item(d)
        suggestion = suggest_decision(d, flags)
        proposed = d.get("proposed") or {}
        novelty = d.get("novelty") or {}
        packet.append({
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
        })

    out_path = args.output or "review_packet.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(packet, fh, ensure_ascii=False, indent=1)

    auto = sum(1 for p in packet if p["suggestion"]["auto"])
    esc = len(packet) - auto
    print(f"open 队列 {len(packet)} 条：可自动处置 {auto}，需人工判断 {esc}")
    print(f"{'review':8s} {'project':24s} {'ent/edge':9s} {'novelty':18s} 建议 / flags")
    for p in packet:
        nov = p["novelty"] or {}
        nov_s = f"{nov.get('status', '-')}/{nov.get('admission', '-')}"
        sg = p["suggestion"]
        act = sg["action"] + (f"({sg.get('content_mode', '')})" if sg["action"] == "approve" else "")
        flag_s = "; ".join(f["check"] for f in p["flags"]) or "-"
        print(f"{p['review_id'][:8]:8s} {(p['project_id'] or '')[:24]:24s} "
              f"{p['entity_count']}/{p['edge_count']:<7d} {nov_s:18s} {act} | {flag_s}")
        print(f"         {(p['summary'] or '')[:80]}")
    print(f"\n审核包已写入 {out_path}——逐条阅读 proposed/distilled_content 做判断，"
          f"然后写决策文件用 apply 执行。")
    return 0


# ---------------------------------------------------------------- apply


def cmd_apply(args) -> int:
    with open(args.decisions, encoding="utf-8") as fh:
        decisions = json.load(fh)
    client = make_client(args)
    dry = args.dry_run

    failures = 0

    for rem in decisions.get("removals", []):
        body = {"entities": rem.get("entities", []), "edges": rem.get("edges", [])}
        if not body["entities"] and not body["edges"]:
            continue
        if dry:
            print(f"[dry-run] REMOVE {rem['review_id'][:8]}: {json.dumps(body, ensure_ascii=False)[:160]}")
            continue
        status, resp = client.post(f"/review/extraction/{rem['review_id']}/remove", body)
        ok = status == 200
        failures += 0 if ok else 1
        print(f"REMOVE {rem['review_id'][:8]} -> {status}{'' if ok else ' ' + json.dumps(resp, ensure_ascii=False)[:200]}")

    # 按 (action, content_mode, rationale) 分组批量调用，同组共享一次 rationale 留痕
    groups: dict[tuple, list[str]] = {}
    for item in decisions.get("approvals", []):
        key = ("approve", item.get("content_mode", "original"), item.get("rationale") or None)
        groups.setdefault(key, []).append(item["review_id"])
    for item in decisions.get("rejections", []):
        key = ("reject", None, item.get("rationale") or None)
        groups.setdefault(key, []).append(item["review_id"])

    for (action, mode, rationale), ids in groups.items():
        body = {"review_ids": ids, "action": action, "acknowledge_novelty_warning": False}
        if action == "approve":
            body["content_mode"] = mode or "original"
        if rationale:
            body["rationale"] = rationale
        if dry:
            print(f"[dry-run] {action.upper()} x{len(ids)} mode={mode} rationale={str(rationale)[:60]}")
            continue
        status, resp = client.post("/review/extraction/actions", body)
        results = resp.get("results", []) if isinstance(resp, dict) else []
        for r in results:
            ok = r.get("status") in {"approved", "rejected", "already_processed"}
            failures += 0 if ok else 1
            print(f"{action.upper()} {r.get('review_id', '?')[:8]} -> {r.get('status')}"
                  + (f" | {r.get('error')}" if r.get("error") else ""))
        if not results:
            failures += 1
            print(f"{action.upper()} batch -> HTTP {status} {json.dumps(resp, ensure_ascii=False)[:300]}")

    print("\n完成。" + ("（dry-run，未实际执行）" if dry else f"失败 {failures} 项。"))
    return 1 if failures else 0


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

    args = parser.parse_args()
    if args.command == "scan":
        return cmd_scan(args)
    return cmd_apply(args)


if __name__ == "__main__":
    sys.exit(main())

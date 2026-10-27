"""Read-only quality/latency baseline over local recall audit files.

Parses recall-results/<agent>/<project>/*.md (服务端完整响应 JSON) and prints one
Markdown report: latency, injection organization, gate kills by reason. Use the
same window and exclusions before/after a server change and append the summary
row to the iteration ledger (.claude/plans/MemoryHub召回质量迭代路线.md).

    python recall_audit_stats.py --since 20261020
    python recall_audit_stats.py --since 20261020 --hub-src D:/Github/memory-hub/src  # + anchor replay
    python recall_audit_stats.py --since 20261020 --export-cases cases.jsonl          # gate kills for labeling
    python recall_audit_stats.py --since 20261028 --metrics                            # 汇总 recall-metrics.jsonl（含失败率）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".local/state/memory-hub-hook/recall-results"
# Skill eval / isolated harness runs: 2026-10-20~27 they were 70% of all recall
# calls and almost always empty; mixing them in hides the real interactive numbers.
DEFAULT_EXCLUDE = ("dwa-iso", "skills", "isolated", "skill-creator", "tests")
_FULL = re.compile(r"## 服务端完整响应（原样）\s*```json\n(.*?)\n```", re.S)
_DURATION = re.compile(r"duration_ms: `(\d+)`")
_HEDGE = re.compile(r"截至会话结束|尚无实现确认|尚无确认|未获用户确认|尚无实施证据|仅为助手建议")
_LABEL = re.compile(r"^- (.{4,80}?)：", re.M)


def _pct(values: list, q: float):
    values = sorted(v for v in values if v is not None)
    return values[min(len(values) - 1, int(len(values) * q))] if values else None


def _sentences(context: str) -> list[str]:
    return [s.strip(" -…。；") for s in re.split(r"[。；…\n]", context) if len(s.strip()) >= 12]


def _near_dup_shingles(sentences: list[str]) -> int:
    """20-char shingles shared by two distinct sentences ≈ the same fact said twice."""
    seen: Counter = Counter()
    for sentence in set(sentences):
        for i in range(0, max(1, len(sentence) - 20), 10):
            seen[sentence[i:i + 20]] += 1
    return sum(1 for count in seen.values() if count > 1)


def load(root: Path, since: str, exclude: tuple[str, ...]):
    rows, skipped = [], Counter()
    for path in sorted(root.glob("*/*/*.md")):
        agent, project = path.parts[-3], path.parts[-2]
        if path.name[:len(since)] < since:
            continue
        if any(token in project for token in exclude):
            skipped[project] += 1
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = _FULL.search(text)
        if not match:
            continue
        try:
            response = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        duration = _DURATION.search(text)
        rows.append((path, agent, project, response, int(duration.group(1)) if duration else None))
    return rows, skipped


def analyse(rows, hub_src: str | None):
    replay = None
    if hub_src:
        sys.path.insert(0, hub_src)
        from memory_hub.application import retrieval_judge as replay  # noqa: PLC0415
    metrics: dict[str, list] = {k: [] for k in ("dur", "judge", "out_tokens", "chars")}
    counts: Counter = Counter()
    attempts: Counter = Counter()
    policies: Counter = Counter()
    anchor_sides: Counter = Counter()
    supersede_reasons: Counter = Counter()
    cases = []
    for path, agent, project, response, duration in rows:
        audit = response.get("audit") or {}
        stage_a = audit.get("stage_a") or {}
        context = response.get("injection_context") or ""
        counts["files"] += 1
        policies[response.get("policy_version")] += 1
        attempts[stage_a.get("attempts")] += 1
        metrics["dur"].append(duration)
        for call in stage_a.get("llm_calls") or []:
            if call.get("stage") == "judge":
                metrics["judge"].append(call.get("latency_ms"))
                metrics["out_tokens"].append((call.get("usage") or {}).get("output_tokens"))
        if (response.get("fusion") or {}).get("fallback"):
            counts["graph_fallback"] += 1
        if not context.strip():
            counts["empty"] += 1
            continue
        counts["nonempty"] += 1
        metrics["chars"].append(len(context))
        sentences = _sentences(context)
        labels = _LABEL.findall(context)
        counts["f_exact_dup"] += len(sentences) > len(set(sentences))
        counts["f_near_dup"] += _near_dup_shingles(sentences) > 0
        counts["f_hedge"] += bool(_HEDGE.search(context))
        counts["f_repeat_label"] += len(labels) > len(set(labels))
        counts["f_superseded_note"] += "较早记录" in context
        items = (audit.get("stage_b") or {}).get("items") or []
        counts["unknown_slots"] += sum(1 for item in items if item.get("status") == "unknown")
        judgments = stage_a.get("judgments") or []
        by_id = {j.get("result_id"): j for j in judgments}
        for judgment in judgments:
            conflict = judgment.get("conflict") or ""
            reason = None
            if "SUPERSEDES" in conflict:
                reason = "supersede"
                replaced = re.findall(r"[0-9a-f]{8}-[0-9a-f-]{27}", conflict)
                successor = by_id.get(replaced[0]) if replaced else None
                counts["supersede"] += 1
                counts["supersede_successor_missing"] += successor is None
                counts["supersede_successor_kept"] += bool(successor and (successor.get("rating") or 0) >= 2)
                # 无 evidence/槽位的候选本就进不了注入，只有「有用」的清零才是损失（10-24~27：73 次中 32 次）。
                useful = bool(judgment.get("evidence") and judgment.get("supports_slots"))
                counts["supersede_useful"] += useful
                if useful:
                    supersede_reasons[judgment.get("superseded_reason") or "unrecorded(<89ed110)"] += 1
            elif "可核验锚点" in conflict:
                reason = "anchor"
                counts["anchor"] += 1
                if replay is not None:
                    side = _anchor_side(replay, judgment, response.get("query") or "")
                    anchor_sides[side] += 1
            elif conflict:
                reason = "other"
                counts["other_conflict"] += 1
            if reason:
                relevance = judgment.get("task_relevance") or {}
                cases.append({
                    "file": f"{agent}/{project}/{path.name}", "rank": judgment.get("rank"),
                    "result_id": judgment.get("result_id"), "reason": reason,
                    "conflict": conflict[:200], "query": response.get("query") or "",
                    "task_anchor": relevance.get("task_anchor"),
                    "evidence_anchor": relevance.get("evidence_anchor"),
                    "task_relevance": relevance or None,
                    "evidence": judgment.get("evidence") or "", "label": None,
                })
    return metrics, counts, attempts, policies, anchor_sides, supersede_reasons, cases


def _anchor_side(rj, judgment: dict, query: str) -> str:
    """Which side of the relevance bridge fails today, and would 0.6 on the task side flip it."""
    relevance = judgment.get("task_relevance") or {}
    if rj.task_relevance_verified(judgment, query):
        return "passes_current_code"
    task, _ = rj.split_retrieval_query(query, [])

    def ratio(anchor, original):
        if not isinstance(anchor, str):
            return 0.0
        tokens, hay = rj._anchor_tokens(anchor), rj._normalize_quote(original)
        if rj._normalize_quote(anchor) in hay:
            return 1.0
        return sum(t in hay for t in tokens) / len(tokens) if len(tokens) >= 3 else 0.0

    task_ratio = ratio(relevance.get("task_anchor"), task)
    evidence_ratio = ratio(relevance.get("evidence_anchor"), judgment.get("evidence") or "")
    side = ("task" if task_ratio < 0.7 else "") + ("+evidence" if evidence_ratio < 0.7 else "")
    if side == "task" and task_ratio >= 0.6:
        side = "task(0.6-0.7)"
    return side.lstrip("+") or "kind/explanation"


def report(args, rows, skipped, result) -> str:
    metrics, counts, attempts, policies, anchor_sides, supersede_reasons, _ = result
    nonempty = counts["nonempty"] or 1
    lines = [
        f"# Recall audit baseline since {args.since}",
        "",
        f"- files {counts['files']}（排除评测/隔离 {sum(skipped.values())}：{dict(skipped.most_common(5))}）",
        f"- 空注入 {counts['empty']}，非空 {counts['nonempty']}；graph fallback {counts['graph_fallback']}",
        f"- policy：{dict(policies.most_common(3))}",
        "",
        "| 指标 | p50 | p90 |", "|---|---|---|",
        f"| 端到端 duration_ms | {_pct(metrics['dur'], .5)} | {_pct(metrics['dur'], .9)} |",
        f"| Stage A judge ms | {_pct(metrics['judge'], .5)} | {_pct(metrics['judge'], .9)} |",
        f"| judge output tokens | {_pct(metrics['out_tokens'], .5)} | {_pct(metrics['out_tokens'], .9)} |",
        f"| 注入字符 | {_pct(metrics['chars'], .5)} | {_pct(metrics['chars'], .9)} |",
        "",
        f"- Stage A attempts：{dict(attempts)}",
        "",
        "组织（占非空注入比例）：",
        f"- 近重复事实 {counts['f_near_dup']}/{nonempty}，完全重复句 {counts['f_exact_dup']}/{nonempty}，"
        f"槽位标题重复 {counts['f_repeat_label']}/{nonempty}，状态套话 {counts['f_hedge']}/{nonempty}",
        f"- unknown 槽位 {counts['unknown_slots']} 个",
        "",
        "门禁击杀（judgment 数）：",
        f"- SUPERSEDES 整条清零 {counts['supersede']}，其中有用候选 {counts['supersede_useful']}"
        f"（原因 {dict(supersede_reasons)}；替代者不在候选池 {counts['supersede_successor_missing']}，"
        f"替代者被放行 {counts['supersede_successor_kept']}）；部分保留「较早记录」出现于 {counts['f_superseded_note']} 份注入",
        f"- 锚点降级 {counts['anchor']}" + (f"：{dict(anchor_sides)}" if anchor_sides else "（加 --hub-src 拆分失败侧）"),
        f"- 其他 conflict {counts['other_conflict']}",
        "",
        "台账行：",
        "| 日期窗 | 版本 | n | 空注入 | e2e p50/p90 s | judge p50 s | out tok p50 | 近重复 | SUPERSEDES 有用清零 | 锚点降级 |",
        f"| {args.since}~ | <commit> | {counts['files']} | {counts['empty']} | "
        f"{(_pct(metrics['dur'], .5) or 0) / 1000:.0f}/{(_pct(metrics['dur'], .9) or 0) / 1000:.0f} | "
        f"{(_pct(metrics['judge'], .5) or 0) / 1000:.0f} | {_pct(metrics['out_tokens'], .5)} | "
        f"{counts['f_near_dup']}/{counts['nonempty']} | {counts['supersede_useful']} | {counts['anchor']} |",
    ]
    return "\n".join(lines)


def metrics_report(path: Path, since: str) -> str:
    """汇总客户端 recall-metrics.jsonl（每次召回一行，含失败）：md 审计看不到的错误率在这里。"""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("ts") or "").replace("-", "")[:len(since)] >= since:
            rows.append(row)
    lines = [f"# recall-metrics since {since}", ""]
    for origin in sorted({row.get("origin") or "unknown" for row in rows}):
        group = [row for row in rows if (row.get("origin") or "unknown") == origin]
        done = [row for row in group if row.get("outcome") != "error"]
        errors = Counter(row.get("error_code") or "unknown" for row in group if row.get("outcome") == "error")
        reasons: Counter = Counter()
        for row in group:
            reasons.update(row.get("supersede_useful_reasons") or {})
        lines += [
            f"## {origin}：{len(group)} 次，失败 {sum(errors.values())}（{100 * sum(errors.values()) / max(1, len(group)):.1f}%）",
            f"- 结果：{dict(Counter(row.get('outcome') for row in group))}；错误码：{dict(errors)}",
            f"- 端到端 p50/p90 {_pct([r.get('duration_ms') for r in done], .5)}/{_pct([r.get('duration_ms') for r in done], .9)} ms；"
            f"judge p50 {_pct([r.get('judge_ms') for r in done if r.get('judge_calls')], .5)} ms；"
            f"输出 token p50 {_pct([r.get('judge_out_tokens') for r in done if r.get('judge_calls')], .5)}",
            f"- resolver 降级 {sum(1 for r in group if r.get('resolver_degraded'))}；graph fallback "
            f"{sum(1 for r in group if r.get('graph_fallback'))}；注入行 p50 {_pct([r.get('context_lines') for r in done if r.get('context_chars')], .5)}",
            f"- SUPERSEDES 有用清零 {sum(reasons.values())} {dict(reasons)}，部分保留 {sum(r.get('supersede_partial') or 0 for r in group)}；"
            f"锚点降级 {sum(r.get('anchor_kills') or 0 for r in group)}",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--since", default="20261020", help="文件名前缀下界，如 20261020 或 20261024T05")
    parser.add_argument("--exclude", default=",".join(DEFAULT_EXCLUDE), help="project 目录名包含即排除，逗号分隔")
    parser.add_argument("--hub-src", help="memory-hub 仓库 src 目录：用当前代码重放锚点降级的失败侧")
    parser.add_argument("--export-cases", type=Path, help="把门禁击杀案例写成 JSONL（label 留空待人工标注）")
    parser.add_argument("--metrics", nargs="?", const=DEFAULT_ROOT.parent / "recall-metrics.jsonl", type=Path,
                        help="改为汇总客户端 recall-metrics.jsonl（含失败召回；按 origin 分组）")
    args = parser.parse_args()
    if args.metrics:
        print(metrics_report(args.metrics, args.since))
        return 0
    exclude = tuple(token for token in args.exclude.split(",") if token)
    rows, skipped = load(args.root, args.since, exclude)
    result = analyse(rows, args.hub_src)
    print(report(args, rows, skipped, result))
    if args.export_cases:
        with args.export_cases.open("w", encoding="utf-8") as handle:
            for case in result[-1]:
                handle.write(json.dumps(case, ensure_ascii=False) + "\n")
        print(f"\nexported {len(result[-1])} cases -> {args.export_cases}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

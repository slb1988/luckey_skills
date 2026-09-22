#!/usr/bin/env python3
"""批量批准驱动：显式已审核决策输入 + 同物理组串行门禁 + 结构化回执与安全恢复。

输入（新接口）：apply 决策 JSON 的顶层 approvals 结构，每项在 review_id / content_mode /
snapshot_token / rationale 之外必须带 memory_id / group_id 两个本地元数据字段，由生成决策的
人或 agent 从实际审核的同一 scan 包原样带入；驱动不联网补齐、不 rescan 换 token。
token 变化 / review_changed / memory 或物理组不一致一律转“待重审”，不自动放行、不重发。

用法：
    python drive_approvals.py DECISIONS.json --run-dir RUN_DIR [--base-url ... --agent-id ... --project-id ...]

run 目录（每次运行独立，不覆盖 skills 内文件与历史材料）：
    decisions.input.json           输入副本（固定本批范围，sha256 记入 state）
    state.json                     最小状态，原子更新；损坏时拒绝当空批重置
    round-NNN.decisions.json       逐轮提交载荷（审计用，追加新轮不覆盖旧轮）
    round-NNN.receipts.jsonl       apply 结构化回执（意图/逐项结果/unknown）
    round-NNN.apply.log            子进程输出（恢复后追加新轮，不覆盖）
    drive.log                      阶段日志（queue/detail/apply/verify/poll/finalize 与最后进展时间）
    stacks.txt                     长时间未推进时的线程栈转储（仅诊断；Python 不能强制取消底层等待）
    run.lock                       排他运行标记；陈旧标记不自动抢占，须人工确认旧父/子进程停止后删除

中断恢复：同一命令重跑即可——先回放回执并只读核对：已尝试项不重复审批，未尝试项不丢失；
仅当原审核 token、memory/物理组仍匹配时才继续执行未尝试项。一次 open 不是未提交证明。

退出码：0 本批已对账结束；1 输入/用法错误；2 存在等待超时/待重审项；3 存在未知提交结果；
4 读取或记录失败（含运行记录冲突）。
"""
from __future__ import annotations

import argparse
import faulthandler
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
RQ = os.path.join(SKILL_DIR, "review_queue.py")

spec = importlib.util.spec_from_file_location("review_queue", RQ)
rq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rq)

POLL_INTERVAL = 20          # 轮询节奏（秒）
WAIT_BUDGET = 15 * 60       # 有限等待预算（单调时钟），到期间输出阻塞明细并非零退出
APPLY_TIMEOUT = 600         # apply 子进程边界
STALL_DUMP_AFTER = 180      # 无推进栈转储阈值（秒）

ACTIVE = {"pending", "submitted_unknown", "wait_indexed"}


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def log_line(run_dir: str, phase: str, msg: str) -> None:
    """阶段日志：只记 ID/状态/耗时，不输出凭证或正文。"""
    line = f"{_ts()} [{phase}] {msg}"
    print(line, flush=True)
    with open(os.path.join(run_dir, "drive.log"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def save_state(run_dir: str, state: dict) -> None:
    state["saved_at"] = _ts()
    tmp = os.path.join(run_dir, "state.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, os.path.join(run_dir, "state.json"))


def load_state(run_dir: str) -> dict:
    with open(os.path.join(run_dir, "state.json"), encoding="utf-8") as fh:
        state = json.load(fh)
    if not isinstance(state, dict) or not isinstance(state.get("items"), list):
        raise ValueError("state.json 结构不完整")
    return state


def acquire_lock(run_dir: str) -> bool:
    try:
        with open(os.path.join(run_dir, "run.lock"), "x", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "started": _ts()}, fh)
        return True
    except FileExistsError:
        return False


def release_lock(run_dir: str) -> None:
    try:
        os.remove(os.path.join(run_dir, "run.lock"))
    except OSError:
        pass


class Watchdog:
    """长时间未推进时把线程栈写入 stacks.txt（仅诊断，不承诺能取消底层等待）。"""

    def __init__(self, run_dir: str, after: float):
        self._fh = open(os.path.join(run_dir, "stacks.txt"), "a", encoding="utf-8")
        self._fh.write(f"\n--- {_ts()} watchdog armed after={after}s ---\n")
        self._fh.flush()
        faulthandler.dump_traceback_later(after, file=self._fh)

    def cancel(self) -> None:
        faulthandler.cancel_dump_traceback_later()
        self._fh.close()


def validate_input(decisions: dict) -> None:
    """驱动侧输入校验（在 review_queue.validate_decisions 之上追加必填元数据）。"""
    rq.validate_decisions(decisions)
    if decisions.get("removals") or decisions.get("rejections"):
        raise ValueError("驱动只执行 approvals；removals/rejections 请先用 review_queue.py apply 分阶段处理")
    approvals = decisions.get("approvals") or []
    if not approvals:
        raise ValueError("approvals 为空；空批不是完成条件")
    for item in approvals:
        for field in ("memory_id", "group_id", "rationale"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(
                    f"APPROVE {item.get('review_id')} 缺少必填元数据 {field}；"
                    "须从实际审核的同一 scan 包原样带入，驱动不联网补齐")


def build_client(args):
    return rq.make_client(args)


def read_detail(client, review_id: str):
    """只读详情；返回 (detail, error)。"""
    try:
        return client.get(f"/review/extraction/{review_id}"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def parse_receipt_files(run_dir: str):
    """回放全部 round receipts：返回 (意图中的完整ID集合, {完整ID: 最后一次 result})。
    崩溃瞬间截断的尾行跳过，但绝不能据此把记录当空批。"""
    intents: set[str] = set()
    results: dict[str, dict] = {}
    for name in sorted(os.listdir(run_dir)):
        if not name.endswith(".receipts.jsonl"):
            continue
        with open(os.path.join(run_dir, name), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ids = entry.get("review_ids") or []
                if entry.get("kind") == "intent":
                    intents.update(ids)
                elif entry.get("kind") == "receipt":
                    for r in entry.get("results") or []:
                        if r.get("review_id"):
                            results[r["review_id"]] = r
                elif entry.get("kind") == "unknown":
                    for rid in ids:
                        results.setdefault(rid, {"status": "unknown"})
    return intents, results


def correspondence_problem(item: dict, detail: dict):
    """决策元数据与当前详情的对应关系；不一致或缺失返回原因（须重审），一致返回 None。"""
    for field in ("memory_id", "group_id"):
        current = detail.get(field)
        if not current:
            return f"当前详情缺少 {field}，对应关系无法确认"
        if current != item[field]:
            return f"{field} 不一致（决策 {item[field]} / 当前 {current}）"
    if detail.get("status") in {"approved", "rejected"}:
        return None
    token = detail.get("snapshot_token")
    if not token:
        return "当前详情缺少 snapshot_token，快照对应无法确认"
    if token != item["snapshot_token"]:
        return "snapshot_token 已变化（预览重建或并发修改），须重新审核"
    return None


def poll_until_indexed(item: dict, client, run_dir: str) -> str:
    """等对应 memory indexed（同组门禁释放的唯一依据；hub_only 不放行）。
    有限等待（单调时钟 + WAIT_BUDGET），返回 done/timeout。"""
    deadline = time.monotonic() + WAIT_BUDGET
    while True:
        detail, err = read_detail(client, item["review_id"])
        ms = detail.get("memory_status") if detail else None
        rs = detail.get("status") if detail else None
        log_line(run_dir, "poll", f"{item['review_id']} memory_status={ms} review_status={rs}"
                                  + (f" err={err}" if err else ""))
        if ms == "indexed":
            return "done"
        if time.monotonic() >= deadline:
            return "timeout"
        time.sleep(POLL_INTERVAL)


def verify_item(item: dict, client, run_dir: str, phase: str = "verify") -> None:
    """只读核对并更新状态：approved→wait_indexed/done；rejected→skipped_terminal；
    仍 open 或读取失败 → 保持原未知状态，不重发。"""
    detail, err = read_detail(client, item["review_id"])
    if err:
        item["note"] = f"只读核对失败：{err}；保持原状态，不重发"
        log_line(run_dir, phase, f"{item['review_id']} 核对失败：{err}")
        return
    rs, ms = detail.get("status"), detail.get("memory_status")
    log_line(run_dir, phase, f"{item['review_id']} 核对：review={rs} memory={ms}")
    if rs == "approved":
        item["state"] = "done" if ms == "indexed" else "wait_indexed"
        item["note"] = item.get("note") or "核对已批准"
    elif rs == "rejected":
        item["state"] = "skipped_terminal"
        item["attribution"] = "concurrent"
        item["note"] = "核对已被拒绝（并发/先前终态，非本次动作）"
    else:
        item["note"] = f"核对仍为 {rs}：一次 open 不是未提交证明，保持未知不重发"


def apply_result(item: dict, status, client, run_dir: str, ours: bool) -> None:
    """按完整 ID 归因逐项回执。ours=该 ID 在本次提交意图内。"""
    if status == "approved":
        item["state"] = "wait_indexed"
        item["attribution"] = "receipt" if ours else "concurrent"
        item["note"] = "本次批准已受理，待 indexed" if ours else "回执 approved"
    elif status == "already_processed":
        item["note"] = "already_processed：只读核对最终状态，不计本次动作"
        verify_item(item, client, run_dir)
        if item["state"] in {"wait_indexed", "done", "skipped_terminal"}:
            item["attribution"] = "concurrent"
    elif status == "review_changed":
        item["state"] = "needs_rereview"
        item["note"] = "快照已变化：不自动换 token/重发；重新审核后生成新决策"
    else:
        item["state"] = "submitted_unknown"
        item["note"] = f"回执状态 {status}（未知/失败），不自动重发；只读核对"


def run_apply_round(batch: list, args, client, run_dir: str, round_no: int) -> str | None:
    run_dir = os.path.abspath(run_dir)
    round_path = os.path.join(run_dir, f"round-{round_no:03d}.decisions.json")
    receipt_path = os.path.join(run_dir, f"round-{round_no:03d}.receipts.jsonl")
    payload = {"removals": [], "rejections": [], "approvals": [
        {"review_id": it["review_id"], "content_mode": it["content_mode"],
         "snapshot_token": it["snapshot_token"], "rationale": it["rationale"]} for it in batch]}
    with open(round_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    log_line(run_dir, "apply", f"round {round_no} 提交 {len(batch)} 条：" +
             ", ".join(f"{it['review_id']}({it['group_id']},{it['content_mode']})" for it in batch))

    cmd = [sys.executable, RQ]
    for flag in ("base_url", "agent_id", "project_id"):
        val = getattr(args, flag, None)
        if val:
            cmd += ["--" + flag.replace("_", "-"), val]
    cmd += ["apply", round_path, "--receipt-file", receipt_path]

    watchdog = Watchdog(run_dir, STALL_DUMP_AFTER)
    timed_out = False
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=SKILL_DIR, timeout=APPLY_TIMEOUT)
        out = (proc.stdout or "") + (proc.stderr or "")
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        out, rc, timed_out = "", None, True
    finally:
        watchdog.cancel()
    with open(os.path.join(run_dir, f"round-{round_no:03d}.apply.log"), "a", encoding="utf-8") as fh:
        fh.write(out or "")
    log_line(run_dir, "apply", f"round {round_no} 子进程结束 rc={rc}"
                               + ("（超时：有意图无回执的项按未知处理，不重发）" if timed_out else ""))

    intents, results = parse_receipt_files(run_dir)
    for it in batch:
        rid = it["review_id"]
        if rid in results:
            apply_result(it, results[rid].get("status"), client, run_dir, ours=True)
        elif rid in intents:
            it["state"] = "submitted_unknown"
            it["attribution"] = "unknown-verified"
            it["note"] = "提交意图已持久化但无回执：结果未知，不重发；只读核对"
            verify_item(it, client, run_dir)
        # 无意图的项保持 pending，但本轮必须停下，不能把子进程失败当进展。
    unattempted = [it["review_id"] for it in batch
                   if it["review_id"] not in intents and it["review_id"] not in results]
    if unattempted:
        log_path = os.path.join(run_dir, f"round-{round_no:03d}.apply.log")
        return f"apply rc={rc}，{len(unattempted)} 项无提交记录；停止新增提交，请检查 {log_path}"
    return None


def resume_reconcile(state: dict, client, run_dir: str) -> None:
    """恢复：回放回执 + 只读核对。已尝试项不重复审批，未尝试项不丢失。"""
    intents, results = parse_receipt_files(run_dir)
    if not intents and not results:
        return
    for it in state["items"]:
        if it["state"] not in ACTIVE:
            continue
        rid = it["review_id"]
        if rid in results:
            apply_result(it, results[rid].get("status"), client, run_dir, ours=True)
        elif rid in intents:
            it["state"] = "submitted_unknown"
            it["attribution"] = "unknown-verified"
            it["note"] = "恢复：有意图无回执，只读核对不重发"
            verify_item(it, client, run_dir)
        else:
            it["state"] = "pending"  # 未尝试；组头轮转时会重新核对 token/组对应关系


def finalize(state: dict, run_dir: str, execution_error: str | None = None) -> int:
    """汇总退出：本批已对账结束 / 等待或待重审 / 未知结果 / 读取失败；后三类非零退出。
    不做末尾全队列 rescan。"""
    buckets: dict[str, list] = {k: [] for k in
                                ("done_receipt", "done_verified", "done_concurrent", "skipped_terminal",
                                 "needs_rereview", "submitted_unknown", "waiting", "read_failed")}
    for it in state["items"]:
        st = it["state"]
        if st == "done":
            buckets[{"receipt": "done_receipt", "unknown-verified": "done_verified"}.get(
                it.get("attribution"), "done_concurrent")].append(it)
        elif st == "skipped_terminal":
            buckets["skipped_terminal"].append(it)
        elif st == "needs_rereview":
            buckets["needs_rereview"].append(it)
        elif st == "submitted_unknown":
            buckets["submitted_unknown"].append(it)
        elif st in ACTIVE:
            key = "read_failed" if str(it.get("note") or "").startswith("读取失败") else "waiting"
            buckets[key].append(it)

    lines = ["===== 汇总 ====="]
    if execution_error:
        lines.append("执行错误：" + execution_error)
    labels = [
        ("done_receipt", "本次批准回执 → indexed"),
        ("done_verified", "未知回执核对后已批准（不计本次回执）"),
        ("done_concurrent", "并发/先前已批准 → indexed（非本次动作）"),
        ("skipped_terminal", "并发/先前终态（非本次动作）"),
        ("needs_rereview", "待重审（token 变化/对应不一致/review_changed）"),
        ("submitted_unknown", "未知提交结果（暂停，不重发）"),
        ("waiting", "等待/阻塞（preview_pending 或等待超时）"),
        ("read_failed", "读取失败（保留待核，不记 skip/完成）"),
    ]
    for key, label in labels:
        rows = buckets[key]
        if not rows:
            continue
        lines.append(f"{label}：{len(rows)}")
        lines += [f"  {i['review_id']}  {i.get('note') or ''}".rstrip() for i in rows]
    if execution_error or buckets["read_failed"]:
        code = 4
    elif buckets["submitted_unknown"]:
        code = 3
    elif buckets["needs_rereview"] or buckets["waiting"]:
        code = 2
    else:
        code = 0
    lines.insert(1, "结论：" + ("本批已对账结束" if code == 0 else
                 "存在读取/记录失败" if code == 4 else
                 "存在未知提交结果" if code == 3 else "存在等待/待重审项"))
    lines.append(f"最后进展时间：{state.get('last_progress', '-')}")
    for line in lines:
        log_line(run_dir, "finalize", line)
    return code


def run_drive(state: dict, args, client, run_dir: str) -> int:
    state.setdefault("last_progress", _ts())
    progress_clock = time.monotonic()

    def progressed():
        state["last_progress"] = _ts()
        return time.monotonic()

    while True:
        items = state["items"]
        if not any(it["state"] in ACTIVE for it in items):
            return finalize(state, run_dir)

        # 1) 在途项等 indexed（同组下一条的唯一放行依据；hub_only 不放行）
        for it in [i for i in items if i["state"] == "wait_indexed"]:
            if poll_until_indexed(it, client, run_dir) == "done":
                it["state"] = "done"
                progress_clock = progressed()
                save_state(run_dir, state)
            else:
                it["note"] = f"等待 indexed 超过 {WAIT_BUDGET}s（hub_only 不放行）；已停止新增提交"
                save_state(run_dir, state)
                return finalize(state, run_dir)

        # 2) 未知提交结果只读核对（不重发）
        for it in [i for i in items if i["state"] == "submitted_unknown"]:
            verify_item(it, client, run_dir)
            if it["state"] != "submitted_unknown":
                progress_clock = progressed()
        save_state(run_dir, state)

        # 3) 组头分类：连续检查各组头部；缺席 open 列表不 pop，按完整 ID 直读详情核实
        heads = []
        busy = {i["group_id"] for i in items if i["state"] in {"wait_indexed", "submitted_unknown"}}
        seen = set()
        for it in items:
            g = it["group_id"]
            if it["state"] == "pending" and g not in busy and g not in seen:
                seen.add(g)
                heads.append(it)

        batch = []
        if heads:
            try:
                queue = client.get(f"/review/extraction?status=open&limit={rq.SCAN_LIMIT}")
                open_ids = {x["review_id"] for x in queue.get("items", [])}
                cov = "覆盖确定" if len(open_ids) < rq.SCAN_LIMIT else "覆盖未确定（已达 limit）"
                log_line(run_dir, "queue", f"open 列表 {len(open_ids)} 条（{cov}）")
            except Exception as exc:
                open_ids = None
                log_line(run_dir, "queue",
                         f"open 列表读取失败：{type(exc).__name__}: {exc}；继续按完整 ID 直读组头核实")
            watchdog = Watchdog(run_dir, STALL_DUMP_AFTER)
            try:
                details, errors = rq.fetch_details(
                    client, [h["review_id"] for h in heads],
                    progress=lambda done, total, rid, err: log_line(
                        run_dir, "detail", f"[{done}/{total}] {rid} " + (f"失败：{err}" if err else "读取完成")))
            finally:
                watchdog.cancel()
            by_id = {d["review_id"]: d for d in details}
            for h in heads:
                rid = h["review_id"]
                d = by_id.get(rid)
                if d is None:
                    h["note"] = f"读取失败：{errors.get(rid)}"
                    log_line(run_dir, "detail", f"{rid} 读取失败：{errors.get(rid)}（保留待核，不记 skip/完成）")
                    continue
                rs, ms = d.get("status"), d.get("memory_status")
                where = "在 open 列表" if (open_ids is not None and rid in open_ids) else "缺席 open 列表，已定点直读"
                log_line(run_dir, "detail", f"{rid} {where}：review={rs} memory={ms}")
                problem = correspondence_problem(h, d)
                if problem:
                    h["state"] = "needs_rereview"
                    h["note"] = problem
                    progress_clock = progressed()
                elif rs == "review" or (rs == "preview_failed" and h["content_mode"] == "original"):
                    batch.append(h)
                elif rs == "approved":
                    h["state"] = "done" if ms == "indexed" else "wait_indexed"
                    h["attribution"] = "concurrent"
                    h["note"] = "核对已批准（并发/先前终态，非本次动作）"
                    progress_clock = progressed()
                elif rs == "rejected":
                    h["state"] = "skipped_terminal"
                    h["attribution"] = "concurrent"
                    h["note"] = "核对已拒绝（并发/先前终态，非本次动作）"
                    progress_clock = progressed()
                else:
                    h["note"] = f"当前 status={rs}，等待预览或人工"
            save_state(run_dir, state)

        # 4) 本轮每组最多一条可执行项提交
        if batch:
            state["rounds"] = state.get("rounds", 0) + 1
            execution_error = run_apply_round(batch, args, client, run_dir, state["rounds"])
            if any(it["state"] != "pending" for it in batch):
                progress_clock = progressed()
            save_state(run_dir, state)
            if execution_error:
                return finalize(state, run_dir, execution_error=execution_error)
            continue

        # 5) 全部暂不可执行：有限等待（单调时钟 + 预算），不空批早退
        if not any(it["state"] in ACTIVE for it in state["items"]):
            return finalize(state, run_dir)
        if time.monotonic() - progress_clock >= WAIT_BUDGET:
            log_line(run_dir, "finalize", f"无推进超过 {WAIT_BUDGET}s，输出阻塞明细")
            return finalize(state, run_dir)
        remaining = [i["review_id"] for i in state["items"] if i["state"] in ACTIVE]
        log_line(run_dir, "poll", f"暂无可执行项：{len(remaining)} 条待推进（{', '.join(remaining)}），"
                                  f"{POLL_INTERVAL}s 后重查；最后进展 {state['last_progress']}")
        time.sleep(POLL_INTERVAL)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", help="dashboard BFF 或 Hub 根地址")
    parser.add_argument("--agent-id", help="X-Agent-Id（默认 pi）")
    parser.add_argument("--project-id", help="X-Project-Id（默认 ObsidianVault）")
    parser.add_argument("decisions", help="已审核批准决策 JSON（顶层 approvals，每项含 memory_id/group_id）")
    parser.add_argument("--run-dir", required=True,
                        help="本次运行目录（状态/回执/日志）；已有 state.json 时按恢复流程继续")
    args = parser.parse_args(argv)

    with open(args.decisions, "rb") as fh:
        raw = fh.read()
    input_sha = hashlib.sha256(raw).hexdigest()
    try:
        decisions = json.loads(raw.decode("utf-8"))
        validate_input(decisions)
    except ValueError as exc:
        print(f"输入校验失败：{exc}；未发送任何请求。", file=sys.stderr)
        return 1

    os.makedirs(args.run_dir, exist_ok=True)
    if not acquire_lock(args.run_dir):
        print("run.lock 已存在：另一驱动可能仍在运行。陈旧标记不自动抢占——"
              "确认旧父/子进程已停止后人工删除该标记再恢复。", file=sys.stderr)
        return 4
    try:
        state_path = os.path.join(args.run_dir, "state.json")
        if os.path.exists(state_path):
            try:
                state = load_state(args.run_dir)
            except (ValueError, OSError) as exc:
                print(f"state.json 损坏或不可读（{exc}）：不当空批重置；保留现场，请人工核对。",
                      file=sys.stderr)
                return 4
            if state.get("input_sha256") != input_sha:
                print("决策输入与本 run 记录不一致：固定输入不可中途更换；新批次请用新 run 目录。",
                      file=sys.stderr)
                return 4
            # 轮次编号接续已落盘文件，恢复后追加而非覆盖
            existing = [int(n[6:9]) for n in os.listdir(args.run_dir)
                        if n.startswith("round-") and n.endswith(".decisions.json")]
            state["rounds"] = max(existing, default=0)
            log_line(args.run_dir, "resume", "恢复运行：回放回执并只读核对已尝试项")
        else:
            state = {"run_id": uuid.uuid4().hex[:12], "created": _ts(), "input_sha256": input_sha,
                     "rounds": 0,
                     "items": [{"review_id": a["review_id"], "memory_id": a["memory_id"],
                                "group_id": a["group_id"], "content_mode": a.get("content_mode", "original"),
                                "rationale": a["rationale"], "snapshot_token": a["snapshot_token"],
                                "state": "pending", "attribution": None, "note": ""}
                               for a in decisions["approvals"]]}
            with open(os.path.join(args.run_dir, "decisions.input.json"), "wb") as fh:
                fh.write(raw)
            save_state(args.run_dir, state)

        client = build_client(args)
        resume_reconcile(state, client, args.run_dir)
        save_state(args.run_dir, state)
        return run_drive(state, args, client, args.run_dir)
    finally:
        release_lock(args.run_dir)


if __name__ == "__main__":
    sys.exit(main())

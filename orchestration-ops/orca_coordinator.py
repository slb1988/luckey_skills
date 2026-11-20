#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orca-coordinator — Orca 编排外挂薄封装：dispatch/wait/ack/settle/usage + 成本账单。

设计契约（见 ObsidianVault .claude/plans/Orca编排token优化与改造路径.md）：
- 只调 orca 公开 CLI + 读本地 session jsonl，不改 Orca，官方升级零耦合
- wait 绝不自动 ack；settle 校验 taskId+dispatchId 后按 --reuse/--retain/--release 收尾
- usage 按 session 内容中的 task_/ctx_ id 归因（cwd slug+时间窗仅作候选过滤），歧义报 unknown
- 每次调用记日志（~/.orca-coordinator/logs/），usage 产出账单（~/.orca-coordinator/bills/）
"""
import argparse, datetime, json, os, re, subprocess, sys, time

HOME = os.path.join(os.path.expanduser("~"), ".orca-coordinator")
PI_SESSIONS = os.path.join(os.path.expanduser("~"), ".pi", "agent", "sessions")
CODEX_SESSIONS = os.path.join(os.path.expanduser("~"), ".codex", "sessions")
ORCA = os.environ.get("ORCA_CLI_COMMAND", "orca")
WAIT_TYPES = "worker_done,escalation,question"


def log_line(text):
    os.makedirs(os.path.join(HOME, "logs"), exist_ok=True)
    path = os.path.join(HOME, "logs", datetime.date.today().strftime("%Y%m%d") + ".log")
    with open(path, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), text))


def run_orca(args, timeout_ms=None):
    """调 orca CLI，分离 stdout/stderr（心跳在 stderr），返回 (rc, stdout, stderr)。"""
    cmd = [ORCA] + args
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=(timeout_ms / 1000 + 60) if timeout_ms else 300)
    hb = len(re.findall(r'"_(?:keepalive|heartbeat)"', p.stderr))
    log_line("orcacall rc=%d %.1fs hb=%d :: %s" % (p.returncode, time.time() - t0, hb,
                                                   " ".join(a if len(a) < 60 else a[:57] + "..." for a in args)))
    return p.returncode, p.stdout, p.stderr


def run_orca_json(args, timeout_ms=None):
    rc, out, err = run_orca(args, timeout_ms)
    if rc != 0:
        die("orca 调用失败 rc=%d: %s\n%s" % (rc, " ".join(args), err[-500:]))
    # stdout 末段为最终 JSON（可能多行），从第一个 { 起整体解析
    i = out.find("{")
    if i < 0:
        die("orca 输出无 JSON: %s" % " ".join(args))
    return json.loads(out[i:])


def die(msg, rc=1):
    print("[orca-coordinator] ERROR: %s" % msg, file=sys.stderr)
    sys.exit(rc)


def save_json(run_id, kind, name, obj):
    d = os.path.join(HOME, "runs", run_id, kind)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


# ---------- dispatch ----------

def cmd_dispatch(a):
    with open(a.spec_file, encoding="utf-8") as f:
        spec = f.read()
    args = ["orchestration", "worker-start", "--spec", spec, "--worktree", a.worktree, "--json"]
    if a.terminal:
        args += ["--terminal", a.terminal]
    else:
        args += ["--agent", a.agent]
    if a.task:
        args += ["--task", a.task]
    if a.retry_of:
        args += ["--retry-of", a.retry_of]
    if a.run:
        args += ["--run", a.run]
    receipt = run_orca_json(args, timeout_ms=120000)
    res = receipt.get("result", {})
    run_id = res.get("runId") or a.run or "unknown-run"
    save_json(run_id, "specs", os.path.basename(a.spec_file).replace(".txt", ""), {"spec": spec})
    save_json(run_id, "receipts", "start-%d" % int(time.time()), receipt)
    # dispatchId：先全文 regex，找不到再按终端 handle 查 worker-list
    m = re.search(r"ctx_[0-9a-f]{12}", json.dumps(receipt))
    term = None
    for e in res.get("effects", []):
        if e.get("kind") == "terminal":
            term = e.get("id")
    dispatch_id = m.group(0) if m else None
    if not dispatch_id and term:
        wl = run_orca_json(["orchestration", "worker-list", "--run", run_id, "--json"])
        for w in wl.get("result", {}).get("workers", []):
            if w.get("terminal") == term or w.get("terminalHandle") == term:
                dispatch_id = w.get("dispatchId")
    out = {"runId": run_id, "dispatchId": dispatch_id, "terminal": term,
           "stage": (res.get("stage") or {}), "receipt_saved": True}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if not dispatch_id:
        print("[orca-coordinator] WARN: dispatchId 未解析到，用 worker-list --run 核实", file=sys.stderr)


# ---------- wait / ack ----------

def cmd_wait(a):
    rc, out, err = run_orca(["orchestration", "check", "--wait", "--types", WAIT_TYPES,
                             "--timeout-ms", str(a.timeout_ms), "--json"],
                            timeout_ms=a.timeout_ms)
    if rc != 0:
        die("check --wait rc=%d\n%s" % (rc, err[-500:]))
    i = out.find("{")
    if i < 0:
        print("[orca-coordinator] 无事件（可能被其他消费者取走）")
        return
    batch = json.loads(out[i:])
    res = batch.get("result", {})
    # 原样呈现整批（不裁业务内容），提醒逐条处理后显式 ack
    print(json.dumps(res, ensure_ascii=False, indent=2))
    n = res.get("count", 0)
    did = res.get("deliveryId")
    print("[orca-coordinator] 批次 %s 共 %d 条；逐条处理完后执行: ack %s" % (did, n, did),
          file=sys.stderr)


def cmd_ack(a):
    r = run_orca_json(["orchestration", "check", "--ack", a.delivery_id, "--json"])
    print(json.dumps(r.get("result", {}), ensure_ascii=False))


# ---------- settle ----------

def cmd_settle(a):
    wl = run_orca_json(["orchestration", "worker-list", "--include-remote", "--json"])
    rows = wl.get("result", {}).get("workers", [])
    w = next((x for x in rows if x.get("dispatchId") == a.dispatch), None)
    if not w:
        die("worker-list 找不到 dispatch %s" % a.dispatch)
    proj = w.get("projection", {})
    outcome = proj.get("outcome") or w.get("outcome")
    stage = (proj.get("stage") or {})
    if outcome == "in_progress" and not a.force:
        die("dispatch 仍 in_progress（stage=%s），拒绝收尾；确认已 worker_done 或加 --force" % stage)
    if a.mode == "release":
        r = run_orca_json(["orchestration", "worker-release", "--dispatch", a.dispatch, "--json"])
    elif a.mode == "retain":
        r = run_orca_json(["orchestration", "worker-retain", "--dispatch", a.dispatch, "--json"])
    else:  # reuse：只报告终端 handle，后续 dispatch --terminal 复用
        term = w.get("terminal") or w.get("terminalHandle")
        print(json.dumps({"reuse_terminal": term, "dispatchId": a.dispatch,
                          "hint": "dispatch --terminal %s" % term}, ensure_ascii=False))
        return
    print(json.dumps(r.get("result", {}), ensure_ascii=False))


# ---------- usage ----------

def norm_slug(path):
    return "--" + re.sub(r"[^A-Za-z0-9_]", "-", path).strip("-") + "--"

def ws_path(ws_id):
    return ws_id.split("::", 1)[1] if "::" in (ws_id or "") else (ws_id or "")

def iter_session_files():
    """产出 (agent, path)：pi 按 slug 目录、codex 按日期目录，全部候选。"""
    if os.path.isdir(PI_SESSIONS):
        for slug in os.listdir(PI_SESSIONS):
            d = os.path.join(PI_SESSIONS, slug)
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                if fn.endswith(".jsonl"):
                    yield "pi", os.path.join(d, fn)
    if os.path.isdir(CODEX_SESSIONS):
        for root, _dirs, files in os.walk(CODEX_SESSIONS):
            for fn in files:
                if fn.endswith(".jsonl"):
                    yield "codex", os.path.join(root, fn)

ORCA_INTRO = "You are working inside Orca, a multi-agent IDE."
DISPATCH_INTRO = re.compile(
    r"^\s*(?:Please carry out this task from my Orca coordinator by following the brief I pasted below\.\s*)?"
    r"(?:<pasted_content\b[^>]*>\s*)?" + re.escape(ORCA_INTRO)
)
TASK_LABEL = re.compile(r"(?im)^Your task ID is:\s*(task_[0-9a-f]{12})\b")
DISPATCH_LABEL = re.compile(r"(?im)^Your dispatch ID is:\s*(ctx_[0-9a-f]{12})\b")
DISPATCH_PAIR = re.compile(r"--task-id\s+(task_[0-9a-f]{12})\s+--dispatch-id\s+(ctx_[0-9a-f]{12})\b")


def assignment_ids(event):
    if event.get("type") == "message":
        msg = event.get("message") or {}
    elif event.get("type") == "response_item":
        msg = event.get("payload") or {}
    else:
        return None
    if msg.get("role") != "user":
        return None
    content = msg.get("content") or ""
    if isinstance(content, list):
        content = "\n".join(b["text"] for b in content if isinstance(b, dict)
                            and b.get("type") in ("text", "input_text") and isinstance(b.get("text"), str))
    if not isinstance(content, str) or not DISPATCH_INTRO.match(content):
        return None
    # The task brief may quote OTHER assignments. Only Orca's own header is evidence.
    header = content.partition("=== TASK ===")[0]
    tasks = set(TASK_LABEL.findall(header))
    dispatches = set(DISPATCH_LABEL.findall(header))
    for task, dispatch in DISPATCH_PAIR.findall(header):
        tasks.add(task)
        dispatches.add(dispatch)
    if len(tasks) == len(dispatches) == 1:
        return tasks.pop(), dispatches.pop()
    return None, None  # Recognizable new assignment, but no safe owner for subsequent calls.


def empty_usage():
    return {"calls": 0, "input": 0, "cacheRead": 0, "output": 0, "cost": 0.0}


def add_call(totals, agent, event, seen):
    if agent == "pi" and event.get("type") == "message":
        msg = event.get("message") or {}
        if msg.get("role") != "assistant":
            return
        usage, call_id = msg.get("usage"), event.get("id")
        fields = ("input", "cacheRead", "output")
    elif agent == "codex" and event.get("type") == "token_usage_record":
        payload = event.get("payload") or {}
        usage, call_id = payload.get("usage"), payload.get("response_id")
        fields = ("input_tokens", "cached_input_tokens", "output_tokens")
    else:
        return
    if not isinstance(usage, dict) or not usage or (call_id and call_id in seen):
        return
    if call_id:
        seen.add(call_id)
    totals["calls"] += 1
    for name, field in zip(("input", "cacheRead", "output"), fields):
        totals[name] += usage.get(field) or 0
    if agent == "pi":
        cost = usage.get("cost")
        totals["cost"] += (cost.get("total") or 0) if isinstance(cost, dict) else (cost or 0)


def json_event(line):
    try:
        event = json.loads(line)
        return event if isinstance(event, dict) else {}
    except ValueError:
        return {}  # Sessions may still be appending their last line.


def session_usage(agent, path, expected):
    segments, seen, active = {}, set(), None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if active is None and ORCA_INTRO not in line:
                continue
            event = json_event(line)
            stamp = event.get("timestamp")
            assignment = assignment_ids(event) if ORCA_INTRO in line else None
            if assignment is not None:
                task, dispatch = assignment
                active = None
                if dispatch in expected and task == expected[dispatch]:
                    active = segments.setdefault(dispatch, {
                        "agent": agent, "path": path, "last": stamp, "usage": empty_usage(),
                    })
            if active is not None:
                if stamp:
                    active["last"] = stamp
                add_call(active["usage"], agent, event, seen)
    return segments


def usage_by_dispatch(workers):
    expected, scopes = {}, {}
    for w in workers:
        did, tid = w.get("dispatchId"), w.get("taskId")
        if not did:
            continue
        if did in expected and expected[did] != tid:
            expected[did] = None  # Conflicting observations cannot establish ownership.
        else:
            expected[did] = tid
        workspace = w.get("workspace") or ""
        if isinstance(workspace, dict):
            workspace = workspace.get("id") or workspace.get("path") or ""
        slug = norm_slug(ws_path(workspace)).casefold() if workspace else ""
        scopes.setdefault(did, set()).add(slug)
    candidates = {did: [] for did in expected}
    if expected:
        for agent, path in iter_session_files():
            slug = os.path.basename(os.path.dirname(path)).casefold()
            wanted = {d: t for d, t in expected.items() if t and
                      (agent != "pi" or "" in scopes[d] or slug in scopes[d])}
            if not wanted:
                continue
            try:
                segments = session_usage(agent, path, wanted)
            except OSError:
                continue
            for did, segment in segments.items():
                candidates[did].append(segment)
    return expected, candidates


def coordinator_usage(path, run_id, last, worker_files):
    if not path or not last or not os.path.isfile(path) or os.path.realpath(path) in worker_files:
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        start = next((stamp for line in f if run_id in line
                      if (stamp := json_event(line).get("timestamp"))), None)
        if not start or start > last:
            return None
        f.seek(0)
        totals, seen = empty_usage(), set()
        for line in f:
            if '"usage"' in line:
                event = json_event(line)
                if start <= (event.get("timestamp") or "") <= last:
                    add_call(totals, "pi", event, seen)
    return {**totals, "since": start, "session": os.path.basename(path)}


def cache_hit(totals, agent):
    inputs = totals["input"] + (totals["cacheRead"] if agent == "pi" else 0)
    return round(100 * totals["cacheRead"] / inputs, 1) if inputs else 0


def cmd_usage(a):
    wl = run_orca_json(["orchestration", "worker-list", "--run", a.run_id,
                        "--include-remote", "--json"])
    expected, candidates = usage_by_dispatch(wl.get("result", {}).get("workers", []))
    rows, totals, ends = [], empty_usage(), []
    for did, tid in expected.items():
        row = {"dispatch": did, "task": tid}
        matches = candidates[did]
        if len(matches) != 1:
            reason = "ambiguous-sessions" if matches else "no-matching-preamble"
            rows.append({**row, **empty_usage(), "agent": "?", "cost": None,
                         "attribution": "unknown", "note": "unknown: " + reason})
            continue
        match = matches[0]
        agent, usage = match["agent"], match["usage"]
        if match["last"]:
            ends.append(match["last"])
        rows.append({**row, **usage, "agent": agent, "session": os.path.basename(match["path"]),
                     "hit": cache_hit(usage, agent), "cost": round(usage["cost"], 3) if agent == "pi" else None,
                     "attribution": "matched", "note": "exact-task-dispatch"})
        for k in totals:
            totals[k] += usage[k]
    worker_files = {os.path.realpath(m["path"]) for matches in candidates.values() for m in matches}
    coord = coordinator_usage(a.coordinator_session or os.environ.get("PI_SESSION_FILE"), a.run_id,
                              max(ends, default=None), worker_files)
    if coord:
        for k in totals:
            totals[k] += coord[k]
        coord.update(hit=cache_hit(coord, "pi"), cost=round(coord["cost"], 3))
    unknown = sum(r["attribution"] == "unknown" for r in rows)
    bill = {"run_id": a.run_id, "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "objective": a.objective, "workers": rows, "coordinator": coord,
            "totals": {**totals, "cost": round(totals["cost"], 3)},
            "unknown_workers": unknown,
            "cost_note": f"cost 仅含可归属的 Pi 用量；Codex 无金额记录；{unknown} 个 unknown worker 未计入" +
                         ("；协调者未计入" if coord is None else "")}
    os.makedirs(os.path.join(HOME, "bills"), exist_ok=True)
    with open(os.path.join(HOME, "bills", a.run_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(bill, f, ensure_ascii=False, indent=2)
    # 趋势 jsonl：同 run_id 去重写最新（重跑不产生重复行）
    trend = os.path.join(HOME, "bills", "bills.jsonl")
    old = []
    if os.path.exists(trend):
        with open(trend, encoding="utf-8") as f:
            old = [l for l in f if l.strip() and json.loads(l).get("run_id") != a.run_id]
    old.append(json.dumps({"run_id": a.run_id, "ts": bill["generated"],
                           "objective": a.objective, **bill["totals"], "unknown_workers": unknown,
                           "coordinator_counted": coord is not None}, ensure_ascii=False))
    with open(trend, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(old) + "\n")
    print(render_bill(bill))

def render_bill(b):
    lines = ["# 编排账单 %s" % b["run_id"], "", "目标: %s" % (b.get("objective") or "-"), "",
             "| 角色 | agent | 调用 | input | cacheRead | output | 命中% | cost$ | 备注 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in b["workers"]:
        if r.get("attribution") == "unknown":
            lines.append("| worker %s | ? | — | — | — | — | — | 未计 | %s |" % (r["dispatch"][4:12], r["note"]))
            continue
        lines.append("| worker %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            (r["dispatch"] or "?")[4:12], r.get("agent", "?"), r["calls"],
            format(r["input"], ","), format(r["cacheRead"], ","), format(r["output"], ","),
            r.get("hit", "-"), r["cost"] if r["cost"] is not None else "未计", r.get("note", "")))
    c = b.get("coordinator")
    if c:
        lines.append("| coordinator | pi | %s | %s | %s | %s | %s | %.3f | since %s |" % (
            c["calls"], format(c["input"], ","), format(c["cacheRead"], ","),
            format(c["output"], ","), c["hit"], c["cost"], (c.get("since") or "?")[:16]))
    t = b["totals"]
    lines += ["| **合计** | | %s | %s | %s | %s | | **%.3f** | pi 侧口径 |" % (
        t["calls"], format(t["input"], ","), format(t["cacheRead"], ","),
        format(t["output"], ","), t["cost"]), "", "> " + b["cost_note"],
              "> 账单文件: ~/.orca-coordinator/bills/%s.json；趋势: bills.jsonl" % b["run_id"]]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(prog="orca-coordinator", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dispatch", help="启动 worker（不阻塞），返回 receipt")
    d.add_argument("--worktree", required=True)
    d.add_argument("--spec-file", required=True)
    d.add_argument("--agent", default="pi", choices=["pi", "codex", "claude"])
    d.add_argument("--terminal"); d.add_argument("--task"); d.add_argument("--retry-of")
    d.add_argument("--run")
    d.set_defaults(fn=cmd_dispatch)
    w = sub.add_parser("wait", help="check --wait 滤心跳，整批原文输出，不自动 ack")
    w.add_argument("--timeout-ms", type=int, default=900000)
    w.set_defaults(fn=cmd_wait)
    k = sub.add_parser("ack", help="整批处理完后显式 ack")
    k.add_argument("delivery_id")
    k.set_defaults(fn=cmd_ack)
    s = sub.add_parser("settle", help="校验后收尾：--reuse/--retain/--release")
    s.add_argument("dispatch")
    s.add_argument("--mode", required=True, choices=["reuse", "retain", "release"])
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_settle)
    u = sub.add_parser("usage", help="按 run 汇总 token/cache/成本账单并留存")
    u.add_argument("run_id")
    u.add_argument("--objective", default=None)
    u.add_argument("--coordinator-session", default=None)
    u.set_defaults(fn=cmd_usage)
    a = p.parse_args()
    t0 = time.time()
    a.fn(a)
    log_line("cmd=%s rc=0 %.1fs" % (a.cmd, time.time() - t0))

if __name__ == "__main__":
    main()

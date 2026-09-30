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
ID_RE = re.compile(r"(?:ctx|task)_[0-9a-f]{12}")


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

def load_lines(path):
    lines = []
    with open(path, encoding="utf-8", errors="replace") as f:
        offset = 0
        for line in f:
            lines.append((offset, line))
            offset += len(line.encode("utf-8", errors="replace"))
    return lines

def sum_usage(agent, segment_lines):
    """segment_lines: [(offset, line)]，只统计真实 usage 行。截断行跳过。"""
    t = {"calls": 0, "input": 0, "cacheRead": 0, "output": 0, "cost": 0.0}
    for _off, line in segment_lines:
        if agent == "pi":
            if '"usage"' not in line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            u = (obj.get("message") or {}).get("usage")
            if not u:
                continue
            t["calls"] += 1
            t["input"] += u.get("input") or 0
            t["cacheRead"] += u.get("cacheRead") or 0
            t["output"] += u.get("output") or 0
            c = u.get("cost")
            t["cost"] += (c.get("total") or 0) if isinstance(c, dict) else (c or 0)
        else:
            if '"token_usage_record"' not in line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            u = (obj.get("payload") or {}).get("usage")
            if not u:
                continue
            t["calls"] += 1
            t["input"] += u.get("input_tokens") or 0          # codex input 含 cached
            t["cacheRead"] += u.get("cached_input_tokens") or 0
            t["output"] += u.get("output_tokens") or 0
    return t

USER_MARK = ('"role": "user"', '"role":"user"')

def _is_user_line(line):
    return any(m in line for m in USER_MARK)

def attribute_dispatch(dispatch_id, task_id, want_paths):
    """候选 = session 内容含 dispatch/task id 且首次出现行是 user 消息（preamble 证据，
    排除 plan 引子/协调者命令串的 id 污染）。分段边界 = 后续行里首个出现在 user 行的
    其他 dispatch id（复用终端场景），工具输出里的引子不算。"""
    ids = [x for x in (dispatch_id, task_id) if x]
    hits, weak = [], []
    for agent, path in iter_session_files():
        if agent == "pi" and want_paths:
            slug = os.path.basename(os.path.dirname(path)).casefold()
            if not any(slug == norm_slug(p).casefold() for p in want_paths if p):
                continue
        try:
            lines = load_lines(path)
        except OSError:
            continue
        for _off, line in lines:
            hit = next((i for i in ids if i in line), None)
            if hit:
                if _is_user_line(line):
                    hits.append((agent, path, lines))
                else:
                    weak.append((agent, path, lines))
                break
    if not hits and weak:
        hits, note_extra = weak, "no-preamble-evidence；"
    else:
        note_extra = ""
    if not hits:
        return None, None, None, None, "no-session-found"
    if len(hits) > 1:
        hits.sort(key=lambda h: os.path.getmtime(h[1]))
        note_extra += "multi-candidate-picked-oldest；"
    agent, path, lines = hits[0]
    start_idx = next(i for i, (_o, l) in enumerate(lines) if any(i in l for i in ids))
    start_off = lines[start_idx][0]
    boundary_off, last_ts = None, None
    for off, line in lines[start_idx + 1:]:
        m = re.search(r'"timestamp":\s*"([^"]+)"', line)
        if m:
            last_ts = m.group(1)
        if not _is_user_line(line):
            continue
        for g in set(ID_RE.findall(line)):
            if g not in ids:
                boundary_off = off
                break
        if boundary_off:
            break
    seg = [(o, l) for o, l in lines if o >= start_off and (boundary_off is None or o < boundary_off)]
    note = note_extra + ("ok" if boundary_off is None else "session含后续dispatch，已按user行边界截断")
    return agent, path, seg, last_ts, note

def cmd_usage(a):
    wl = run_orca_json(["orchestration", "worker-list", "--run", a.run_id,
                        "--include-remote", "--json"])
    workers = wl.get("result", {}).get("workers", [])
    rows, totals = [], {"calls": 0, "input": 0, "cacheRead": 0, "output": 0, "cost": 0.0}
    first_ts, last_ts_all = None, None
    for w in workers:
        did, tid = w.get("dispatchId"), w.get("taskId")
        if not did:
            continue
        wsp = ws_path((w.get("workspace") or {}).get("id"))
        agent, path, seg, last_ts, note = attribute_dispatch(did, tid, [wsp] if wsp else [])
        if not seg:
            rows.append({"dispatch": did, "task": tid, "agent": "?", "note": note,
                         "calls": 0, "input": 0, "cacheRead": 0, "output": 0, "cost": None})
            continue
        if last_ts and (not last_ts_all or last_ts > last_ts_all):
            last_ts_all = last_ts
        t = sum_usage(agent, seg)
        hit = (t["cacheRead"] / (t["cacheRead"] + t["input"]) * 100) if (t["cacheRead"] + t["input"]) else 0
        if agent == "codex":  # codex input 含 cached，命中率口径不同
            hit = (t["cacheRead"] / t["input"] * 100) if t["input"] else 0
        rows.append({"dispatch": did, "task": tid, "agent": agent, "calls": t["calls"],
                     "input": t["input"], "cacheRead": t["cacheRead"], "output": t["output"],
                     "hit": round(hit, 1), "cost": round(t["cost"], 3) if agent == "pi" else None,
                     "session": os.path.basename(path), "note": note})
        for k in ("calls", "input", "cacheRead", "output"):
            totals[k] += t[k]
        totals["cost"] += t["cost"]
        # 协调者窗口起点：worker session 首条记录时间
        m = re.search(r'"timestamp":\s*"([^"]+)"', seg[0][1]) if seg else None
        if m and (not first_ts or m.group(1) < first_ts):
            first_ts = m.group(1)
    # 协调者：当前 session（env 传入），窗口 = [首个含 run_id 的行, worker 最后活动时间]
    coord = None
    cs = a.coordinator_session or os.environ.get("PI_SESSION_FILE")
    if cs and os.path.exists(cs):
        lines = load_lines(cs)
        def _ts(l):
            m = re.search(r'"timestamp":\s*"([^"]+)"', l)
            return m.group(1) if m else None
        start_ts = next((_ts(l) for _o, l in lines if a.run_id in l and _ts(l)), None) or first_ts
        if start_ts:
            lines = [(o, l) for o, l in lines if (_ts(l) or "") >= start_ts]
        if last_ts_all:
            lines = [(o, l) for o, l in lines if (_ts(l) or "9999") <= last_ts_all]
        t = sum_usage("pi", lines)
        hit = (t["cacheRead"] / (t["cacheRead"] + t["input"]) * 100) if (t["cacheRead"] + t["input"]) else 0
        coord = {"session": os.path.basename(cs), "since": start_ts, "calls": t["calls"],
                 "input": t["input"], "cacheRead": t["cacheRead"], "output": t["output"],
                 "hit": round(hit, 1), "cost": round(t["cost"], 3)}
        for k in ("calls", "input", "cacheRead", "output"):
            totals[k] += t[k]
        totals["cost"] += t["cost"]
    bill = {"run_id": a.run_id, "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "objective": a.objective, "workers": rows, "coordinator": coord,
            "totals": {**totals, "cost": round(totals["cost"], 3)},
            "cost_note": "cost 仅 pi 侧实测合计；codex 无 cost 记录未计入"}
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
                           "objective": a.objective, **bill["totals"]}, ensure_ascii=False))
    with open(trend, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(old) + "\n")
    print(render_bill(bill))

def render_bill(b):
    lines = ["# 编排账单 %s" % b["run_id"], "", "目标: %s" % (b.get("objective") or "-"), "",
             "| 角色 | agent | 调用 | input | cacheRead | output | 命中% | cost$ | 备注 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in b["workers"]:
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

#!/usr/bin/env python3
"""定时兜底 sweep：找出本地已结束但未被 hook 上传的 session，幂等补传到 Memory Hub。

背景：agent 进程被杀（如 Orca worker release）时 SessionEnd/agent_end 不触发，
capture 从未发生，spool/Hub 均无记录。本脚本按「本地文件 − spool − Hub」三层比对
定位缺口，调 upload_sessions.py（--hook-namespace 双资产、幂等）补传。

已处理标识：state dir 的 sweep-state.json 按 uuid 记录 {status,size,mtime,project,sid,ts}；
status 为终态且文件 size/mtime 未变时直接跳过（内容增长后下一轮换新版本重传）。
spool 中 queued/retry 的本轮跳过（等 hook flush 自己完成），不写标识。

用法：
  python3 sweep_missed_sessions.py [--days 10] [--dry-run] [--limit N] [--ignore UUID...]
环境：MEMORY_HUB_API_KEY（生产必须）；MEMORY_HUB_URL 可覆盖 Hub base。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import memory_hook  # noqa: E402  复用 project 派生与别名口径

UPLOAD = os.path.join(HERE, "upload_sessions.py")
STATE_DIR = memory_hook.default_state_dir()
STATE_FILE = STATE_DIR / "sweep-state.json"
UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
EXTRACTION_PREFIX = "You are the Skill extraction sub-agent."
FRESH_GUARD_SEC = 30 * 60  # 30 分钟内还在动的文件视为 live，本轮跳过
RESULT_LINE_RE = re.compile(r"^\[\d+/\d+\]\s+(\w+)\s*\|\s*(\S+)\s*\|")

DEFAULT_ROOTS = {
    "pi": os.path.expanduser("~/.pi/agent/sessions"),
    "claude": os.path.expanduser("~/.claude/projects"),
    "codex": os.path.expanduser("~/.codex/sessions"),
}
TERMINAL_STATUSES = {
    "uploaded", "on-hub", "spool-completed", "skipped-extraction",
    "skipped-lowvalue", "skipped-unchanged", "ignored",
}


def log(msg: str) -> None:
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("sessions"), dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"schema_version": 1, "sessions": {}}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


def mark(state: dict, uuid: str, status: str, size: int, mtime: float,
         project: str = "", sid: str = "") -> None:
    state["sessions"][uuid] = {
        "status": status, "size": size, "mtime": mtime,
        "project": project, "sid": sid, "ts": time.time(),
    }


def spool_states() -> dict:
    """uuid -> set(state)，spool 是 hook capture 的本地持久记录。"""
    out: dict[str, set] = {}
    db_path = STATE_DIR / "spool.sqlite3"
    if not db_path.exists():
        return out
    import sqlite3
    db = sqlite3.connect(str(db_path))
    try:
        for sid, st in db.execute("SELECT source_session_id, state FROM jobs"):
            m = UUID_RE.search(sid or "")
            if m:
                out.setdefault(m.group(1), set()).add(st)
    finally:
        db.close()
    return out


def parse_session_file(path: str, source: str) -> tuple[str, str, str]:
    """-> (uuid, cwd, first_user_text)。只读头部信息，逐行扫到够用为止。"""
    uuid = cwd = first_user = ""
    m = UUID_RE.search(os.path.basename(path))
    if m:
        uuid = m.group(1)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(ev, dict):
                    continue
                t = ev.get("type")
                if source == "pi":
                    if t == "session" and not cwd:
                        cwd = ev.get("cwd") or ""
                        uuid = uuid or (ev.get("id") or "")
                    elif t == "message" and not first_user:
                        msg = ev.get("message")
                        if isinstance(msg, dict) and msg.get("role") == "user":
                            first_user = "\n".join(
                                c.get("text", "") for c in msg.get("content", [])
                                if isinstance(c, dict) and c.get("type") == "text")
                elif source == "claude":
                    if not cwd and ev.get("cwd"):
                        cwd = ev["cwd"]
                    if not uuid and ev.get("sessionId"):
                        uuid = ev["sessionId"]
                    if t == "user" and not first_user:
                        msg = ev.get("message") or {}
                        c = msg.get("content")
                        first_user = c if isinstance(c, str) else "\n".join(
                            x.get("text", "") for x in c
                            if isinstance(x, dict) and x.get("type") == "text")
                elif source == "codex":
                    if t == "session_meta":
                        pl = ev.get("payload") or {}
                        cwd = cwd or pl.get("cwd") or ""
                        uuid = uuid or pl.get("session_id") or ""
                    elif t == "response_item" and not first_user:
                        pl = ev.get("payload") or {}
                        if pl.get("type") == "message" and pl.get("role") == "user":
                            first_user = "\n".join(
                                c.get("text", "") for c in pl.get("content", [])
                                if isinstance(c, dict) and c.get("type") in ("input_text", "text"))
                if uuid and cwd and first_user:
                    break
    except OSError:
        pass
    return uuid, cwd, (first_user or "").strip()


def hub_probe(sid: str, project: str, hub_url: str, api_key: str, user_id: str) -> int:
    req = urllib.request.Request(
        f"{hub_url}/v1/sessions/{urllib.parse.quote(sid, safe='')}", method="GET")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("X-Agent-Id", "pi")
    req.add_header("X-Project-Id", project)
    req.add_header("X-User-Id", user_id)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return -1


def upload_one(path: str, source: str, project: str, user_id: str,
               hub_url: str, api_key: str) -> str:
    """单文件调 upload_sessions.py，返回 uploaded/skipped-lowvalue/skipped-unchanged/failed。"""
    env = dict(os.environ, MEMORY_HUB_TITLE_LLM="0")  # Orca 派遣模板会被 LLM 分类器误判
    cmd = [sys.executable, UPLOAD, "--source", source, "--hook-namespace",
           "--project-id", project, "--user-id", user_id,
           "--hub-url", hub_url, path]
    if api_key:
        cmd += ["--api-key", api_key]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    except subprocess.TimeoutExpired:
        return "failed"
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    for line in out.splitlines():
        m = RESULT_LINE_RE.match(line.strip())
        if not m:
            continue
        status, sid = m.group(1), m.group(2)
        if UUID_RE.search(sid):
            if status == "uploaded":
                return "uploaded"
            if status == "skipped":
                return "skipped-lowvalue" if "低价值" in line else "skipped-unchanged"
            return "failed"
    return "uploaded" if proc.returncode == 0 and "uploaded=1" in out else "failed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ignore", nargs="*", default=[],
                    help="把这些 uuid 标记为 ignored（人工确认不归档），永不处理")
    ap.add_argument("--user-id", default=os.environ.get("MEMORY_HUB_CLIENT_USER_ID", "sunlaibing"))
    ap.add_argument("--hub-url", default=os.environ.get("MEMORY_HUB_URL") or memory_hook.DEFAULT_HUB_URL)
    ap.add_argument("--api-key", default=os.environ.get("MEMORY_HUB_API_KEY", ""))
    args = ap.parse_args()

    state = load_state()
    sessions = state["sessions"]

    for u in args.ignore:
        m = UUID_RE.search(u)
        if m:
            mark(state, m.group(1), "ignored", 0, 0)
            log(f"ignored {m.group(1)}")
    if args.ignore:
        save_state(state)

    cutoff = time.time() - args.days * 86400
    spool = spool_states()
    scanned = skipped_marked = skipped_fresh = 0
    candidates: list[dict] = []

    for source, root in DEFAULT_ROOTS.items():
        for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
            norm = path.replace("/", "\\").lower()
            if "\\backup\\" in norm or "\\subagents\\" in norm:
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            if st.st_mtime < cutoff:
                continue
            scanned += 1
            uuid, cwd, first_user = parse_session_file(path, source)
            if not uuid:
                continue
            prev = sessions.get(uuid)
            if prev and prev.get("status") == "ignored":
                skipped_marked += 1
                continue  # 人工确认不归档：不看文件是否变化，永不处理
            if (prev and prev.get("status") in TERMINAL_STATUSES
                    and prev.get("size") == st.st_size and prev.get("mtime") == st.st_mtime):
                skipped_marked += 1
                continue
            if time.time() - st.st_mtime < FRESH_GUARD_SEC:
                skipped_fresh += 1
                continue
            project = memory_hook.project_id_for_cwd(cwd, "unknown") if cwd else "unknown"
            sid = memory_hook.normalize_identifier(f"{source}:{project}:{uuid}", f"{source}-session")
            rec = dict(uuid=uuid, path=path, source=source, project=project, sid=sid,
                       size=st.st_size, mtime=st.st_mtime)
            if first_user.lstrip().startswith(EXTRACTION_PREFIX):
                mark(state, uuid, "skipped-extraction", st.st_size, st.st_mtime, project, sid)
                continue
            states = spool.get(uuid, set())
            if "completed" in states:
                mark(state, uuid, "spool-completed", st.st_size, st.st_mtime, project, sid)
                continue
            if states & {"queued", "retry", "processing"}:
                continue  # hook 在途，本轮不碰、不写标识
            candidates.append(rec)

    log(f"scanned={scanned} marked-skip={skipped_marked} fresh-skip={skipped_fresh} "
        f"to-probe={len(candidates)}")

    uploaded = failed = 0
    probed_ok = 0
    for rec in candidates[: args.limit or None]:
        code = hub_probe(rec["sid"], rec["project"], args.hub_url, args.api_key, args.user_id)
        if code == 200:
            probed_ok += 1
            mark(state, rec["uuid"], "on-hub", rec["size"], rec["mtime"], rec["project"], rec["sid"])
            continue
        if code != 404:
            log(f"probe HTTP {code} {rec['sid']} — 本轮跳过")
            continue
        if args.dry_run:
            print(f"[dry-run] MISSING {rec['source']}:{rec['project']} "
                  f"{os.path.basename(rec['path'])}")
            continue
        result = upload_one(rec["path"], rec["source"], rec["project"],
                            args.user_id, args.hub_url, args.api_key)
        mark(state, rec["uuid"], result, rec["size"], rec["mtime"], rec["project"], rec["sid"])
        log(f"{result} {rec['sid']}")
        if result == "uploaded":
            uploaded += 1
        elif result == "failed":
            failed += 1

    if not args.dry_run:
        save_state(state)
    print(f"SUMMARY scanned={scanned} marked-skip={skipped_marked} fresh-skip={skipped_fresh} "
          f"probe={len(candidates)} on-hub={probed_ok} uploaded={uploaded} failed={failed} "
          f"state={STATE_FILE}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""回填漏传的 pi session 到 Memory Hub（自动上传脚本）。

用途：扫描本机 pi session 目录，找出 Hub 中不存在的 session（漏传），
排除 auto-skill extraction 等「LLM 分析」子 session 后，用既有的
upload_sessions.py（--hook-namespace 双资产、幂等）批量上传到指定 project。

只读检测 + 调用既有上传器，不重复造轮子。中断可重跑（幂等）。

用法：
  python3 backfill_missed_pi_sessions.py [--project nas] [--dry-run] [--limit N]

环境：需在本机（能读到 Hub metadata DB 与 pi session 目录）运行。
鉴权：--api-key / MEMORY_HUB_API_KEY（生产）；当前服务端未强制 key 时留空亦可。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.join(HERE, "upload_sessions.py")
HUB_DB = "/share/Container/memory-hub/data/memory-hub.sqlite3"
PI_SESS_ROOT = os.path.expanduser("~/.pi/agent/sessions")

# 与 memory_hook.py 保持同步：auto-skill extraction 子 session 首条 user 消息签名
EXTRACTION_PREFIX = "You are the Skill extraction sub-agent."
UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


def hub_uuids() -> set[str]:
    db = sqlite3.connect(f"file:{HUB_DB}?mode=ro", uri=True)
    out = set()
    for (sid,) in db.execute("SELECT session_id FROM sessions"):
        m = UUID_RE.search(sid or "")
        if m:
            out.add(m.group(1))
    db.close()
    return out


def first_user_text(path: str) -> str:
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
                msg = ev.get("message") if ev.get("type") == "message" else None
                if not isinstance(msg, dict) or msg.get("role") != "user":
                    continue
                return "\n".join(
                    c.get("text", "")
                    for c in msg.get("content", [])
                    if isinstance(c, dict) and c.get("type") == "text"
                )
    except OSError:
        pass
    return ""


def local_sessions(sess_dir: str) -> dict[str, str]:
    out = {}
    for p in glob.glob(os.path.join(sess_dir, "*.jsonl")):
        m = UUID_RE.search(os.path.basename(p))
        if m:
            out[m.group(1)] = p
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="nas")
    ap.add_argument("--sess-dir", default=os.path.join(
        PI_SESS_ROOT, "--share-CACHEDEV1_DATA-homes-slb1988--"))
    ap.add_argument("--hub-url", default="http://10.77.77.6:9287")
    ap.add_argument("--dashboard-url", default="http://10.77.77.6:9288")
    ap.add_argument("--user-id", default=os.environ.get("MEMORY_HUB_CLIENT_USER_ID", "sunlaibing"))
    ap.add_argument("--api-key", default=os.environ.get("MEMORY_HUB_API_KEY", ""))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    hub = hub_uuids()
    local = local_sessions(args.sess_dir)
    gap = sorted(set(local) - hub)

    upload, skipped = [], []
    for u in gap:
        p = local[u]
        if first_user_text(p).lstrip().startswith(EXTRACTION_PREFIX):
            skipped.append(u)  # LLM 分析子 session，不上传
        else:
            upload.append(p)
    if args.limit:
        upload = upload[: args.limit]

    print(f"[detect] Hub sessions={len(hub)} local={len(local)} gap={len(gap)} "
          f"llm-extraction-skip={len(skipped)} to-upload={len(upload)}")
    if skipped:
        print("[skip] LLM 分析子 session:")
        for u in skipped:
            print("   ", u)
    if not upload:
        print("[done] 无漏传，无需上传。")
        return 0
    if args.dry_run:
        print("[dry-run] 将上传以下文件：")
        for p in upload:
            print("   ", os.path.basename(p))
        return 0

    cmd = [sys.executable, UPLOAD,
           "--source", "pi",
           "--hook-namespace",
           "--project-id", args.project,
           "--user-id", args.user_id,
           "--hub-url", args.hub_url,
           "--dashboard-url", args.dashboard_url]
    if args.api_key:
        cmd += ["--api-key", args.api_key]
    cmd += upload
    print("[upload] running:", " ".join(cmd[:12]), f"... ({len(upload)} files)")
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())

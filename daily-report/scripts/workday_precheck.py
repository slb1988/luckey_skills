#!/usr/bin/env python3
"""daily-report 定时任务 precheck：当天有工作证据 exit 0（继续执行 agent），否则 exit 1（记录 skipped）。

工作证据（任一命中即算）：
1. 三台 P4 服务器当天有本人提交的 CL
2. ActivityWatch 当天 not-afk 累计活跃 >= 2 小时（有工作但没提交的日子）
"""

import json
import os
import socket
import subprocess
import sys
import urllib.request
from datetime import date, timedelta

P4_SERVERS = [
    ("192.168.2.236:1666", "sunlaibing", False),
    ("192.168.2.13:1666", "admin_sun", True),
    ("10.77.77.6:1666", "admin", True),
]

AW_MIN_ACTIVE_SECONDS = 7200


def p4_has_cl_today(port, user, utf8):
    today = date.today().strftime("%Y/%m/%d")
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y/%m/%d")
    env = dict(os.environ, P4CHARSET="utf8") if utf8 else None
    try:
        r = subprocess.run(
            ["p4", "-p", port, "-u", user, "changes", "-u", user, "-s", "submitted", f"@{today},@{tomorrow}"],
            capture_output=True, text=True, timeout=15, env=env,
        )
        return "Change " in (r.stdout or "")
    except Exception:
        return False  # 连接失败不视为有工作证据


def aw_active_enough():
    today = date.today().isoformat()
    body = json.dumps({
        "timeperiods": [f"{today}T00:00:00+08:00/{today}T23:59:59+08:00"],
        "query": [
            f'events = query_bucket("aw-watcher-afk_{socket.gethostname()}");',
            'events = filter_keyvals(events, "status", ["not-afk"]);',
            "RETURN = events;",
        ],
    }).encode()
    try:
        req = urllib.request.Request(
            "http://localhost:5600/api/0/query/", data=body,
            headers={"Content-Type": "application/json"},
        )
        events = json.load(urllib.request.urlopen(req, timeout=10))[0]
        return sum(e.get("duration", 0) for e in events) >= AW_MIN_ACTIVE_SECONDS
    except Exception:
        return False


if __name__ == "__main__":
    for port, user, utf8 in P4_SERVERS:
        if p4_has_cl_today(port, user, utf8):
            print(f"work evidence: P4 CL on {port}")
            sys.exit(0)
    if aw_active_enough():
        print("work evidence: AW active >= 2h")
        sys.exit(0)
    print("no work evidence today")
    sys.exit(1)

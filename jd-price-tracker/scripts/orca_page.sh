#!/bin/bash
# orca_page.sh <url-substring> [create-url]
# 打印一个 URL 包含 substring 的 Orca 内嵌浏览器 tab 的 browserPageId；没有则用 create-url 新建。
# 用法: PAGE=$(.claude/skills/jd-price-tracker/scripts/orca_page.sh jd.com "https://www.jd.com")
ORCA=${ORCA_CLI:-orca}
SUB="$1"; CREATE="$2"
PAGE=$($ORCA tab list --json 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    tabs=d['result']['tabs']
    for t in tabs:
        if '$SUB' in (t.get('url') or ''):
            print(t['browserPageId']); break
except Exception: pass
")
if [ -z "$PAGE" ] && [ -n "$CREATE" ]; then
  PAGE=$($ORCA tab create --url "$CREATE" --json 2>/dev/null | python3 -c "
import json,sys
try: print(json.load(sys.stdin)['result']['browserPageId'])
except Exception: pass
")
fi
if [ -z "$PAGE" ]; then
  echo "ERROR: no Orca browser tab containing '$SUB' and none created" >&2
  exit 1
fi
echo "$PAGE"

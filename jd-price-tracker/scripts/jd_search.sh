#!/bin/bash
# jd_search.sh "<关键词>" —— 打印京东搜索结果卡片: "SKU :: 标题|价格|促销|店铺"
# 需京东已登录（未登录会被跳 passport.jd.com）。输出含 ¥ 的卡有效；空结果多为限流，停 1-2 分钟重试。
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ORCA=${ORCA_CLI:-orca}
PAGE=$("$SKILL_DIR/scripts/orca_page.sh" jd.com "https://www.jd.com") || exit 1
KW=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$1")
$ORCA goto --page $PAGE --url "https://search.jd.com/Search?keyword=${KW}&enc=utf-8" --json >/dev/null 2>&1
$ORCA wait --page $PAGE --load load --json >/dev/null 2>&1
sleep 3
$ORCA eval --page $PAGE --expression "$(cat "$SKILL_DIR/scripts/jd_extract.js")" --json 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
if not d.get('ok'): print('ERR',json.dumps(d,ensure_ascii=False)[:300]); sys.exit(1)
try: items=json.loads(d['result']['result'])
except Exception: print('PARSE-ERR', str(d['result'])[:300]); sys.exit(1)
if not items:
    print('EMPTY(可能限流或无结果)')
    sys.exit(2)
for x in items: print(x['sku'],'::',x['txt'])
"

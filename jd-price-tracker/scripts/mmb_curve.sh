#!/bin/bash
# mmb_curve.sh <京东商品URL> [天数=90] —— 慢慢买历史价曲线统计：区间、低点、高点、现价（到手价口径）
# 需慢慢买已登录（微信扫码，保存在 Orca 浏览器 profile）。
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ORCA=${ORCA_CLI:-orca}
DAYS=${2:-90}
ENC=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$1")
PAGE=$("$SKILL_DIR/scripts/orca_page.sh" manmanbuy.com "https://tool.manmanbuy.com/HistoryLowest.aspx?url=${ENC}") || exit 1
$ORCA goto --page $PAGE --url "https://tool.manmanbuy.com/HistoryLowest.aspx?url=${ENC}" --json >/dev/null 2>&1
$ORCA wait --page $PAGE --load load --json >/dev/null 2>&1
sleep 6
$ORCA eval --page $PAGE --expression "(()=>{try{flotChart.showDayData('${DAYS}',null,0);return 't'}catch(e){return 'E '+e.message}})()" --json >/dev/null 2>&1
sleep 5
$ORCA eval --page $PAGE --expression "JSON.stringify(flotChart.data)" --json 2>/dev/null | python3 -c "
import json,sys,datetime
d=json.load(sys.stdin)
if not d.get('ok'): print('ERR',str(d)[:200]); sys.exit(1)
try: arr=json.loads(d['result']['result'])
except Exception: print('NO-DATA(可能未登录或无收录)'); sys.exit(2)
by={}
for p in arr: by[datetime.datetime.fromtimestamp(p[0]/1000).strftime('%Y-%m-%d')]=p[1]
days=sorted(by.items())
if not days: print('NO-DATA'); sys.exit(2)
vals=[v for _,v in days]
print('点数',len(days),'区间',days[0][0],'->',days[-1][0])
print('低点',min(vals),[x for x,v in days if v==min(vals)][0])
print('高点',max(vals),[x for x,v in days if v==max(vals)][0])
print('现价',days[-1][0],days[-1][1])
print('CSV', ';'.join(f'{d0},{v}' for d0,v in days))
"

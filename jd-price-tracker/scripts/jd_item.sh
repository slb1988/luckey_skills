#!/bin/bash
# jd_item.sh <sku> —— 商品页核实：标题、可见价格数字、加购按钮/库存提示、店铺
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ORCA=${ORCA_CLI:-orca}
PAGE=$("$SKILL_DIR/scripts/orca_page.sh" jd.com "https://www.jd.com") || exit 1
$ORCA goto --page $PAGE --url "https://item.jd.com/$1.html" --json >/dev/null 2>&1
$ORCA wait --page $PAGE --load load --json >/dev/null 2>&1
sleep 3
$ORCA eval --page $PAGE --expression "(()=>{const t=document.body.innerText.replace(/\n+/g,'|');if(document.title.includes('频控'))return JSON.stringify({blocked:true});const i=t.indexOf('加入购物车');const nums=[...document.querySelectorAll('span,div')].filter(e=>e.children.length===0&&/^\d{3,6}(\.\d{1,2})?\$/.test(e.textContent.trim())).map(e=>e.textContent.trim());return JSON.stringify({title:document.title.slice(0,60),nums:nums.slice(0,10),cart:i>=0?t.slice(Math.max(0,i-30),i+15):'NO-CART-BTN',btn:(t.match(/加入购物车|到货通知|暂时无货|售罄|仅剩\d+件/g)||[]).slice(0,4),shop:(t.match(/[^|]{2,30}(自营旗舰店|官方旗舰店|旗舰店)/g)||[]).slice(0,2),subsidy:(t.match(/政府补贴[^|]{0,20}|已减[\￥]?[0-9.]+/g)||[]).slice(0,3)})})()" --json 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(json.dumps(json.loads(d['result']['result']),ensure_ascii=False) if d.get('ok') else 'ERR '+str(d)[:200])
"

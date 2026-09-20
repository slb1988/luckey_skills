import sqlite3, json, os, re, sys, hashlib

DAY = sys.argv[1] if len(sys.argv) > 1 else '2026-08-12'
# 第二参数可选：逗号分隔的关键词（给才过滤；默认全量）
KW_ARG = sys.argv[2] if len(sys.argv) > 2 else ''
OUT = '/tmp/distill'
os.makedirs(OUT, exist_ok=True)

KEYWORDS = [k.strip() for k in KW_ARG.split(',') if k.strip()]


def first_user_text(b):
    """会话首个真实用户消息（用于二次去重：同一对话被多 session_id 反复快照的场景）"""
    for msg in b.get('messages', []):
        if msg.get('role') != 'user':
            continue
        cont = msg.get('content')
        if isinstance(cont, str):
            t = cont
        elif isinstance(cont, list):
            t = ' '.join(x.get('text', '') for x in cont if isinstance(x, dict) and x.get('type') == 'text')
        else:
            continue
        t = t.strip()
        if t and not t.startswith(('<system-reminder', 'Caveat:', '<command-')):
            return t[:500]
    return ''


c = sqlite3.connect('/app/data/history.db')

# pass 1: 按 (key, session_id) 去重取最长快照；可选关键词过滤
best = {}  # session_key -> (request_id, n_msgs, key_name, ts, first_hash)
scanned = matched = 0
for rid, key, ts, body in c.execute(
        "SELECT request_id, key_name, ts, request_body FROM request_history "
        "WHERE ts LIKE ? AND LENGTH(COALESCE(request_body,''))>10", (DAY + '%',)):
    scanned += 1
    if KEYWORDS:
        lb = body.lower()
        if not any(k in lb for k in KEYWORDS):
            continue
    matched += 1
    try:
        b = json.loads(body)
    except Exception:
        continue
    meta = b.get('metadata') or {}
    uid = meta.get('user_id') or ''
    sid = ''
    m = re.search(r'session_id\\?":\\?"([\w-]+)', uid)
    if m:
        sid = m.group(1)
    else:
        try:
            sid = json.loads(uid).get('session_id', '')
        except Exception:
            pass
    n = len(b.get('messages', []))
    fh = hashlib.md5(first_user_text(b).encode()).hexdigest()[:12]
    sk = (key, sid or rid)
    if sk not in best or n > best[sk][1]:
        best[sk] = (rid, n, key, ts, fh)

# pass 1.5: 二次去重——(key, 首问 hash) 相同视为同一对话，留消息最多者
dedup = {}
for sk, v in best.items():
    rid, n, key, ts, fh = v
    dk = (key, fh)
    if dk not in dedup or n > dedup[dk][1]:
        dedup[dk] = v

print(f'scanned={scanned} matched={matched} sessions={len(best)} after_firstprompt_dedup={len(dedup)}', flush=True)

# pass 2: extract transcripts
def text_of(content, limit_toolresult=2000, limit_thinking=1500):
    parts = []
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for blk in content:
            if not isinstance(blk, dict):
                continue
            t = blk.get('type')
            if t == 'text':
                parts.append(blk.get('text', ''))
            elif t == 'thinking':
                th = blk.get('thinking', '')
                if th.strip():
                    parts.append('[thinking] ' + th[:limit_thinking])
            elif t == 'tool_result':
                sub = blk.get('content')
                s = text_of(sub) if not isinstance(sub, str) else sub
                parts.append('[tool_result] ' + s[:limit_toolresult])
            elif t == 'tool_use':
                name = blk.get('name', '')
                inp = json.dumps(blk.get('input', {}), ensure_ascii=False)
                parts.append(f'[tool_use {name}] {inp[:400]}')
    return '\n'.join(p for p in parts if p)

index = []
for (key, fh), (rid, n, key_name, ts, _fh) in sorted(dedup.items()):
    row = c.execute("SELECT request_body FROM request_history WHERE request_id=?", (rid,)).fetchone()
    if not row:
        continue
    b = json.loads(row[0])
    lines = []
    for msg in b.get('messages', []):
        role = msg.get('role', '?')
        txt = text_of(msg.get('content'))
        if txt.strip():
            lines.append(f'===== {role} =====\n{txt}')
    fn = f'{key}_{rid[:13]}_{fh}.txt'
    with open(os.path.join(OUT, fn), 'w', errors='replace') as f:
        f.write('\n\n'.join(lines))
    sz = os.path.getsize(os.path.join(OUT, fn))
    index.append((key, ts, n, sz, fn))

with open(os.path.join(OUT, 'index.tsv'), 'w') as f:
    for r in index:
        f.write('\t'.join(map(str, r)) + '\n')
for r in sorted(index, key=lambda x: -x[3])[:40]:
    print(r)

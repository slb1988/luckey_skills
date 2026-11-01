#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kimi for Coding 额度批量查询（5h / 7d / 加油包），终端仪表盘 + HTML 报告 + 历史对比预测。

用法:
  python kimi_quota.py sk-kimi-aaa sk-kimi-bbb
  python kimi_quota.py -f keys.txt [--html report.html] [--open]
  python kimi_quota.py --include-pi            # 顺带查 pi auth.json 里的 kimi-coding key
  python kimi_quota.py --import-html a.html b.html   # 把旧 HTML 报告导入历史快照（不探测）

keys.txt 每行一个:  `<key> [别名]`，# 开头为注释。

历史快照独立存放于 kimi_quota_history.jsonl（与 HTML 报告分离，一次探测一行 JSON，方便差分）。
每次探测自动追加（--no-save 关闭），并与最近一次 ≥ --baseline-gap 小时（默认 2）前的快照对比，
按两次探测间的净消耗速率线性外推 7 天窗口耗尽时间，预测能否撑到重置（滚动窗口，仅供参考）。
"""
import argparse, concurrent.futures, html, json, os, re, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

API = 'https://api.kimi.com/coding/v1'
CST = timezone(timedelta(hours=8))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'assets'))
HISTORY_FILE = os.path.join(ASSETS_DIR, 'kimi_quota_history.jsonl')
DEFAULT_HTML = os.path.join(ASSETS_DIR, 'reports', 'kimi_quota_report.html')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def http_get(path, key, timeout=25):
    r = urllib.request.Request(API + path)
    r.add_header('Authorization', 'Bearer ' + key)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.load(resp)


def mask(key):
    return key[:12] + '...' + key[-4:] if len(key) > 20 else key[:6] + '...'


def cents(obj):
    return int((obj or {}).get('priceInCents', 0)) / 100


def probe(item):
    label, key = item
    out = {'label': label, 'key_mask': mask(key), 'ok': False, 'error': ''}
    try:
        me = http_get('/me', key)
        out['nickname'] = me.get('nickname', '?')
        out['user_id'] = me.get('user_id', '?')
        out['phone'] = (me.get('phone') or {}).get('number', '')
        d = http_get('/usages', key)
        u = d.get('usages') or {}
        for name, src in (('h5', 'limit_5h'), ('d7', 'limit_7d')):
            w = u.get(src) or {}
            out[name + '_ratio'] = float(w.get('used_ratio', 0))
            out[name + '_reset'] = w.get('reset_time', '')
        bw = d.get('booster_wallet') or {}
        out['booster_status'] = bw.get('status', '?').replace('STATUS_', '')
        out['booster_used'] = cents(bw.get('monthlyUsed'))
        out['booster_limit'] = cents(bw.get('monthlyChargeLimit'))
        out['ok'] = True
    except urllib.error.HTTPError as e:
        out['error'] = f'HTTP {e.code}'
    except Exception as e:
        out['error'] = f'{type(e).__name__}: {e}'
    return out


def fmt_reset(iso):
    if not iso:
        return '?'
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(CST).strftime('%m-%d %H:%M')
    except ValueError:
        return iso


def parse_dt(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace('Z', '+00:00')).astimezone(CST)
    except ValueError:
        return None


def bar(ratio, width=20):
    fill = max(0, min(width, round(ratio * width)))
    return '█' * fill + '░' * (width - fill)


def color_cls(ratio):
    return 'ok' if ratio < 0.7 else ('warn' if ratio < 0.9 else 'crit')


# ---------- 历史快照（独立于 HTML 报告，方便差分） ----------

def load_history(path=HISTORY_FILE):
    runs = []
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get('ts') and rec.get('keys'):
                    runs.append(rec)
    return runs


def save_snapshot(results, path=HISTORY_FILE):
    rec = {'ts': datetime.now(CST).isoformat(timespec='seconds'),
           'keys': {r['key_mask']: {'nickname': r.get('nickname', ''),
                                     'h5': round(r['h5_ratio'], 6),
                                     'd7': round(r['d7_ratio'], 6),
                                     'd7_reset': r.get('d7_reset', '')}
                    for r in results if r.get('ok')}}
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return rec


def pick_baseline(runs, now, min_gap_h):
    """最近一次 ≥ min_gap_h 小时前的快照（间隔太短的对比噪声太大）；没有则取最新一条。"""
    ok = [r for r in runs if parse_dt(r['ts'])]
    if not ok:
        return None
    ok.sort(key=lambda r: r['ts'])
    for r in reversed(ok):
        if (now - parse_dt(r['ts'])).total_seconds() >= min_gap_h * 3600:
            return r
    return ok[-1]


VERDICT_LABEL = {'new_exhausted': '新增耗尽', 'exhausted': '仍耗尽', 'short': '间隔太短',
                 'flat': '回落/持平', 'risk': '撑不到重置', 'safe': '可撑到重置'}


def attach_compare(results, baseline, now):
    """给每个 key 挂上 cmp 对比/预测信息，返回对比上的 key 数。"""
    base_ts = parse_dt(baseline['ts'])
    if not base_ts:
        return 0
    dt_h = max(0.0, (now - base_ts).total_seconds() / 3600)
    n = 0
    for r in results:
        if not r.get('ok'):
            continue
        p = baseline['keys'].get(r['key_mask'])
        if not p or p.get('d7') is None:
            continue
        cur, prev = r['d7_ratio'], float(p['d7'])
        c = {'base_ts': base_ts, 'dt_h': dt_h, 'd7_prev': prev,
             'd7_delta_pp': (cur - prev) * 100,
             'h5_delta_pp': (r['h5_ratio'] - float(p.get('h5') or 0)) * 100}
        if cur >= 0.9995:
            c['verdict'] = 'new_exhausted' if prev < 0.9995 else 'exhausted'
        elif dt_h < 0.5:
            c['verdict'] = 'short'
        elif c['d7_delta_pp'] <= 0:
            c['verdict'] = 'flat'
        else:
            c['rate_pd'] = c['d7_delta_pp'] / dt_h * 24.0   # pp/天（净消耗速率）
            c['eta'] = now + timedelta(days=(100 - cur * 100) / c['rate_pd'])
            reset = parse_dt(r.get('d7_reset'))
            c['verdict'] = 'risk' if (reset and c['eta'] < reset) else 'safe'
        r['cmp'] = c
        n += 1
    return n


def cmp_line(r):
    c = r.get('cmp')
    if not c:
        return ''
    arrow = f"{c['d7_prev']*100:.1f}%→{r['d7_ratio']*100:.1f}%"
    v = c['verdict']
    if v in ('new_exhausted', 'exhausted'):
        return f"{VERDICT_LABEL[v]}（{arrow}）"
    if v == 'short':
        return f"Δ{c['d7_delta_pp']:+.2f}pp（{arrow}，间隔 {c['dt_h']*60:.0f} 分钟，不预测）"
    if v == 'flat':
        return f"Δ{c['d7_delta_pp']:+.2f}pp（{arrow}，可撑到重置）"
    return (f"Δ{c['d7_delta_pp']:+.2f}pp · {c['rate_pd']:.1f}pp/天 → "
            f"预计 {c['eta'].strftime('%m-%d %H:%M')} 耗尽（{VERDICT_LABEL[v]}，重置 {fmt_reset(r['d7_reset'])}）")


def summarize(results):
    g = {'new_exhausted': [], 'risk': [], 'safe': [], 'flat': [], 'short': [], 'exhausted': []}
    for r in results:
        c = r.get('cmp')
        if c:
            g[c['verdict']].append(r)
    g['risk'].sort(key=lambda r: r['cmp']['eta'])
    g['new_exhausted'].sort(key=lambda r: r['cmp']['d7_prev'])
    usable = [r for r in results if r.get('ok') and r['d7_ratio'] < 0.9995]
    return g, usable


# ---------- 旧 HTML 报告导入历史 ----------

NAME_DIV = re.compile(r'<div class="name">(.*?)</div>', re.S)
KEY_SPAN = re.compile(r'class="key">(sk-kimi-[^<]+)<')
PCT_SPAN = re.compile(r'class="pct">\s*([\d.]+)%')
GEN_TIME = re.compile(r'生成于 (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')


def parse_report_html(doc):
    """按文档顺序配对每个 key 与其后的两个 pct（5h、7d）；查询失败的卡片无 pct，自动跳过。"""
    events = []
    for m in NAME_DIV.finditer(doc):
        km = KEY_SPAN.search(m.group(1))
        if not km:
            continue
        nm = re.match(r'\s*([^<]+)', m.group(1))
        events.append((m.end(), 'key', (km.group(1), nm.group(1).strip() if nm else '')))
    for m in PCT_SPAN.finditer(doc):
        events.append((m.start(), 'pct', float(m.group(1)) / 100))
    events.sort(key=lambda e: e[0])
    keys, cur, pcts = {}, None, []
    for _, kind, val in events:
        if kind == 'key':
            cur, pcts = val, []
        elif cur and cur[0] not in keys:
            pcts.append(val)
            if len(pcts) == 2:
                keys[cur[0]] = {'nickname': cur[1], 'h5': pcts[0], 'd7': pcts[1], 'd7_reset': ''}
    return keys


def import_html(paths):
    existing = {r['ts'] for r in load_history()}
    imported = 0
    for path in paths:
        try:
            with open(path, encoding='utf-8') as f:
                doc = f.read()
        except OSError as e:
            print(f'✗ {path}: {e}')
            continue
        m = GEN_TIME.search(doc)
        keys = parse_report_html(doc)
        if not m or not keys:
            print(f'✗ {path}: 解析失败（{"无生成时间" if not m else "无 key 数据"}），跳过')
            continue
        ts = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S').replace(tzinfo=CST).isoformat(timespec='seconds')
        if ts in existing:
            print(f'· {path}: {ts} 已在历史中，跳过')
            continue
        with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'ts': ts, 'keys': keys}, ensure_ascii=False) + '\n')
        existing.add(ts)
        imported += 1
        print(f'✓ {path}: 导入 {len(keys)} 个 key @ {ts[:16]}')
    print(f'共导入 {imported} 条快照 → {HISTORY_FILE}')


# ---------- 输出 ----------

def print_console(results):
    for i, r in enumerate(results, 1):
        print('=' * 60)
        head = f"[{i}] {r.get('nickname', '查询失败')}  {r['key_mask']}"
        if r['label']:
            head += f"  【{r['label']}】"
        print(head)
        print('-' * 60)
        if not r['ok']:
            print(f"  ✗ {r['error']}")
            continue
        if r.get('phone'):
            print(f"  手机 {r['phone']}   user_id {r['user_id']}")
        print(f"  5小时窗口  {bar(r['h5_ratio'])}  {r['h5_ratio']*100:6.2f}% 已用   重置 {fmt_reset(r['h5_reset'])}")
        print(f"  7天窗口    {bar(r['d7_ratio'])}  {r['d7_ratio']*100:6.2f}% 已用   重置 {fmt_reset(r['d7_reset'])}")
        if r.get('cmp'):
            print(f"  对比上次   {cmp_line(r)}")
        print(f"  加油包月消费  ¥{r['booster_used']:.2f} / 上限 ¥{r['booster_limit']:.2f}  ({r['booster_status']})")
    print('=' * 60)


def print_compare_summary(results, baseline):
    g, usable = summarize(results)
    base_ts = parse_dt(baseline['ts'])
    dt_h = (datetime.now(CST) - base_ts).total_seconds() / 3600
    total_ok = sum(1 for r in results if r['ok'])
    names = lambda rs: '、'.join(r.get('nickname', r['key_mask']) for r in rs) or '无'
    print(f"\n{'=' * 60}\n对比与预测 · 基线 {base_ts.strftime('%m-%d %H:%M')}（{dt_h:.1f}h 前）· 速率为净消耗线性外推\n{'-' * 60}")
    print(f"当前可用（7天窗口未耗尽）: {len(usable)} / {total_ok}")
    print(f"新增耗尽（{len(g['new_exhausted'])}）: {names(g['new_exhausted'])}")
    if g['risk']:
        print(f"撑不到重置（{len(g['risk'])}）:")
        for r in g['risk']:
            c = r['cmp']
            print(f"  · {r.get('nickname', '?')}  {r['d7_ratio']*100:.1f}%  {c['rate_pd']:.1f}pp/天"
                  f" → 预计 {c['eta'].strftime('%m-%d %H:%M')} 耗尽（重置 {fmt_reset(r['d7_reset'])}）")
    else:
        print("撑不到重置（0）: 无")
    print(f"可撑到重置（{len(g['safe'])}）: {names(g['safe'])}")
    print(f"回落/持平（{len(g['flat'])}）: {names(g['flat'])}")
    if g['short']:
        print(f"间隔太短未预测（{len(g['short'])}）: {names(g['short'])}")
    print('=' * 60)


HTML_TMPL = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>Kimi 额度报告</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f3f4f6;margin:0;padding:24px;color:#111827}}
h1{{font-size:20px;margin:0 0 4px}}.sub{{color:#6b7280;font-size:13px;margin-bottom:20px}}
.summary{{background:#fff;border-radius:12px;padding:16px 20px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:20px}}
.sum-title{{font-size:15px;font-weight:700}}
.sum-sub{{font-size:12px;color:#9ca3af;margin:2px 0 10px}}
.sum-sec{{font-size:13px;margin:6px 0;line-height:2}}
.pill{{display:inline-block;border-radius:999px;padding:1px 9px;font-size:12px;margin:1px 4px 1px 0;background:#f3f4f6;color:#374151}}
.pill.crit{{background:#fee2e2;color:#b91c1c}}
.pill.warn{{background:#fef3c7;color:#92400e}}
.pill.ok{{background:#d1fae5;color:#065f46}}
.pill.flat{{background:#e0f2fe;color:#075985}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}}
.card{{background:#fff;border-radius:12px;padding:18px 20px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.card.fail{{border:1px solid #fca5a5;background:#fef2f2}}
.name{{font-size:16px;font-weight:600;display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.tag{{font-size:11px;background:#e0e7ff;color:#3730a3;border-radius:999px;padding:2px 10px;font-weight:500}}
.key{{font-family:Consolas,monospace;font-size:12px;color:#9ca3af}}
.meta{{font-size:12px;color:#6b7280;margin:2px 0 12px}}
.row{{margin:10px 0}}.row .lbl{{display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px}}
.pct{{font-variant-numeric:tabular-nums;font-weight:600}}
.track{{height:10px;background:#e5e7eb;border-radius:999px;overflow:hidden}}
.fill{{height:100%;border-radius:999px}}
.ok{{background:linear-gradient(90deg,#34d399,#10b981)}}
.warn{{background:linear-gradient(90deg,#fbbf24,#f59e0b)}}
.crit{{background:linear-gradient(90deg,#f87171,#ef4444)}}
.reset{{font-size:12px;color:#9ca3af}}
.cmp{{font-size:12px;color:#6b7280;margin-top:-4px}}
.cmp.risk,.cmp.new_exhausted{{color:#b45309;font-weight:600}}
.wallet{{margin-top:12px;padding-top:10px;border-top:1px dashed #e5e7eb;font-size:13px;color:#374151}}
.err{{color:#dc2626;font-size:13px;margin-top:8px}}
</style></head><body>
<h1>Kimi for Coding 额度报告</h1>
<div class="sub">共 {total} 个 key，成功 {ok} 个 · 生成于 {now}（北京时间）</div>
{summary}
<div class="grid">{cards}</div>
</body></html>"""

CARD_TMPL = """<div class="card{fail_cls}">
<div class="name">{nickname} {tag}<span class="key">{key_mask}</span></div>
<div class="meta">{meta}</div>
{body}
</div>"""

ROW_TMPL = """<div class="row"><div class="lbl"><span>{title}</span><span class="pct">{pct:.2f}%</span></div>
<div class="track"><div class="fill {cls}" style="width:{width:.2f}%"></div></div>
<div class="reset">重置时间 {reset}</div></div>"""


def render_summary_html(results, baseline):
    g, usable = summarize(results)
    base_ts = parse_dt(baseline['ts'])
    dt_h = (datetime.now(CST) - base_ts).total_seconds() / 3600
    total_ok = sum(1 for r in results if r['ok'])

    def pills(rs, cls, fmt=None):
        if not rs:
            return '<span class="pill">无</span>'
        return ''.join('<span class="pill %s">%s</span>' % (cls, html.escape(fmt(r) if fmt else r.get('nickname', '?')))
                       for r in rs)

    secs = [f'<div class="sum-sec">当前可用 <b>{len(usable)}</b> / {total_ok} 个 key（7天窗口未耗尽）</div>',
            f'<div class="sum-sec">新增耗尽（{len(g["new_exhausted"])}）：{pills(g["new_exhausted"], "crit")}</div>',
            f'<div class="sum-sec">撑不到重置（{len(g["risk"])}）：' +
            pills(g['risk'], 'warn', lambda r: f'{r.get("nickname", "?")} {r["cmp"]["rate_pd"]:.0f}pp/天→预计{r["cmp"]["eta"].strftime("%m-%d %H:%M")}') + '</div>',
            f'<div class="sum-sec">可撑到重置（{len(g["safe"])}）：{pills(g["safe"], "ok")}</div>',
            f'<div class="sum-sec">回落/持平（{len(g["flat"])}）：{pills(g["flat"], "flat")}</div>']
    if g['short']:
        secs.append(f'<div class="sum-sec">间隔太短未预测（{len(g["short"])}）：{pills(g["short"], "")}</div>')
    return ('<div class="summary"><div class="sum-title">对比与预测</div>'
            f'<div class="sum-sub">基线 {base_ts.strftime("%m-%d %H:%M")}（{dt_h:.1f}h 前）'
            ' · 速率 = 两次探测间净消耗线性外推，滚动窗口下仅供参考</div>' + ''.join(secs) + '</div>')


def render_html(results, path, baseline=None):
    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    cards = []
    for r in results:
        tag = f'<span class="tag">{html.escape(r["label"])}</span>' if r['label'] else ''
        if not r['ok']:
            body = f'<div class="err">✗ 查询失败：{html.escape(r["error"])}</div>'
            cards.append(CARD_TMPL.format(fail_cls=' fail', nickname='（无效 key）', tag=tag,
                                          key_mask=html.escape(r['key_mask']), meta='', body=body))
            continue
        meta = ' · '.join(x for x in [html.escape(r.get('phone', '')), f"user_id {r.get('user_id', '')}"] if x)
        body = ROW_TMPL.format(title='5 小时窗口', pct=r['h5_ratio'] * 100, cls=color_cls(r['h5_ratio']),
                               width=min(100, r['h5_ratio'] * 100), reset=fmt_reset(r['h5_reset']))
        body += ROW_TMPL.format(title='7 天窗口', pct=r['d7_ratio'] * 100, cls=color_cls(r['d7_ratio']),
                                width=min(100, r['d7_ratio'] * 100), reset=fmt_reset(r['d7_reset']))
        if r.get('cmp'):
            body += f'<div class="cmp {r["cmp"]["verdict"]}">对比 {r["cmp"]["base_ts"].strftime("%m-%d %H:%M")}：{html.escape(cmp_line(r))}</div>'
        body += (f'<div class="wallet">加油包月消费 <b>¥{r["booster_used"]:.2f}</b> / 上限 ¥{r["booster_limit"]:.2f}'
                 f' · 状态 {html.escape(r["booster_status"])}</div>')
        cards.append(CARD_TMPL.format(fail_cls='', nickname=html.escape(r.get('nickname', '?')), tag=tag,
                                      key_mask=html.escape(r['key_mask']), meta=meta, body=body))
    now = datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')
    summary = render_summary_html(results, baseline) if baseline else ''
    doc = HTML_TMPL.format(total=len(results), ok=sum(1 for r in results if r['ok']),
                           now=now, summary=summary, cards='\n'.join(cards))
    with open(path, 'w', encoding='utf-8') as f:
        f.write(doc)


def load_keys(args):
    items = []
    for k in args.keys or []:
        items.append(('', k.strip()))
    if args.keys_file:
        with open(args.keys_file, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(None, 1)
                key = parts[0]
                label = parts[1].strip() if len(parts) > 1 else ''
                items.append((label, key))
    if args.include_pi:
        try:
            auth = json.load(open(os.path.expanduser('~/.pi/agent/auth.json'), encoding='utf-8'))['kimi-coding']
            items.append(('pi auth.json', auth['key'] if isinstance(auth, dict) else auth))
        except Exception as e:
            print(f'警告: 读取 pi auth.json 失败: {e}', file=sys.stderr)
    # 按 key 去重，保留首个 label
    seen, uniq = set(), []
    for label, key in items:
        if key not in seen:
            seen.add(key)
            uniq.append((label, key))
    return uniq


def main():
    ap = argparse.ArgumentParser(description='Kimi for Coding 额度批量查询')
    ap.add_argument('keys', nargs='*', help='sk-kimi- 开头的 key，可多个')
    ap.add_argument('-f', '--keys-file', help='key 列表文件，每行: <key> [别名]')
    ap.add_argument('--include-pi', action='store_true', help='顺带查询 pi auth.json 中的 kimi-coding key')
    ap.add_argument('--html', nargs='?', const=DEFAULT_HTML,
                    help='输出 HTML 报告（可指定路径，默认 assets/reports/，文件名自动追加 _年月日-时分秒）')
    ap.add_argument('--open', dest='open_browser', action='store_true',
                    help='生成 HTML 报告后自动用默认浏览器打开')
    ap.add_argument('--no-save', action='store_true', help='本次结果不写入历史快照')
    ap.add_argument('--baseline-gap', type=float, default=2.0,
                    help='对比基线的最小间隔小时数（默认 2.0，避免短间隔噪声）')
    ap.add_argument('--import-html', nargs='+', metavar='REPORT.html',
                    help='把旧 HTML 报告导入历史快照后退出（不探测）')
    args = ap.parse_args()

    if args.import_html:
        import_html(args.import_html)
        return

    items = load_keys(args)
    if not items:
        ap.error('没有可查询的 key（传参、-f 文件或 --include-pi）')

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(probe, items))

    now = datetime.now(CST)
    baseline = pick_baseline(load_history(), now, args.baseline_gap)
    if baseline and attach_compare(results, baseline, now) == 0:
        baseline = None  # 历史里没有共同 key

    print_console(results)
    if baseline:
        print_compare_summary(results, baseline)
    else:
        print('\n（暂无历史基线，未做对比预测）')

    if not args.no_save:
        save_snapshot(results)
        print(f'历史快照已追加 → {HISTORY_FILE}（共 {len(load_history())} 条）')

    if args.html:
        stem, ext = os.path.splitext(args.html)
        path = f"{stem}_{datetime.now(CST).strftime('%Y%m%d-%H%M%S')}{ext}"
        render_html(results, path, baseline)
        print(f'\nHTML 报告: {os.path.abspath(path)}')
        if args.open_browser:
            try:
                os.startfile(path)  # Windows：用默认关联程序（浏览器）打开
            except (OSError, AttributeError) as exc:
                print(f'自动打开浏览器失败，请手动打开上方路径: {exc}')


if __name__ == '__main__':
    main()

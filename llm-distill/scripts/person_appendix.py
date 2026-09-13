#!/usr/bin/env python3
"""person_appendix.py — 生成某人当天的会话清单附录（Markdown）。

用法: python3 person_appendix.py <distill_dir> <key_name>
输出: 该人全部去重会话的清单（按大小排序），每个含首条用户提问 + 末尾 assistant 结论段截取。
"""
import os, re, sys

d, person = sys.argv[1], sys.argv[2]
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 25

BOT_PREFIXES = (
    '<local-command-caveat', '<system-reminder', 'Caveat:', '[tool_result]',
    '[SYSTEM NOTIFICATION', '<command-message>', '<command-name>',
    'This is an automatically generated checkpoint',
    'The conversation history before this point',
    '[SUGGESTION MODE', 'You are deciding whether', 'Generate a short kebab-case',
    'reply with exactly', 'You are the Skill extraction sub-agent',
    '[Request interrupted by user]', 'The user stepped away',
    'Current runtime context',
)

def users(txt):
    out = []
    for b in txt.split('===== user =====')[1:]:
        seg = re.split(r'===== (?:assistant|system) =====', b)[0].strip()
        if seg.startswith(BOT_PREFIXES):
            continue
        seg = re.sub(r'\s+', ' ', seg)
        if len(seg) > 15:
            out.append(seg)
    return out

def last_assistant(txt):
    blocks = txt.split('===== assistant =====')
    for b in reversed(blocks[1:]):
        seg = re.split(r'===== (?:user|system) =====', b)[0].strip()
        seg = re.sub(r'\[tool_use[^\]]*\][^\n]*', '', seg)
        seg = re.sub(r'\[thinking\][^\n]*', '', seg)
        seg = re.sub(r'\s+', ' ', seg).strip()
        if len(seg) > 60:
            return seg
    return ''

rows = []
for fn in os.listdir(d):
    if not fn.startswith(person + '_') or fn == 'index.tsv':
        continue
    path = os.path.join(d, fn)
    txt = open(path, errors='ignore').read()
    rows.append((os.path.getsize(path), fn, users(txt), last_assistant(txt)))

rows.sort(reverse=True)
total = sum(r[0] for r in rows)
shown = rows[:LIMIT]
print(f'## 会话清单附录（共 {len(rows)} 个去重会话 / {total//1024}K，下列按大小前 {len(shown)} 个）\n')
for sz, fn, ums, last in shown:
    print(f'### `{fn}`（{sz//1024}K）')
    if ums:
        for m in ums[:3]:
            print(f'- 问：{m[:300]}')
    else:
        print('- （无人工提问文本，机器人/compaction 会话）')
    if last:
        print(f'- 收尾：{last[:400]}')
    print()
if len(rows) > LIMIT:
    rest = rows[LIMIT:]
    print(f'\n其余 {len(rest)} 个碎片会话（共 {sum(r[0] for r in rest)//1024}K，多为机器人/快照/轻量操作）未逐条列出。')

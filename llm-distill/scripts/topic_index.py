#!/usr/bin/env python3
"""topic_index.py — 对 distill 目录生成话题索引（每会话提取人类提问前几条，按文件大小排序）。

用法: python3 topic_index.py /tmp/distill > /tmp/topics.txt
"""
import os, re, sys

d = sys.argv[1] if len(sys.argv) > 1 else '/tmp/distill'

# 明显的机器人/系统消息前缀，不作为"人类提问"
BOT_PREFIXES = (
    '<local-command-caveat', '<system-reminder', 'Caveat:', '[tool_result]',
    '[SYSTEM NOTIFICATION', '<command-message>', '<command-name>',
)

out = []
for fn in sorted(os.listdir(d)):
    if fn == 'index.tsv' or not fn.endswith('.txt'):
        continue
    path = os.path.join(d, fn)
    txt = open(path, errors='ignore').read()
    user_msgs = []
    for b in txt.split('===== user =====')[1:]:
        seg = b.split('=====')[0].strip()
        if seg.startswith(BOT_PREFIXES):
            continue
        seg = re.sub(r'\s+', ' ', seg)
        if len(seg) > 15:
            user_msgs.append(seg[:200])
    if user_msgs:
        out.append((fn, os.path.getsize(path), user_msgs[:3]))

out.sort(key=lambda x: -x[1])
for fn, sz, msgs in out:
    print(f'### {fn} ({sz // 1024}K)')
    for m in msgs:
        print('   -', m[:180])

#!/usr/bin/env python3
"""session_read.py — 读取单个会话 transcript 文件，按角色抽取文本块。

用法:
  python3 session_read.py <file.txt>                  # 全部（user+assistant）
  python3 session_read.py <file.txt> --user           # 只看人类提问
  python3 session_read.py <file.txt> --assistant      # 只看 assistant 结论段
  python3 session_read.py <file.txt> --assistant --tail 4000   # 只打末尾 4000 字符
"""
import re, sys

args = sys.argv[1:]
path = args[0]
role = 'user' if '--user' in args else ('assistant' if '--assistant' in args else None)
thinking_only = '--thinking' in args
if thinking_only and role is None:
    role = 'assistant'
tail = None
if '--tail' in args:
    tail = int(args[args.index('--tail') + 1])

txt = open(path, errors='ignore').read()

if role is None:
    print(txt)
    sys.exit(0)

blocks = txt.split(f'===== {role} =====')
out = []
for b in blocks[1:]:
    # 块结束于下一个角色标记
    seg = re.split(r'===== (?:user|assistant|system) =====', b)[0].strip()
    if thinking_only:
        # 抽 [thinking] 标记的思维链段落（内容可多行，终止于下一个 [ 标记或块尾）
        out.extend(re.findall(r'\[thinking\] (.*?)(?=\n\[(?:thinking|tool_result|tool_use)[^\]]*\] |\Z)',
                              seg, re.S))
        continue
    # 去掉 tool_use 噪音行，只留文本
    seg = re.sub(r'\[tool_use[^\]]*\][^\n]*', '', seg)
    if role == 'user':
        if seg.startswith(('[tool_result]', '<system-reminder', 'Caveat:',
                           '<local-command-caveat', '[SYSTEM NOTIFICATION')):
            continue
    if len(seg) > (15 if role == 'user' else 100):
        out.append(seg)

joined = '\n---\n'.join(out)
try:
    print(joined[-tail:] if tail else joined)
except BrokenPipeError:
    pass

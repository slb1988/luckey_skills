#!/usr/bin/env python3
"""把 pi-trace.jsonl 轮转为带时间戳的备份，让每轮测试/分析从干净文件开始。

Pi 扩展按事件 appendFileSync 追加写 trace，无持久句柄：会话运行中 move 也安全，
下一个事件会自动重建新文件。备份统一放到 state dir 的 trace-backups/ 子目录，
避免污染 state dir 顶层的 glob/检索。

用法（每轮 eval / 真实 Pi 成对测试前执行）：

    python3 scripts/rotate_pi_trace.py                 # 轮转 pi-trace.jsonl
    python3 scripts/rotate_pi_trace.py --include-hook-trace  # 连同 hook-trace.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from memory_hook import default_state_dir

PI_TRACE = "pi-trace.jsonl"
HOOK_TRACE = "hook-trace.jsonl"


def rotate_trace(state_dir: Path, name: str = PI_TRACE) -> dict:
    """把 state_dir/<name> 移到 trace-backups/<stem>-<UTC时间戳>.jsonl。

    同分区 os.replace 语义，原子；文件名撞秒时追加 -2/-3 后缀。
    源文件不存在时返回 rotated=False，不视为错误（本来就没有旧数据）。
    """
    source = state_dir / name
    if not source.is_file():
        return {"name": name, "rotated": False, "reason": "missing"}
    backup_dir = state_dir / "trace-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = name[: -len(".jsonl")] if name.endswith(".jsonl") else name
    candidate = backup_dir / ("%s-%s.jsonl" % (stem, stamp))
    suffix = 2
    while candidate.exists():
        candidate = backup_dir / ("%s-%s-%d.jsonl" % (stem, stamp, suffix))
        suffix += 1
    size = source.stat().st_size
    source.replace(candidate)
    return {
        "name": name,
        "rotated": True,
        "backup": str(candidate),
        "bytes": size,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        default=None,
        help="覆盖 state dir（默认取 MEMORY_HOOK_STATE_DIR 或 ~/.local/state/memory-hub-hook）",
    )
    parser.add_argument(
        "--include-hook-trace",
        action="store_true",
        help="同时轮转 hook-trace.jsonl（脚本侧 ground truth）",
    )
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir).expanduser() if args.state_dir else default_state_dir()
    names = [PI_TRACE] + ([HOOK_TRACE] if args.include_hook_trace else [])
    results = [rotate_trace(state_dir, name) for name in names]
    print(json.dumps({"state_dir": str(state_dir), "traces": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

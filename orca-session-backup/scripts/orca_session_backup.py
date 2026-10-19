#!/usr/bin/env python3
"""Orca 会话备份 / 恢复：把 Orca 终端里的 agent 会话序列化成可读 .md，按需恢复。

用法：
  python orca_session_backup.py backup [--worktree SEL | --all] [--out DIR]
  python orca_session_backup.py restore FILE.md [--only 1,3] [--dry-run] [--force]

backup 只读：调用 `orca terminal list`，读取 Orca terminal-history 与各 agent 的本地会话文件
（Pi: ~/.pi/agent/sessions，Claude: ~/.claude/projects），不关闭、不修改任何东西。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

HOME = Path.home()
APPDATA = Path(os.environ.get("APPDATA", HOME / "AppData" / "Roaming"))
ORCA_HISTORY = APPDATA / "orca" / "terminal-history"
PI_SESSIONS = HOME / ".pi" / "agent" / "sessions"
CLAUDE_PROJECTS = HOME / ".claude" / "projects"
DEFAULT_OUT = HOME / ".orca" / "session-backups"
MARK = "orca-session-backup"
IS_WIN = os.name == "nt"

ANSI_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"          # CSI
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC
    r"|\x1b[@-Z\\-_]"                    # 2-byte
)
WS_RE = re.compile(r"\s+")


# ---------------------------------------------------------------- helpers

def norm(text: str) -> str:
    """去 ANSI 与全部空白：TUI 常用光标移动代替空格，比较时统一去掉。"""
    return WS_RE.sub("", ANSI_RE.sub("", text))


def parse_ts(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value / 1000 if value > 1e11 else float(value)
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def fmt_ts(ts: float | None, with_year: bool = False) -> str:
    if not ts:
        return "?"
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M" if with_year else "%m-%d %H:%M")


def one_line(text: str, limit: int) -> str:
    text = WS_RE.sub(" ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def orca_exe() -> str:
    exe = shutil.which("orca")
    if not exe:
        sys.exit("找不到 orca CLI（确认 Orca 已安装且 `orca` 在 PATH 中）")
    return exe


def orca_json(*args: str) -> dict:
    proc = subprocess.run([orca_exe(), *args, "--json"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit(f"orca {' '.join(args)} 输出无法解析：\n{proc.stdout[:500]}\n{proc.stderr[:500]}")
    if not data.get("ok", True):
        sys.exit(f"orca {' '.join(args)} 失败：{json.dumps(data, ensure_ascii=False)[:500]}")
    return data.get("result", data)


# ---------------------------------------------------------------- sessions

@dataclass
class Session:
    agent: str
    id: str
    path: Path
    cwd: str
    started: float | None = None
    last_active: float | None = None
    name: str = ""
    model: str = ""
    prompts: list[str] = field(default_factory=list)
    last_reply: str = ""
    files: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.name or (one_line(self.prompts[0], 40) if self.prompts else self.id[:8])

    def resume_cmd(self) -> str:
        return {"pi": f"pi --session {self.id}", "claude": f"claude --resume {self.id}"}[self.agent]


def _add_file(files: list[str], cwd: str, path: str | None):
    if not path:
        return
    p = path if re.match(r"^([A-Za-z]:|/|\\)", path) else str(Path(cwd) / path)
    p = p.replace("\\", "/")
    if p not in files:
        files.append(p)


def load_pi(path: Path) -> Session | None:
    s = None
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = o.get("type")
        if t == "session":
            s = Session("pi", o["id"], path, o.get("cwd", ""), parse_ts(o.get("timestamp")))
            continue
        if s is None:
            return None
        ts = parse_ts(o.get("timestamp"))
        if ts:
            s.last_active = ts
        if t == "session_info" and o.get("name"):
            s.name = o["name"]
        elif t == "model_change":
            s.model = o.get("modelId", s.model)
        elif t == "message":
            m = o.get("message") or {}
            content = m.get("content")
            items = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]
            if m.get("role") == "user":
                text = " ".join(i.get("text", "") for i in items if i.get("type") == "text").strip()
                if text:
                    s.prompts.append(text)
            elif m.get("role") == "assistant":
                text = "\n".join(i.get("text", "") for i in items if i.get("type") == "text").strip()
                if text:
                    s.last_reply = text
                for i in items:
                    if i.get("type") == "toolCall" and i.get("name") in ("write", "edit"):
                        _add_file(s.files, s.cwd, (i.get("arguments") or {}).get("path"))
    if s and not s.last_active:
        s.last_active = path.stat().st_mtime
    return s


def load_claude(path: Path) -> Session | None:
    s = Session("claude", path.stem, path, "")
    custom_title = ai_title = ""
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = o.get("type")
        if t == "custom-title":
            custom_title = o.get("customTitle") or custom_title
        elif t == "ai-title":
            ai_title = o.get("aiTitle") or ai_title
        s.name = custom_title or ai_title
        ts = parse_ts(o.get("timestamp"))
        if ts:
            s.started = s.started or ts
            s.last_active = ts
        s.cwd = s.cwd or o.get("cwd", "")
        if t not in ("user", "assistant"):
            continue
        if o.get("isSidechain") or o.get("isMeta"):
            continue
        m = o.get("message") or {}
        content = m.get("content")
        items = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]
        if t == "user":
            text = " ".join(i.get("text", "") for i in items if i.get("type") == "text").strip()
            if text and not text.startswith("<") and not text.startswith("[Request interrupted"):
                s.prompts.append(text)
        else:
            s.model = m.get("model", s.model)
            text = "\n".join(i.get("text", "") for i in items if i.get("type") == "text").strip()
            if text:
                s.last_reply = text
            for i in items:
                if i.get("type") == "tool_use" and i.get("name") in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                    inp = i.get("input") or {}
                    _add_file(s.files, s.cwd, inp.get("file_path") or inp.get("notebook_path"))
    return s if s.prompts else None


def session_dir(agent: str, cwd: str) -> Path:
    if agent == "pi":
        return PI_SESSIONS / ("--" + re.sub(r"[/\\:]", "-", cwd.lstrip("/\\")) + "--")
    return CLAUDE_PROJECTS / re.sub(r"[^A-Za-z0-9]", "-", cwd)


_session_cache: dict[tuple[str, str], list[Session]] = {}


LOOKBACK_DAYS = 30


def sessions_for(agent: str, cwd: str) -> list[Session]:
    """cwd 下最近 LOOKBACK_DAYS 天有改动的会话。不按终端启动时间过滤：Orca 重启后会在新 PTY 里
    resume 旧会话，此时会话最后活动可能早于终端启动。"""
    key = (agent, cwd)
    if key not in _session_cache:
        since = dt.datetime.now().timestamp() - LOOKBACK_DAYS * 86400
        loader = load_pi if agent == "pi" else load_claude
        d = session_dir(agent, cwd)
        files = [f for f in d.glob("*.jsonl") if f.stat().st_mtime >= since] if d.is_dir() else []
        _session_cache[key] = [s for s in map(loader, files) if s]
    return _session_cache[key]


# ---------------------------------------------------------------- terminals

@dataclass
class Tab:
    handle: str
    pty_id: str
    title: str
    agent: str
    worktree_id: str
    worktree_path: str
    branch: str
    started: float | None
    preview: str
    text: str = ""            # 归一化后的终端历史，用于内容匹配
    sessions: list[tuple[Session, list[str]]] = field(default_factory=list)  # (session, 匹配依据)


def load_tab(t: dict) -> Tab:
    hist = ORCA_HISTORY / quote(t["ptyId"], safe="-_.~")
    started, text = None, ""
    try:
        started = parse_ts(json.loads((hist / "meta.json").read_text(encoding="utf-8")).get("startedAt"))
    except (OSError, json.JSONDecodeError):
        pass
    parts = []
    for name in ("output.log", "checkpoint.json"):
        try:
            raw = (hist / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if name == "checkpoint.json":
            try:
                raw = json.loads(raw).get("snapshotAnsi", "")
            except json.JSONDecodeError:
                pass
        parts.append(raw)
    text = norm("\n".join(parts) + t.get("preview", ""))
    branch = (t.get("branch") or "").removeprefix("refs/heads/")
    return Tab(t["handle"], t["ptyId"], t.get("title", ""), t.get("agentIdentity") or "",
               t["worktreeId"], t["worktreePath"], branch, started, t.get("preview", ""), text)


def content_hits(tab: Tab, s: Session) -> int:
    hits = 0
    for p in s.prompts:
        snippet = norm(p)[:24]
        if len(snippet) >= 10 and snippet in tab.text:  # 太短的（continue / git commit）到处都有
            hits += 1
    return hits


def tab_title_core(title: str) -> str:
    """去掉 Claude/Pi 写在标题前面的状态符号（✳ ◐ ⠋ π 等）。"""
    return re.sub(r"^[^\w(\[]+", "", title).strip()


def evidence(tab: Tab, s: Session) -> tuple[int, list[str]]:
    score, why = 0, []
    if s.name and tab_title_core(tab.title) == s.name:
        score, why = score + 5, why + ["终端标题 = 会话标题"]
    if tab.started and s.started and abs(s.started - tab.started) <= 20:
        score, why = score + 3, why + ["启动时间吻合"]
    hits = content_hits(tab, s)
    # 只有内容命中时要求同类 agent，且 ≥2 条或会话在终端打开后仍有活动（共享路径、相似提问会串台）
    if hits and (score or (s.agent == tab.agent and (
            hits >= 2 or (tab.started and (s.last_active or 0) >= tab.started)))):
        score, why = score + hits, why + [f"终端内容命中 {hits} 条"]
    return score, why


def map_sessions(tabs: list[Tab]) -> dict[tuple[str, str], list[Session]]:
    """把会话分配给终端：标题吻合 > 启动时间吻合 > 终端内容命中，按总分贪心分配，每个会话只归属一个终端。
    Orca 的 agentIdentity 不可靠（pi 标签里可能跑着 claude），所以两种 agent 的会话都参与匹配。
    返回各 (agent, cwd) 下未被任何终端认领的会话。"""
    scored: list[tuple[int, Tab, Session, list[str]]] = []
    for tab in tabs:
        if tab.agent not in ("pi", "claude"):
            continue
        for agent in ("pi", "claude"):
            for s in sessions_for(agent, tab.worktree_path):
                score, why = evidence(tab, s)
                if score:
                    scored.append((score, tab, s, why))
    scored.sort(key=lambda x: -x[0])
    claimed: set[Path] = set()
    for _, tab, s, why in scored:
        if s.path in claimed:
            continue
        claimed.add(s.path)
        tab.sessions.append((s, why))
    for tab in tabs:
        tab.sessions.sort(key=lambda x: -(x[0].last_active or 0))
    leftovers: dict[tuple[str, str], list[Session]] = {}
    for key, sess in _session_cache.items():
        rest = [s for s in sess if s.path not in claimed]
        if rest:
            leftovers[key] = sorted(rest, key=lambda s: -(s.last_active or 0))
    return leftovers


SELECTOR_PREFIXES = ("id:", "path:", "name:", "branch:", "identity:", "issue:")


def resolve_worktree(arg: str) -> str:
    """接受 Orca selector，也接受裸目录名 / 路径（name: 匹配的是 displayName，常是分支名，易踩坑）。"""
    if arg.startswith(SELECTOR_PREFIXES) or arg in ("active", "current"):
        return arg
    if re.match(r"^([A-Za-z]:|/|~)", arg):
        return "path:" + str(Path(arg).expanduser()).replace("\\", "/")
    rows = orca_json("worktree", "list").get("worktrees", [])
    hits = [w for w in rows if Path(w["path"]).name.lower() == arg.lower() or w.get("displayName") == arg]
    if len(hits) != 1:
        found = ", ".join(w["path"] for w in hits) or "无"
        sys.exit(f"无法唯一定位工作区 {arg!r}（匹配：{found}），请改用 path:<绝对路径>")
    return "path:" + hits[0]["path"]


def collect(worktree: str | None) -> tuple[list[Tab], dict]:
    args = ["terminal", "list", "--limit", "1000"]
    if worktree:
        args += ["--worktree", worktree]
    result = orca_json(*args)
    tabs = [load_tab(t) for t in result.get("terminals", []) if t.get("worktreePath")]
    return tabs, map_sessions(tabs)


# ---------------------------------------------------------------- markdown

AGENT_ICON = {"pi": "π", "claude": "✳"}


def confidence(why: list[str]) -> str:
    strong = len(why) >= 2 or any(w.startswith(("终端标题", "启动时间")) for w in why)         or any(w.startswith("终端内容命中") and not w.endswith(" 1 条") for w in why)
    return ("✅ 高（" if strong else "🟡 中（") + " + ".join(why) + "）"


def cd_cmd(path: str) -> str:
    return f'cd /d "{path.replace("/", chr(92))}"' if IS_WIN else f'cd "{path}"'


def safe_title(text: str) -> str:
    return one_line(re.sub(r'[&|<>^"%!`$]', "", text).replace("\\", "/"), 28)


def render_entry(n: int, s: Session, tab: Tab | None, conf: str, note: str = "") -> list[str]:
    icon = AGENT_ICON.get(s.agent, "")
    title = safe_title(f"{icon} {s.title}")
    wt_path = tab.worktree_path if tab else s.cwd.replace("\\", "/")
    orca_cmd = (f'orca terminal create --worktree "path:{wt_path}" --title "{title}" '
                f'--command "{s.resume_cmd()}"')
    meta = {"n": n, "agent": s.agent, "session": s.id, "cwd": wt_path, "title": title,
            "handle": tab.handle if tab else None}
    lines = [
        f"### {n}. {icon} {one_line(s.title, 60)}",
        "",
        "- [ ] 已 review",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| Agent / 模型 | {s.agent}" + (f" · {s.model}" if s.model else "") + " |",
        f"| 会话 ID | `{s.id}` |",
        f"| 开始 → 最后活动 | {fmt_ts(s.started)} → **{fmt_ts(s.last_active)}** |",
        f"| 轮次 | {len(s.prompts)} |",
        f"| 原终端 | " + (f"{tab.title} · `{tab.handle}`" if tab else "（已不在任何打开的终端）") + " |",
        f"| 匹配置信度 | {conf} |",
    ]
    if note:
        lines.append(f"| 备注 | {note} |")
    lines += ["", f"**首问**：{one_line(s.prompts[0], 200)}"]
    if len(s.prompts) > 1:
        lines.append(f"\n**末问**：{one_line(s.prompts[-1], 200)}")
    if s.last_reply:
        reply = s.last_reply.strip().splitlines()
        reply = [r for r in reply if r.strip() and not r.lstrip().startswith("```")][:8]
        excerpt = "\n".join("> " + one_line(r, 160) for r in reply)
        lines += ["", "**最后回复（节选）**：", "", excerpt]
    if s.files:
        lines += ["", f"**产出 / 修改的文件**（{len(s.files)}）："]
        lines += [f"- `{f}`" for f in s.files[:20]]
        if len(s.files) > 20:
            lines.append(f"- …另 {len(s.files) - 20} 个")
    lines += [
        "",
        "恢复（手动）：",
        "",
        "```bat" if IS_WIN else "```sh",
        f"{cd_cmd(wt_path)} && {s.resume_cmd()}",
        "```",
        "",
        "恢复到 Orca 新标签：",
        "",
        "```bat" if IS_WIN else "```sh",
        orca_cmd,
        "```",
        "",
        f"<!-- {MARK} {json.dumps(meta, ensure_ascii=False)} -->",
        "",
    ]
    return lines


def render(tabs: list[Tab], leftovers: dict, scope: str, out_file: Path) -> str:
    now = dt.datetime.now()
    script = Path(__file__).resolve().as_posix()
    by_wt: dict[str, list[Tab]] = {}
    for tab in tabs:
        by_wt.setdefault(tab.worktree_path, []).append(tab)

    body: list[str] = []
    checklist: list[str] = []
    close_cmds: list[str] = []
    unmapped: list[str] = []
    n = 0
    for wt_path, wt_tabs in by_wt.items():
        agent_tabs = [t for t in wt_tabs if t.agent in ("pi", "claude")]
        others = [t for t in wt_tabs if t.agent not in ("pi", "claude")]
        if not agent_tabs and not others:
            continue
        name = Path(wt_path).name
        body += [f"## {name}", "", f"`{wt_path}`" + (f" · 分支 `{wt_tabs[0].branch}`" if wt_tabs[0].branch else ""), ""]
        for tab in sorted(agent_tabs, key=lambda t: t.started or 0):
            if not tab.sessions:
                unmapped.append(f"- `{tab.handle}` · {tab.agent} · {name} · {tab.title}"
                                f" — 未找到会话文件（可能尚未发过消息）")
                continue
            for idx, (s, why) in enumerate(tab.sessions):
                n += 1
                conf = confidence(why)
                note = "" if idx == 0 else "同一终端内较早的会话（agent 在此终端被重启过）"
                body += render_entry(n, s, tab, conf, note)
                checklist.append(f"- [ ] **{n}.** {AGENT_ICON[s.agent]} {one_line(s.title, 50)} · {name} · "
                                 f"最后活动 {fmt_ts(s.last_active)}")
            close_cmds.append(f"orca terminal close --terminal {tab.handle}")
        for tab in others:
            unmapped.append(f"- `{tab.handle}` · {tab.agent or 'shell'} · {name} · {tab.title}"
                            f" — 暂不支持该类型，未备份")
        # 同工作区里未被任何打开终端认领的近期会话（多半来自已关闭的终端）
        earliest = min((t.started for t in wt_tabs if t.started), default=0) - 60
        extra = sorted((s for agent in ("pi", "claude") for s in leftovers.get((agent, wt_path), [])
                        if (s.last_active or 0) >= earliest), key=lambda s: -(s.last_active or 0))[:10]
        if extra:
            body += ["#### 同工作区近期、但不在任何打开终端里的会话", "",
                     "> 多半是之前关掉的终端。默认不纳入「全部恢复」，需要时手动复制命令。", ""]
            for s in extra:
                body.append(f"- {AGENT_ICON[s.agent]} {fmt_ts(s.last_active)} · {one_line(s.title, 50)} · "
                            f"`{cd_cmd(wt_path)} && {s.resume_cmd()}`")
            body.append("")

    head = [
        "---",
        "tags: [orca-session-backup]",
        f"backup_at: {now.isoformat(timespec='seconds')}",
        f"scope: {scope}",
        "---",
        "",
        f"# Orca 会话备份 · {scope} · {now:%Y-%m-%d %H:%M}",
        "",
        f"> {len(tabs)} 个终端 → {n} 个会话。勾选「已 review」后可放心关闭对应终端。",
        "",
        "全部恢复（每个会话新开一个 Orca 标签，已在打开终端里的会自动跳过）：",
        "",
        "```bat" if IS_WIN else "```sh",
        f'python "{script}" restore "{out_file.as_posix()}"',
        "```",
        "",
        f"只恢复部分：在上面命令后加 `--only 1,3`；先看会执行什么：加 `--dry-run`。",
        "",
        "## 待 Review 清单",
        "",
        *checklist,
        "",
    ]
    tail = []
    if unmapped:
        tail += ["## 未备份的终端", "", *unmapped, ""]
    if close_cmds:
        tail += ["## 备份后关闭这些终端（确认无误再执行）", "",
                 "```bat" if IS_WIN else "```sh", *close_cmds, "```", ""]
    return "\n".join(head + body + tail)


# ---------------------------------------------------------------- commands

def cmd_backup(args):
    if args.all:
        worktree, scope = None, "all"
    else:
        worktree = resolve_worktree(args.worktree or "active")
        scope = None
    tabs, leftovers = collect(worktree)
    if not tabs:
        sys.exit("没有找到打开的终端")
    if scope is None:
        scope = Path(tabs[0].worktree_path).name if len({t.worktree_path for t in tabs}) == 1 else "mixed"
    out_dir = Path(args.out).expanduser() if args.out else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"orca-sessions-{re.sub(r'[^A-Za-z0-9_.-]', '-', scope)}-{dt.datetime.now():%Y%m%d-%H%M}.md"
    out_file.write_text(render(tabs, leftovers, scope, out_file), encoding="utf-8")
    n = sum(len(t.sessions) for t in tabs)
    print(f"已备份 {len(tabs)} 个终端 / {n} 个会话 → {out_file}")


def cmd_restore(args):
    text = Path(args.file).read_text(encoding="utf-8")
    entries = [json.loads(m) for m in re.findall(rf"<!-- {MARK} (\{{.*?\}}) -->", text)]
    if args.only:
        wanted = {int(x) for x in args.only.split(",") if x.strip()}
        entries = [e for e in entries if e["n"] in wanted]
    if not entries:
        sys.exit("没有可恢复的条目")
    live: set[str] = set()
    if not args.force:
        for cwd in {e["cwd"] for e in entries}:
            tabs, _ = collect(f"path:{cwd}")
            live |= {s.id for t in tabs for s, _ in t.sessions}
    for e in entries:
        label = f"#{e['n']} {e['agent']} {e['session'][:8]} {e['title']}"
        if e["session"] in live:
            print(f"跳过 {label}（已在打开的终端里，--force 可强制再开）")
            continue
        cmd = {"pi": f"pi --session {e['session']}", "claude": f"claude --resume {e['session']}"}[e["agent"]]
        argv = ["terminal", "create", "--worktree", f"path:{e['cwd']}", "--title", e["title"], "--command", cmd]
        if args.dry_run:
            print(f"[dry-run] {label}: orca {' '.join(argv)}")
            continue
        res = orca_json(*argv)
        handle = (res.get("terminal") or {}).get("handle") or res.get("handle") or "?"
        print(f"已恢复 {label} → {handle}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup", help="备份终端里的 agent 会话为 .md")
    g = b.add_mutually_exclusive_group()
    g.add_argument("--worktree", help="Orca worktree selector，如 name:angelscript-merge / path:E:/x（默认 active）")
    g.add_argument("--all", action="store_true", help="备份所有工作区")
    b.add_argument("--out", help=f"输出目录（默认 {DEFAULT_OUT}）")
    b.set_defaults(func=cmd_backup)
    r = sub.add_parser("restore", help="从备份 .md 恢复会话到 Orca 新标签")
    r.add_argument("file")
    r.add_argument("--only", help="只恢复这些编号，如 1,3")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--force", action="store_true", help="已在打开终端里的会话也再开一个")
    r.set_defaults(func=cmd_restore)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

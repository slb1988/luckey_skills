#!/usr/bin/env python3
"""
cli-anything-obsidian: Stateful CLI harness for Obsidian vault automation.

Usage:
    python obsidian_cli.py --vault /path/to/vault [--json] <command> [args]

State persists via ~/.cli-anything-obsidian.json (last used vault path).
"""

import json
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── Optional click import (graceful fallback) ─────────────────────────────────
try:
    import click
    HAS_CLICK = True
except ImportError:
    HAS_CLICK = False

# ── State file ────────────────────────────────────────────────────────────────
STATE_FILE = Path.home() / ".cli-anything-obsidian.json"

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

# ── Vault helpers ─────────────────────────────────────────────────────────────

def resolve_vault(vault_arg: Optional[str]) -> Path:
    """Resolve vault path from arg or saved state."""
    state = load_state()
    if vault_arg:
        p = Path(vault_arg).expanduser().resolve()
    elif "vault" in state:
        p = Path(state["vault"])
    else:
        raise RuntimeError(
            "No vault specified. Use --vault /path/to/vault or run:\n"
            "  python obsidian_cli.py vault set /path/to/vault"
        )
    if not p.is_dir():
        raise RuntimeError(f"Vault directory not found: {p}")
    return p

def vault_name(vault_path: Path) -> str:
    """Return Obsidian vault name (directory name)."""
    return vault_path.name

def note_path(vault: Path, rel: str) -> Path:
    """Resolve a relative note path, appending .md if needed."""
    if not rel.endswith(".md"):
        rel = rel + ".md"
    return vault / rel

def obsidian_uri(vault: Path, **params) -> str:
    """Build obsidian://advanced-uri?vault=...&... URI."""
    base = "obsidian://advanced-uri"
    p = {"vault": vault_name(vault)}
    p.update(params)
    return base + "?" + urllib.parse.urlencode(p)

def launch_uri(uri: str):
    """Launch an Obsidian URI on Windows."""
    subprocess.Popen(["cmd", "/c", "start", "", uri], shell=False)

# ── Output helpers ────────────────────────────────────────────────────────────

_JSON_MODE = False

def out(data):
    """Output data - JSON dict/list or plain text string."""
    if _JSON_MODE:
        if isinstance(data, str):
            print(json.dumps({"result": data}, ensure_ascii=False))
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if isinstance(data, (dict, list)):
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(data)

def err(msg: str):
    data = {"error": msg}
    if _JSON_MODE:
        print(json.dumps(data), file=sys.stderr)
    else:
        print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

# ── Tag parsing ───────────────────────────────────────────────────────────────

def extract_tags(content: str) -> list[str]:
    """Extract #tags and frontmatter tags from note content."""
    tags = set()
    # Strip fenced code blocks before scanning inline tags
    stripped = re.sub(r'```[\s\S]*?```', '', content)
    stripped = re.sub(r'`[^`]+`', '', stripped)
    # C/preprocessor keywords to ignore
    CPP_KEYWORDS = {"include", "define", "ifdef", "ifndef", "endif", "else", "elif",
                    "pragma", "undef", "error", "warning", "if", "line"}
    # inline #tags — must start at word boundary, not just any non-space
    # Obsidian tags: start with letter or _, no pure-numeric tags
    # Skip lines that start with # (headings) — tags won't be alone at line start
    for m in re.finditer(r'(?<=\s)#([A-Za-z_][A-Za-z0-9_\-/]*)', stripped):
        tag_val = m.group(1)
        if tag_val not in CPP_KEYWORDS:
            tags.add(tag_val)
    # frontmatter tags: field
    fm = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if fm:
        block = fm.group(1)
        # tags: [a, b] or tags:\n  - a
        m = re.search(r'^tags:\s*\[([^\]]+)\]', block, re.MULTILINE)
        if m:
            for t in re.split(r'[,\s]+', m.group(1)):
                t = t.strip().strip('"\'')
                if t:
                    tags.add(t)
        for m in re.finditer(r'^\s+-\s+(.+)', block, re.MULTILINE):
            tags.add(m.group(1).strip())
    return sorted(tags)

def extract_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter (simple key:value, no full YAML parser needed)."""
    fm = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not fm:
        return {}
    result = {}
    for line in fm.group(1).splitlines():
        m = re.match(r'^(\w[\w\-]*):\s*(.*)', line)
        if m:
            result[m.group(1)] = m.group(2).strip()
    return result

def strip_frontmatter(content: str) -> str:
    return re.sub(r'^---\n.*?\n---\n?', '', content, flags=re.DOTALL)

def scan_notes(vault: Path) -> list[Path]:
    """Return all .md files in vault (excluding .obsidian/)."""
    return [
        p for p in vault.rglob("*.md")
        if ".obsidian" not in p.parts
    ]

# ══════════════════════════════════════════════════════════════════════════════
# COMMANDS (functional core — called by both CLI and direct import)
# ══════════════════════════════════════════════════════════════════════════════

# ── vault ─────────────────────────────────────────────────────────────────────

def cmd_vault_set(path: str):
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        err(f"Directory not found: {p}")
    state = load_state()
    state["vault"] = str(p)
    save_state(state)
    out({"vault": str(p), "name": p.name, "status": "saved"})

def cmd_vault_info(vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    notes = scan_notes(vault)
    folders = {n.parent.relative_to(vault) for n in notes}
    obsidian_dir = vault / ".obsidian"
    plugins = []
    cp = obsidian_dir / "community-plugins.json"
    if cp.exists():
        plugins = json.loads(cp.read_text(encoding="utf-8"))
    out({
        "name": vault_name(vault),
        "path": str(vault),
        "note_count": len(notes),
        "folder_count": len(folders),
        "plugins": plugins,
    })

def cmd_vault_list_notes(vault_arg: Optional[str] = None, folder: str = ""):
    vault = resolve_vault(vault_arg)
    notes = scan_notes(vault)
    if folder:
        prefix = (vault / folder).resolve()
        notes = [n for n in notes if str(n).startswith(str(prefix))]
    items = [{"path": str(n.relative_to(vault)), "modified": n.stat().st_mtime} for n in sorted(notes)]
    out(items)

# ── note ─────────────────────────────────────────────────────────────────────

def cmd_note_read(rel: str, vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    p = note_path(vault, rel)
    if not p.exists():
        err(f"Note not found: {rel}")
    content = p.read_text(encoding="utf-8")
    fm = extract_frontmatter(content)
    tags = extract_tags(content)
    body = strip_frontmatter(content)
    out({
        "path": rel if rel.endswith(".md") else rel + ".md",
        "frontmatter": fm,
        "tags": tags,
        "content": content,
        "body": body,
        "size": len(content),
        "lines": content.count("\n") + 1,
    })

def cmd_note_create(rel: str, content: str = "", title: str = "", open_after: bool = False, vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    p = note_path(vault, rel)
    if p.exists():
        err(f"Note already exists: {rel}. Use 'note update' to modify.")
    p.parent.mkdir(parents=True, exist_ok=True)
    if not content and title:
        content = f"# {title}\n"
    p.write_text(content, encoding="utf-8")
    result = {"path": str(p.relative_to(vault)), "created": True, "size": len(content)}
    if open_after:
        uri = obsidian_uri(vault, filepath=str(p.relative_to(vault)).replace("\\", "/"))
        launch_uri(uri)
        result["opened"] = True
    out(result)

def cmd_note_update(rel: str, content: str = "", append: str = "", prepend: str = "", vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    p = note_path(vault, rel)
    if not p.exists():
        err(f"Note not found: {rel}")
    existing = p.read_text(encoding="utf-8")
    if content:
        new_content = content
    elif append:
        new_content = existing.rstrip("\n") + "\n" + append
    elif prepend:
        new_content = prepend + "\n" + existing
    else:
        err("Provide --content, --append, or --prepend")
    p.write_text(new_content, encoding="utf-8")
    out({"path": str(p.relative_to(vault)), "updated": True, "size": len(new_content)})

def cmd_note_delete(rel: str, vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    p = note_path(vault, rel)
    if not p.exists():
        err(f"Note not found: {rel}")
    p.unlink()
    out({"path": rel, "deleted": True})

def cmd_note_open(rel: str, vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    p = note_path(vault, rel)
    fp = str(p.relative_to(vault)).replace("\\", "/")
    uri = obsidian_uri(vault, filepath=fp)
    launch_uri(uri)
    out({"opened": True, "path": fp, "uri": uri})

# ── search ────────────────────────────────────────────────────────────────────

def cmd_search(query: str, folder: str = "", case_sensitive: bool = False, limit: int = 50, vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    notes = scan_notes(vault)
    if folder:
        prefix = (vault / folder).resolve()
        notes = [n for n in notes if str(n.resolve()).startswith(str(prefix))]
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(query), flags)
    results = []
    for note in notes:
        try:
            content = note.read_text(encoding="utf-8")
        except Exception:
            continue
        matches = []
        for i, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                matches.append({"line": i, "text": line.strip()})
        if matches:
            results.append({
                "path": str(note.relative_to(vault)),
                "matches": matches[:5],
                "match_count": len(matches),
            })
        if len(results) >= limit:
            break
    out({"query": query, "results": results, "total_files": len(results)})

# ── tags ──────────────────────────────────────────────────────────────────────

def cmd_tag_list(vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    tag_counts: dict[str, int] = {}
    for note in scan_notes(vault):
        try:
            content = note.read_text(encoding="utf-8")
        except Exception:
            continue
        for tag in extract_tags(content):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])
    out([{"tag": t, "count": c} for t, c in sorted_tags])

def cmd_tag_find(tag: str, vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    results = []
    for note in scan_notes(vault):
        try:
            content = note.read_text(encoding="utf-8")
        except Exception:
            continue
        tags = extract_tags(content)
        if tag in tags or any(t.startswith(tag + "/") for t in tags):
            results.append({"path": str(note.relative_to(vault)), "tags": tags})
    out({"tag": tag, "notes": results, "count": len(results)})

# ── daily ─────────────────────────────────────────────────────────────────────

def cmd_daily(day: str = "", open_after: bool = True, vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    if not day:
        day = date.today().isoformat()

    # Read daily notes config
    dn_config = {}
    dn_cfg_path = vault / ".obsidian" / "daily-notes.json"
    if dn_cfg_path.exists():
        dn_config = json.loads(dn_cfg_path.read_text(encoding="utf-8"))

    fmt = dn_config.get("format", "YYYY-MM-DD")
    # Convert Obsidian moment.js format → Python strftime
    py_fmt = fmt.replace("YYYY", "%Y").replace("MM", "%m").replace("DD", "%d").replace("ddd", "%a").replace("dddd", "%A")
    try:
        d = datetime.strptime(day, "%Y-%m-%d")
        filename = d.strftime(py_fmt)
    except ValueError:
        filename = day

    folder = dn_config.get("folder", "")
    rel = (folder + "/" + filename if folder else filename)

    p = note_path(vault, rel)
    created = False
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        # Use template if configured
        template_path = dn_config.get("template", "")
        content = f"# {filename}\n"
        if template_path:
            tp = note_path(vault, template_path)
            if tp.exists():
                content = tp.read_text(encoding="utf-8")
        p.write_text(content, encoding="utf-8")
        created = True

    result = {
        "date": day,
        "path": str(p.relative_to(vault)),
        "created": created,
    }
    if open_after:
        fp = str(p.relative_to(vault)).replace("\\", "/")
        uri = obsidian_uri(vault, filepath=fp)
        launch_uri(uri)
        result["opened"] = True
    out(result)

# ── links ─────────────────────────────────────────────────────────────────────

def cmd_links_outgoing(rel: str, vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    p = note_path(vault, rel)
    if not p.exists():
        err(f"Note not found: {rel}")
    content = p.read_text(encoding="utf-8")
    links = re.findall(r'\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]', content)
    links = [l.strip() for l in links]
    out({"path": rel, "links": links, "count": len(links)})

def cmd_links_backlinks(rel: str, vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    target = Path(rel).stem  # note name without .md
    results = []
    for note in scan_notes(vault):
        try:
            content = note.read_text(encoding="utf-8")
        except Exception:
            continue
        if f"[[{target}" in content or f"[[{rel}" in content:
            results.append(str(note.relative_to(vault)))
    out({"target": rel, "backlinks": results, "count": len(results)})

# ── config ────────────────────────────────────────────────────────────────────

def cmd_config_get(key: str = "", vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    obsidian_dir = vault / ".obsidian"
    if not obsidian_dir.exists():
        err("No .obsidian directory found")
    configs = {}
    for f in obsidian_dir.glob("*.json"):
        try:
            configs[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    if key:
        parts = key.split(".")
        val = configs
        for part in parts:
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                err(f"Key not found: {key}")
        out({key: val})
    else:
        out(configs)

# ── template ──────────────────────────────────────────────────────────────────

def cmd_template_list(vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    # Read templates folder from config
    tmpl_cfg = vault / ".obsidian" / "templates.json"
    folder = ""
    if tmpl_cfg.exists():
        cfg = json.loads(tmpl_cfg.read_text(encoding="utf-8"))
        folder = cfg.get("folder", "")
    if not folder:
        out({"templates": [], "folder": None})
        return
    tmpl_dir = vault / folder
    if not tmpl_dir.exists():
        out({"templates": [], "folder": folder})
        return
    templates = [str(t.relative_to(vault)) for t in tmpl_dir.rglob("*.md")]
    out({"folder": folder, "templates": templates})

# ── stats ─────────────────────────────────────────────────────────────────────

def cmd_stats(vault_arg: Optional[str] = None):
    vault = resolve_vault(vault_arg)
    notes = scan_notes(vault)
    total_words = 0
    total_chars = 0
    all_tags: dict[str, int] = {}
    for note in notes:
        try:
            content = note.read_text(encoding="utf-8")
        except Exception:
            continue
        body = strip_frontmatter(content)
        total_words += len(body.split())
        total_chars += len(content)
        for tag in extract_tags(content):
            all_tags[tag] = all_tags.get(tag, 0) + 1
    out({
        "vault": vault_name(vault),
        "notes": len(notes),
        "total_words": total_words,
        "total_chars": total_chars,
        "unique_tags": len(all_tags),
        "top_tags": sorted(all_tags.items(), key=lambda x: -x[1])[:10],
    })

# ══════════════════════════════════════════════════════════════════════════════
# CLI (Click-based) — only built if click is available
# ══════════════════════════════════════════════════════════════════════════════

def build_cli():
    @click.group()
    @click.option("--vault", default=None, help="Vault path (overrides saved state)")
    @click.option("--json", "json_mode", is_flag=True, help="Output JSON")
    @click.pass_context
    def cli(ctx, vault, json_mode):
        """cli-anything-obsidian: Automate your Obsidian vault from the command line."""
        global _JSON_MODE
        _JSON_MODE = json_mode
        ctx.ensure_object(dict)
        ctx.obj["vault"] = vault

    # ── vault group ───────────────────────────────────────────────────────────
    @cli.group()
    def vault(): """Vault management."""

    @vault.command("set")
    @click.argument("path")
    def vault_set(path):
        """Save vault path as default."""
        cmd_vault_set(path)

    @vault.command("info")
    @click.pass_context
    def vault_info(ctx):
        """Show vault info."""
        cmd_vault_info(ctx.obj["vault"])

    @vault.command("list")
    @click.option("--folder", default="", help="Subfolder filter")
    @click.pass_context
    def vault_list(ctx, folder):
        """List all notes in vault."""
        cmd_vault_list_notes(ctx.obj["vault"], folder)

    # ── note group ────────────────────────────────────────────────────────────
    @cli.group()
    def note(): """Note operations."""

    @note.command("read")
    @click.argument("path")
    @click.pass_context
    def note_read(ctx, path):
        """Read a note."""
        cmd_note_read(path, ctx.obj["vault"])

    @note.command("create")
    @click.argument("path")
    @click.option("--content", default="", help="Note content")
    @click.option("--title", default="", help="Note title (used if no content)")
    @click.option("--open", "open_after", is_flag=True, help="Open in Obsidian after creating")
    @click.pass_context
    def note_create(ctx, path, content, title, open_after):
        """Create a new note."""
        cmd_note_create(path, content, title, open_after, ctx.obj["vault"])

    @note.command("update")
    @click.argument("path")
    @click.option("--content", default="", help="Replace entire content")
    @click.option("--append", default="", help="Append text")
    @click.option("--prepend", default="", help="Prepend text")
    @click.pass_context
    def note_update(ctx, path, content, append, prepend):
        """Update a note."""
        cmd_note_update(path, content, append, prepend, ctx.obj["vault"])

    @note.command("delete")
    @click.argument("path")
    @click.pass_context
    def note_delete(ctx, path):
        """Delete a note."""
        cmd_note_delete(path, ctx.obj["vault"])

    @note.command("open")
    @click.argument("path")
    @click.pass_context
    def note_open(ctx, path):
        """Open a note in Obsidian."""
        cmd_note_open(path, ctx.obj["vault"])

    # ── search ────────────────────────────────────────────────────────────────
    @cli.command("search")
    @click.argument("query")
    @click.option("--folder", default="", help="Limit to folder")
    @click.option("--case-sensitive", is_flag=True)
    @click.option("--limit", default=50, help="Max results")
    @click.pass_context
    def search(ctx, query, folder, case_sensitive, limit):
        """Full-text search across notes."""
        cmd_search(query, folder, case_sensitive, limit, ctx.obj["vault"])

    # ── tags ──────────────────────────────────────────────────────────────────
    @cli.group()
    def tag(): """Tag operations."""

    @tag.command("list")
    @click.pass_context
    def tag_list(ctx):
        """List all tags with counts."""
        cmd_tag_list(ctx.obj["vault"])

    @tag.command("find")
    @click.argument("tag_name")
    @click.pass_context
    def tag_find(ctx, tag_name):
        """Find notes with a tag."""
        cmd_tag_find(tag_name, ctx.obj["vault"])

    # ── daily ─────────────────────────────────────────────────────────────────
    @cli.command("daily")
    @click.option("--date", "day", default="", help="Date YYYY-MM-DD (default: today)")
    @click.option("--no-open", is_flag=True, help="Don't open in Obsidian")
    @click.pass_context
    def daily(ctx, day, no_open):
        """Create/open a daily note."""
        cmd_daily(day, not no_open, ctx.obj["vault"])

    # ── links ─────────────────────────────────────────────────────────────────
    @cli.group()
    def links(): """Link graph operations."""

    @links.command("outgoing")
    @click.argument("path")
    @click.pass_context
    def links_outgoing(ctx, path):
        """List outgoing [[wikilinks]] from a note."""
        cmd_links_outgoing(path, ctx.obj["vault"])

    @links.command("backlinks")
    @click.argument("path")
    @click.pass_context
    def links_backlinks(ctx, path):
        """Find notes that link to this note."""
        cmd_links_backlinks(path, ctx.obj["vault"])

    # ── config ────────────────────────────────────────────────────────────────
    @cli.group()
    def config(): """Obsidian config access."""

    @config.command("get")
    @click.argument("key", default="")
    @click.pass_context
    def config_get(ctx, key):
        """Get config value (e.g., daily-notes.folder)."""
        cmd_config_get(key, ctx.obj["vault"])

    # ── template ──────────────────────────────────────────────────────────────
    @cli.group()
    def template(): """Template management."""

    @template.command("list")
    @click.pass_context
    def template_list(ctx):
        """List available templates."""
        cmd_template_list(ctx.obj["vault"])

    # ── stats ─────────────────────────────────────────────────────────────────
    @cli.command("stats")
    @click.pass_context
    def stats(ctx):
        """Show vault statistics."""
        cmd_stats(ctx.obj["vault"])

    return cli


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not HAS_CLICK:
        print("Install click for full CLI: pip install click", file=sys.stderr)
        print("Running in direct-call mode. Import and call cmd_* functions.")
        sys.exit(1)
    cli = build_cli()
    cli()

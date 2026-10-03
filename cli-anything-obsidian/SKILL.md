---
name: cli-anything-obsidian
description: "CLI harness for automating Obsidian vaults. Use when asked to: create/read/update/delete notes, search vault content, list tags, manage daily notes, find backlinks/outgoing links, manage tasks, inspect properties, manage plugins/themes/snippets, query bases, or any Obsidian vault automation task. Triggers on: 'create a note', 'search vault', 'list tags', 'open daily note', 'find backlinks', 'read note', 'update note', 'vault stats', 'list tasks', 'set property', or any Obsidian operation."
---

# cli-anything-obsidian

Primary interface: `obsidian` CLI (requires Obsidian running).
Fallback: Python scripts for filesystem ops when Obsidian is not running.

## Setup

```bash
obsidian version          # verify install
obsidian vault=luckey vault
```

**Vault name:** `luckey` — resolve its location on the current host (`obsidian vault=luckey vault`); in this workspace it is `<repo-root>/luckey`. Read `luckey/AGENTS.md` and `00_meta/rules/` before writing.

## Usage Pattern

```bash
obsidian vault=luckey <command> [options]
```

Notes:
- `file=<name>` resolves by name (like wikilinks); `path=<path>` is exact (`folder/note.md`)
- Quote values with spaces: `name="My Note"`
- Use `\n` for newline, `\t` for tab in content values

## Most Common Commands

```bash
# Read / Create / Append
obsidian vault=luckey read file=<name>
obsidian vault=luckey create name=<name> [content=<text>] [template=<name>]
obsidian vault=luckey append path=<path> content=<text>

# Daily note
obsidian vault=luckey daily:read
obsidian vault=luckey daily:append content=<text>

# Search
obsidian vault=luckey search query=<text> [limit=<n>]

# Tasks
obsidian vault=luckey tasks [file=<name>] [todo]
obsidian vault=luckey task file=<name> line=<n> [toggle]

# Tags / Links
obsidian vault=luckey tags [counts]
obsidian vault=luckey backlinks file=<name>
```

> 完整命令参考（所有命令 + 参数）→ [`references/commands.md`](references/commands.md)

## Note Path Conventions (This Vault)

| Folder | Content |
|--------|---------|
| `02_notes/<primary_domain>/` | Reusable notes; route by `00_meta/rules/routing-rules.md` |
| `04_sources/books/` | Book sources and reading notes |
| `02_notes/daily/` | Daily notes (YYYY-MM-DD.md); `.obsidian/daily-notes.json` owns this path |

Do not recreate legacy folders. New folder names use snake_case, note filenames use kebab-case, and default YAML contains only a stable `id` (see vault rules).

## Python API Fallback

Use when Obsidian is **not running**.

```python
import sys
sys.path.insert(0, ".claude/skills/cli-anything-obsidian/scripts")
from obsidian_cli import *

from pathlib import Path
VAULT = str(Path("luckey").resolve())  # Run from the confirmed repo root.
cmd_note_read("02_notes/knowledge_management/my-note", VAULT)
# Choose an unused stable id according to the vault rules before creating.
cmd_note_create("02_notes/knowledge_management/new-note", content="---\nid: n-example-new-note\n---\n# Title\n\nContent", vault_arg=VAULT)
cmd_search("daily standup", vault_arg=VAULT)
```

## CLI-Hub Ecosystem (Package Manager)

`cli-hub` is the package manager for browsing and installing CLI-Anything tools. It provides a registry of agent-native CLIs for various software.

### Python 3.11 Compatibility Fix

The `pip install cli-hub` package ships with a Python 3.11 incompatibility — `f-string` expressions cannot contain backslash escapes on 3.11+. The error surfaces as:

```
SyntaxError: f-string expression part cannot include a backslash
```

**Location:** `C:\Python311\Lib\site-packages\cli_hub\preview.py` (line ~723)

**Fix:** Extract escaped strings into variables before the return statement:

```python
# BEFORE (broken — backslash in f-string expression):
f'<div class="trajectory-list">{items_html or "<div class=\"artifact-file\">No step timeline entries yet.</div>"}</div>'

# AFTER (fixed — variable extracted before f-string):
_no_entries_html = '<div class="artifact-file">No step timeline entries yet.</div>'
f'<div class="trajectory-list">{items_html or _no_entries_html}</div>'
```

> Apply this fix immediately after `pip install cli-hub` on Python 3.11+.

### Key Commands

```bash
cli-hub list              # browse available CLIs
cli-hub search <name>     # search by name/description/category
cli-hub info <name>       # show details
cli-hub install <name>    # install a CLI
cli-hub launch <name>     # launch an installed CLI
```

### Installed Unreal Engine Tools

| Tool | Package | Run Command | Purpose |
|------|---------|-------------|---------|
| `unrealinsights` | `cli-anything-unrealinsights` | `cli-anything-unrealinsights` | Windows-first Unreal trace capture, background session control |
| `smithue-cli` | `smithue-cli` | `smithue-cli` / `npx smithue-cli` | Control Unreal Engine editor via Smith |
| `ueatelier` | `cli-anything-ueatelier` | `cli-anything-ueatelier` | Unreal Editor 5.6/5.7 MCP self-extension workbench |

## Line Endings (This Vault)

<memory category="troubleshooting">
- Obsidian saves notes with **LF on all platforms**; merely opening a note can trigger a save (plugin/frontmatter touch) and silently rewrite a CRLF file to LF.
- Repo `.gitattributes` pins `* text=auto eol=lf` (commit 1a59a985): `text=auto` alone checks out "native" EOL (CRLF on Windows) → Mac/Windows/Obsidian EOL flapping. Both halves are required; don't drop `eol=lf`.
- Phantom modification pattern: `git status` shows `M` but `git diff` is empty → EOL/stat-cache mismatch, content identical to blob after normalization. `git add <file>` re-hashes and clears it.
- Programmatic writes (Python fallback, scripts) must emit LF, not platform-native CRLF.
</memory>

## Reference

For vault structure, URI protocol, frontmatter format, plugin data locations:
→ `references/obsidian-interaction.md`

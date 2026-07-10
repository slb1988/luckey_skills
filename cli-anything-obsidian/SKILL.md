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

**This user's vault:** `D:\Github\ObsidianVault\luckey` — **Vault name:** `luckey`

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
| `002 Cards/` | Permanent notes / cards |
| `003 Books/` | Book notes |
| `301 Daily Notes/` | Daily notes (YYYY-MM-DD.md) |

## Python API Fallback

Use when Obsidian is **not running**.

```python
import sys
sys.path.insert(0, ".claude/skills/cli-anything-obsidian/scripts")
from obsidian_cli import *

VAULT = "D:/Github/ObsidianVault/luckey"
cmd_note_read("002 Cards/My Note", VAULT)
cmd_note_create("002 Cards/New Note", content="# Title\n\nContent", vault_arg=VAULT)
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

## Reference

For vault structure, URI protocol, frontmatter format, plugin data locations:
→ `references/obsidian-interaction.md`

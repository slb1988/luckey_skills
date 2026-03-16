---
name: cli-anything-obsidian
description: CLI harness for automating Obsidian vaults. Use when asked to: create/read/update/delete notes, search vault content, list tags, manage daily notes, find backlinks/outgoing links, manage tasks, inspect properties, manage plugins/themes/snippets, query bases, or any Obsidian vault automation task. Triggers on: "create a note", "search vault", "list tags", "open daily note", "find backlinks", "read note", "update note", "vault stats", "list tasks", "set property", or any Obsidian operation.
---

# cli-anything-obsidian

Primary interface: `obsidian` CLI (requires Obsidian running).
Fallback: Python scripts for filesystem ops when Obsidian is not running.

## Setup

```bash
# obsidian CLI is pre-installed. Verify:
obsidian version

# Vault name shortcut (use instead of full path):
# This user's vault name: luckey
obsidian vault=luckey vault
```

**This user's vault:** `D:\Github\ObsidianVault\luckey`
**Vault name:** `luckey`

## Usage Pattern

```bash
obsidian <command> [options]
obsidian vault=luckey <command> [options]   # target specific vault
```

Notes:
- `file=<name>` resolves by name (like wikilinks); `path=<path>` is exact (`folder/note.md`)
- Most commands default to the active file when `file`/`path` is omitted
- Quote values with spaces: `name="My Note"`
- Use `\n` for newline, `\t` for tab in content values

---

## Command Reference

### File Operations

```bash
# Read
obsidian vault=luckey read file=<name>
obsidian vault=luckey read path=<folder/note.md>

# Create
obsidian vault=luckey create name=<name> [path=<path>] [content=<text>] [template=<name>] [overwrite] [open] [newtab]

# Append / Prepend
obsidian vault=luckey append path=<path> content=<text> [inline]
obsidian vault=luckey prepend path=<path> content=<text> [inline]

# Open in Obsidian
obsidian vault=luckey open file=<name> [newtab]

# File info
obsidian vault=luckey file file=<name>
obsidian vault=luckey file path=<path>

# List files
obsidian vault=luckey files [folder=<path>] [ext=<extension>] [total]

# Move / Rename / Delete
obsidian vault=luckey move file=<name> to=<destination-path>
obsidian vault=luckey rename file=<name> name=<new-name>
obsidian vault=luckey delete file=<name> [permanent]

# Word count
obsidian vault=luckey wordcount file=<name> [words] [characters]

# Outline (headings)
obsidian vault=luckey outline file=<name> [format=tree|md|json] [total]
```

### Daily Notes

```bash
obsidian vault=luckey daily [paneType=tab|split|window]       # open/create today's daily note
obsidian vault=luckey daily:read                              # read daily note contents
obsidian vault=luckey daily:path                              # get daily note file path
obsidian vault=luckey daily:append content=<text> [inline] [open]
obsidian vault=luckey daily:prepend content=<text> [inline] [open]
```

### Search

```bash
obsidian vault=luckey search query=<text> [path=<folder>] [limit=<n>] [total] [case] [format=text|json]
obsidian vault=luckey search:context query=<text> [path=<folder>] [limit=<n>] [case] [format=text|json]
obsidian vault=luckey search:open query=<text>                # open search view in Obsidian
```

### Tags

```bash
obsidian vault=luckey tags [file=<name>] [total] [counts] [sort=count] [format=json|tsv|csv] [active]
obsidian vault=luckey tag name=<tag> [total] [verbose]        # tag info + file list
```

### Links

```bash
obsidian vault=luckey links file=<name> [total]               # outgoing [[wikilinks]]
obsidian vault=luckey backlinks file=<name> [counts] [total] [format=json|tsv|csv]
obsidian vault=luckey unresolved [total] [counts] [verbose] [format=json|tsv|csv]
obsidian vault=luckey orphans [total] [all]                   # files with no incoming links
obsidian vault=luckey deadends [total] [all]                  # files with no outgoing links
```

### Properties (Frontmatter)

```bash
# List all properties in vault
obsidian vault=luckey properties [file=<name>] [name=<prop>] [total] [counts] [sort=count] [format=yaml|json|tsv] [active]

# Read / Set / Remove a property
obsidian vault=luckey property:read name=<name> file=<name>
obsidian vault=luckey property:set name=<name> value=<value> [type=text|list|number|checkbox|date|datetime] file=<name>
obsidian vault=luckey property:remove name=<name> file=<name>
```

### Aliases

```bash
obsidian vault=luckey aliases [file=<name>] [total] [verbose] [active]
```

### Tasks

```bash
# List tasks
obsidian vault=luckey tasks [file=<name>] [total] [done] [todo] [status="<char>"] [verbose] [format=json|tsv|csv] [active] [daily]

# Show / update a task
obsidian vault=luckey task ref=<path:line> [toggle] [done] [todo] [status="<char>"]
obsidian vault=luckey task file=<name> line=<n> [toggle] [done]
obsidian vault=luckey task daily line=<n> toggle
```

### Bookmarks

```bash
obsidian vault=luckey bookmarks [total] [verbose] [format=json|tsv|csv]
obsidian vault=luckey bookmark file=<path> [subpath=<heading>] [title=<title>]
obsidian vault=luckey bookmark folder=<path> [title=<title>]
obsidian vault=luckey bookmark search=<query> [title=<title>]
obsidian vault=luckey bookmark url=<url> [title=<title>]
```

### Vault Info

```bash
obsidian vault=luckey vault [info=name|path|files|folders|size]
obsidian vaults [total] [verbose]                             # list all known vaults
obsidian vault=luckey files [folder=<path>] [ext=<ext>] [total]
obsidian vault=luckey folders [folder=<path>] [total]
obsidian vault=luckey folder path=<path> [info=files|folders|size]
obsidian vault=luckey recents [total]
obsidian vault=luckey random [folder=<path>] [newtab]
obsidian vault=luckey random:read [folder=<path>]
obsidian version
```

### History & Sync (Version Control)

```bash
obsidian vault=luckey history file=<name>                     # list file history versions
obsidian vault=luckey history:list                            # files with history
obsidian vault=luckey history:open file=<name>                # open file recovery
obsidian vault=luckey history:read file=<name> [version=<n>]
obsidian vault=luckey history:restore file=<name> version=<n>
obsidian vault=luckey diff file=<name> [from=<n>] [to=<n>] [filter=local|sync]
```

### Bases (Obsidian Bases plugin)

```bash
obsidian vault=luckey bases                                   # list all base files
obsidian vault=luckey base:views file=<name>                  # list views in a base
obsidian vault=luckey base:query file=<name> [view=<name>] [format=json|csv|tsv|md|paths]
obsidian vault=luckey base:create file=<name> [view=<name>] [name=<name>] [content=<text>] [open] [newtab]
```

### Templates

```bash
obsidian vault=luckey templates [total]
obsidian vault=luckey template:read name=<template> [resolve] [title=<title>]
obsidian vault=luckey template:insert name=<template>         # insert into active file
```

### Commands & Hotkeys

```bash
obsidian vault=luckey commands [filter=<prefix>]              # list command IDs
obsidian vault=luckey command id=<command-id>                 # execute a command
obsidian vault=luckey hotkeys [total] [verbose] [format=json|tsv|csv] [all]
obsidian vault=luckey hotkey id=<command-id> [verbose]
```

### Plugins

```bash
obsidian vault=luckey plugins [filter=core|community] [versions] [format=json|tsv|csv]
obsidian vault=luckey plugins:enabled [filter=core|community] [versions] [format=json|tsv|csv]
obsidian vault=luckey plugin id=<plugin-id>
obsidian vault=luckey plugin:enable id=<id>
obsidian vault=luckey plugin:disable id=<id>
obsidian vault=luckey plugin:install id=<id> [enable]
obsidian vault=luckey plugin:uninstall id=<id>
obsidian vault=luckey plugin:reload id=<id>
obsidian vault=luckey plugins:restrict [on] [off]
```

### Themes

```bash
obsidian vault=luckey themes [versions]
obsidian vault=luckey theme [name=<name>]
obsidian vault=luckey theme:set name=<name>
obsidian vault=luckey theme:install name=<name> [enable]
obsidian vault=luckey theme:uninstall name=<name>
```

### CSS Snippets

```bash
obsidian vault=luckey snippets
obsidian vault=luckey snippets:enabled
obsidian vault=luckey snippet:enable name=<name>
obsidian vault=luckey snippet:disable name=<name>
```

### Workspace & Tabs

```bash
obsidian vault=luckey workspace [ids]
obsidian vault=luckey tabs [ids]
obsidian vault=luckey tab:open [group=<id>] [file=<path>] [view=<type>]
```

### App Control

```bash
obsidian vault=luckey reload                                  # reload vault
obsidian restart                                              # restart Obsidian
```

### Developer Commands

```bash
obsidian vault=luckey eval code=<javascript>                  # execute JS, return result
obsidian vault=luckey devtools                                # toggle Electron dev tools
obsidian vault=luckey dev:console [clear] [limit=<n>] [level=log|warn|error|info|debug]
obsidian vault=luckey dev:errors [clear]
obsidian vault=luckey dev:dom selector=<css> [total] [text] [inner] [all] [attr=<name>] [css=<prop>]
obsidian vault=luckey dev:css selector=<css> [prop=<name>]
obsidian vault=luckey dev:cdp method=<CDP.method> [params=<json>]
obsidian vault=luckey dev:debug [on] [off]
obsidian vault=luckey dev:screenshot [path=<filename>]
obsidian vault=luckey dev:mobile [on] [off]
```

---

## Note Path Conventions (This Vault)

| Folder | Content |
|--------|---------|
| `002 Cards/` | Permanent notes / cards |
| `003 Books/` | Book notes |
| `301 Daily Notes/` | Daily notes (YYYY-MM-DD.md) |

Paths are relative to vault root. `.md` extension is optional.

---

## Python API Fallback

Use when Obsidian is **not running** (direct filesystem operations).

```python
import sys
sys.path.insert(0, ".claude/skills/cli-anything-obsidian/scripts")
from obsidian_cli import *

VAULT = "D:/Github/ObsidianVault/luckey"

cmd_note_read("002 Cards/My Note", VAULT)
cmd_note_create("002 Cards/New Note", content="# Title\n\nContent", vault_arg=VAULT)
cmd_search("daily standup", vault_arg=VAULT)
cmd_tag_list(VAULT)
cmd_tag_find("project", VAULT)
cmd_stats(VAULT)
```

---

## Reference

For vault structure, URI protocol, frontmatter format, plugin data locations:
→ `references/obsidian-interaction.md`

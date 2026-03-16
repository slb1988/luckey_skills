# Obsidian Interaction Reference

## Vault Structure

An Obsidian vault is a plain directory containing:
```
vault/
├── .obsidian/              # Config (JSON files)
│   ├── app.json            # App settings
│   ├── appearance.json     # Theme/font settings
│   ├── community-plugins.json
│   ├── core-plugins.json
│   ├── daily-notes.json    # Daily notes config: folder, format, template
│   ├── templates.json      # Templates folder
│   ├── hotkeys.json
│   ├── workspace.json      # Last open tabs/panes
│   └── plugins/            # Plugin data & code
│       └── <plugin-id>/
│           ├── main.js
│           ├── manifest.json
│           └── data.json   # Plugin-specific settings
├── Notes/                  # User content (.md files)
└── *.md                    # Root-level notes
```

## Note Format

Standard Obsidian note format:
```markdown
---
title: My Note
tags: [tag1, tag2/subtag]
created: 2024-01-01
aliases: [Alt Name]
---

# Heading

Content with [[WikiLinks]] and #inline-tags.

> [!NOTE] Callout blocks
> Obsidian-flavored markdown

- [ ] Task items (obsidian-tasks-plugin)
```

## Frontmatter

- YAML between `---` delimiters at top of file
- Tags: `tags: [a, b]` or `tags:\n  - a\n  - b`
- Aliases: `aliases: [name1, name2]`
- Any custom key:value pairs are valid

## Wikilink Syntax

| Syntax | Meaning |
|--------|---------|
| `[[Note Name]]` | Link to note |
| `[[Note Name\|Display Text]]` | Link with custom text |
| `[[Note Name#Heading]]` | Link to heading |
| `![[Note Name]]` | Embed note |
| `![[image.png]]` | Embed image |

## Obsidian URI Protocol

Standard URI scheme: `obsidian://action?params`

| Action | Params | Effect |
|--------|--------|--------|
| `open` | `vault=NAME&file=PATH` | Open note |
| `new` | `vault=NAME&name=TITLE&content=BODY` | Create note |
| `search` | `vault=NAME&query=TERM` | Search |
| `hook-get-address` | `vault=NAME&file=PATH` | Hook integration |

## Advanced URI Plugin (obsidian-advanced-uri)

**Much more powerful** - use this when the plugin is installed (check `community-plugins.json`).

Base: `obsidian://advanced-uri?vault=VAULT_NAME&...`

### File Operations
```
filepath=relative/path.md          # Target file (URL-encoded)
openmode=tab|window|split          # How to open
```

### Write Modes
```
mode=new        # Create new file
mode=append     # Append to end
mode=prepend    # Prepend to start
mode=overwrite  # Replace entire content
data=CONTENT    # URL-encoded content
```

### Command Execution
```
commandid=COMMAND_ID               # Run Obsidian command
commandname=COMMAND_NAME           # By name (URL-encoded)
```

### Heading Navigation
```
heading=HEADING_TEXT               # Navigate to heading
```

### Template Application (Templater)
```
commandid=templater-obsidian:replace-templates-in-active-file
```

## Launching URIs on Windows

```python
import subprocess
subprocess.Popen(["cmd", "/c", "start", "", uri], shell=False)
```

Or using `os.startfile()` for simpler cases.

## Daily Notes Config (`daily-notes.json`)

```json
{
  "folder": "301 Daily Notes",
  "format": "YYYY-MM-DD",
  "template": "Templates/Daily"
}
```

Date format uses moment.js tokens:
- `YYYY` → 4-digit year
- `MM` → 2-digit month
- `DD` → 2-digit day
- `ddd` → Short weekday (Mon, Tue...)
- `dddd` → Full weekday

Python equivalent: `%Y-%m-%d`, `%A`, etc.

## Plugin Data Locations

| Plugin | Config/Data File |
|--------|-----------------|
| Dataview | `.obsidian/plugins/dataview/data.json` |
| Templater | `.obsidian/plugins/templater-obsidian/data.json` → `templates_folder` |
| Tasks | `.obsidian/plugins/obsidian-tasks-plugin/data.json` |
| Calendar | `.obsidian/plugins/calendar/data.json` |
| Kanban | Stored in .md files with special syntax |

## Dataview Query Language (DQL)

Dataview plugin allows querying notes like a database. Read via:
1. Direct file content analysis (parse METADATA fields)
2. External tools cannot directly execute DQL — must use Obsidian UI

Common patterns to replicate in Python:
```python
# Find notes with tag
notes = [n for n in all_notes if 'mytag' in extract_tags(n.read_text())]

# Find notes modified today
today = date.today()
notes = [n for n in all_notes if datetime.fromtimestamp(n.stat().st_mtime).date() == today]

# List tasks
import re
tasks = re.findall(r'- \[(.)\] (.+)', content)
```

## Common Config Files

### `app.json` — General settings
```json
{"defaultViewMode": "source", "foldIndent": true, ...}
```

### `templates.json` — Template folder
```json
{"folder": "Templates"}
```

### `workspace.json` — Active workspace
Contains last open files, split pane config.

## Performance Notes

- `vault.rglob("*.md")` scans all files — cache results for repeated ops
- Avoid reading all files for simple operations — use path-based filters first
- For large vaults (1000+ notes), search with early termination (limit param)

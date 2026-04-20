---
name: merge-engine-skills
title: Merge Engine SKILL.md Files
description: Copies SKILL.md files (and their sibling references/ directories) from d:\MainDev\Engine\ into the current project's Engine\ directory, preserving the same relative path structure. Use this skill when the user wants to sync, pull, or copy Engine SKILL.md documentation from the MainDev source into the local UnrealEngine-Angelscript repo. Triggers on phrases like "copy engine skills", "sync engine SKILL.md", "pull SKILL from MainDev", "merge engine docs", or "遍历 Engine SKILL.md".
tags: [Documentation, Engine-Modification, SKILL.md, Sync, Engine]
---

# Merge Engine SKILL.md Files

> Layer: Tier 3 (Workflow Skill)

## Purpose

This skill automates syncing SKILL.md documentation (plus accompanying `references/` directories) from the MainDev engine source at `d:\MainDev\Engine\` into the local project mirror at `.\Engine\`. It is **additive and non-destructive** — existing files already in `.\Engine\` are not deleted.

## When to Use

- User says: "遍历 Engine SKILL.md 复制到本项目" or similar
- User wants to refresh local Engine docs from the shared MainDev source
- After the MainDev engine team has added or updated SKILL.md files

---

## Workflow

### Step 1 — Discover source files

Find all SKILL.md files under `d:/MainDev/Engine/`:

```bash
find "d:/MainDev/Engine" -name "SKILL.md"
```

For each SKILL.md found, note:
- Its path relative to `d:/MainDev/Engine/` (the subpath)
- Whether a `references/` directory exists as a sibling

### Step 2 — Copy SKILL.md + references/

For each discovered SKILL.md, reproduce the same relative subpath under `D:/UnrealEngine-Angelscript/Engine/`:

```bash
SRC="d:/MainDev/Engine"
DST="D:/UnrealEngine-Angelscript/Engine"

# For each SKILL.md at $SRC/<subpath>/SKILL.md:
mkdir -p "$DST/<subpath>"
cp "$SRC/<subpath>/SKILL.md" "$DST/<subpath>/SKILL.md"

# If references/ exists alongside it:
cp -r "$SRC/<subpath>/references" "$DST/<subpath>/"
```

Run all copies in a single bash block for efficiency. Do **not** copy `SKILL.md.bak` or other backup variants — only canonical `SKILL.md` files.

### Step 3 — Verify

After copying, verify counts match expectations:

```bash
# Count SKILL.md files copied
find "D:/UnrealEngine-Angelscript/Engine" -name "SKILL.md" | wc -l

# Count references/ directories
find "D:/UnrealEngine-Angelscript/Engine" -type d -name "references" | wc -l
```

Report a summary to the user: how many SKILL.md files were found/copied, and how many `references/` directories.

### Step 4 — Rebuild SKILL index

After copying, rebuild the index so the new files are discoverable:

```bash
cmd.exe /c skill_index_gen.bat 2>&1
```

Only run this if any files were actually copied (i.e., don't run it on a no-op sync).

---

## Rules

- **Non-destructive**: never delete or overwrite files already in `.\Engine\` that have no counterpart in `d:\MainDev\Engine\`
- **No `.bak` files**: skip `SKILL.md.bak` and any non-canonical variants
- **Additive `references/`**: use `cp -r` which merges into the target directory rather than replacing it; existing reference files not present in the source are preserved
- **Relative paths only**: always report paths relative to the project root in output, never absolute paths

---

## Example Output

```
Copied 8 SKILL.md files from d:/MainDev/Engine:
  Engine/SKILL.md
  Engine/Extras/RoboMerge/v3/SKILL.md  (+references/ with 8 files)
  Engine/Plugins/Performance/AutomatedPerfTesting/SKILL.md  (+references/ with 3 files)
  Engine/Plugins/PCG/SKILL.md  (+references/ with 1 file)
  Engine/Source/Developer/SessionFrontend/SKILL.md
  Engine/Source/Programs/AutomationTool/Gauntlet/SKILL.md  (+references/ with 10 files)
  Engine/Source/Programs/UnrealGameSync/SKILL.md
  Engine/Source/Runtime/Slate/SKILL.md  (+references/ with 3 files)

5 references/ directories copied.
Rebuilding SKILL index...
```

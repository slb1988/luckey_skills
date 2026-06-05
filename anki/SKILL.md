---
name: anki
description: Operate local Anki through AnkiConnect for deck discovery, note-type inspection, flashcard creation, bulk import, search, tagging, and note updates. Use when Codex needs to add study cards, create or inspect decks/models, batch-import exercises, verify imported notes, or diagnose local Anki connectivity on this machine.
---

# anki

Use local `Anki.app` plus `AnkiConnect` on `http://127.0.0.1:8765`.
Prefer the bundled script `scripts/anki_connect.py` over handwritten `curl` so payloads stay consistent and retry behavior is available.

## Project Integration

This project copy is the canonical Anki skill for `/Users/sun/Documents/ObsidianVault`.
When running from the repository root, call the bundled helper through `.claude/skills/anki/scripts/anki_connect.py`.

When merging updates from the personal Anki skill at `/Users/sun/.codex/skills/anki`, keep project-only references such as `references/local_media_packaging.md`, and only copy over non-empty reusable assets, scripts, or reference files after comparing them.

## Quick Start

1. Ensure Anki is running:

```bash
open -a /Applications/Anki.app
python3 .claude/skills/anki/scripts/anki_connect.py version --retries 15
```

2. Inspect available decks and note types before writing:

```bash
python3 .claude/skills/anki/scripts/anki_connect.py deckNames
python3 .claude/skills/anki/scripts/anki_connect.py modelNames
python3 .claude/skills/anki/scripts/anki_connect.py modelFieldNames --params '{"modelName":"Basic"}'
```

3. Create or import notes.

4. Verify by querying the deck or note ids that were written.

## Workflow

1. Confirm local API availability with `version`.
2. Discover target `deckName`, `modelName`, and field names. Do not assume the model fields.
3. Choose the smallest write operation that fits:
   `addNote` for one note, `addNotes` for bulk import, `updateNoteFields` for edits, `addTags` or `removeTags` for categorization.
4. Set duplicates policy explicitly when importing curriculum content. Prefer `allowDuplicate: false` unless the user asks to keep duplicates.
5. Verify with `findNotes`, then optionally inspect details with `notesInfo`.

## Common Operations

### Inspect environment

List decks:

```bash
python3 .claude/skills/anki/scripts/anki_connect.py deckNames
```

List note types:

```bash
python3 .claude/skills/anki/scripts/anki_connect.py modelNames
```

List model fields:

```bash
python3 .claude/skills/anki/scripts/anki_connect.py modelFieldNames --params '{"modelName":"Basic"}'
```

### Create a deck

```bash
python3 .claude/skills/anki/scripts/anki_connect.py createDeck --params '{"deck":"小初高::数学::一二年级练习"}'
```

### Add one `Basic` note

```bash
python3 .claude/skills/anki/scripts/anki_connect.py addNote --params '{
  "note": {
    "deckName": "小初高::数学::一二年级练习",
    "modelName": "Basic",
    "fields": {
      "Front": "7 + 5 = ?",
      "Back": "12"
    },
    "options": {
      "allowDuplicate": false,
      "duplicateScope": "deck"
    },
    "tags": ["math", "grade1"]
  }
}'
```

### Bulk import notes

For bulk imports, write the full payload to a temporary JSON file first. This keeps quoting correct and makes imports reviewable.

Example payload file:

```json
{
  "action": "addNotes",
  "version": 6,
  "params": {
    "notes": [
      {
        "deckName": "小初高::数学::一二年级练习",
        "modelName": "Basic",
        "fields": {
          "Front": "[一年级] 9 + 6 = ?",
          "Back": "15"
        },
        "options": {
          "allowDuplicate": false,
          "duplicateScope": "deck"
        },
        "tags": ["math", "grade1", "addition"]
      }
    ]
  }
}
```

Import it:

```bash
python3 .claude/skills/anki/scripts/anki_connect.py --payload-file /tmp/anki_add_notes.json
```

### Find and verify notes

Find notes in a deck:

```bash
python3 .claude/skills/anki/scripts/anki_connect.py findNotes --params '{"query":"deck:\"小初高::数学::一二年级练习\""}'
```

Inspect note details:

```bash
python3 .claude/skills/anki/scripts/anki_connect.py notesInfo --params '{"notes":[1776566792691]}'
```

### Update fields or tags

Update an existing note:

```bash
python3 .claude/skills/anki/scripts/anki_connect.py updateNoteFields --params '{
  "note": {
    "id": 1776566792691,
    "fields": {
      "Back": "12\n提示：先凑十。"
    }
  }
}'
```

Add tags:

```bash
python3 .claude/skills/anki/scripts/anki_connect.py addTags --params '{
  "notes": [1776566792691],
  "tags": "math grade1 reviewed"
}'
```

## Guardrails

- Query `deckNames`, `modelNames`, and `modelFieldNames` before the first write in a session.
- Prefer `Basic` only when its fields are confirmed to be `Front` and `Back`.
- Keep tags flat and machine-friendly, for example `math`, `grade1`, `grade2`, `wordproblem`.
- For bulk imports, persist payloads under `/tmp` and call `--payload-file` instead of inlining large JSON.
- Verify every write with `findNotes` or note ids returned from the API.
- If the API is unreachable, start Anki first and retry. On this machine, `AnkiConnect` is typically exposed by add-on `2055492159`.

## References

- Read [references/api_reference.md](references/api_reference.md) for common action payloads and response shapes.
- Read [references/local_media_packaging.md](references/local_media_packaging.md) when converting remote `http/https` media to local Anki media files or exporting a portable `.apkg` package with media backups.
- Use [scripts/anki_connect.py](scripts/anki_connect.py) for all API calls unless a raw `curl` request is specifically required.

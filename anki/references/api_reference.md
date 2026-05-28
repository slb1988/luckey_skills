# AnkiConnect Reference

Use this file when the task needs exact payload shapes or when composing a batch import file.

## Connection

- Default local endpoint: `http://127.0.0.1:8765`
- Default API version used in this vault: `6`
- Standard request envelope:

```json
{
  "action": "deckNames",
  "version": 6,
  "params": {}
}
```

- Standard response envelope:

```json
{
  "result": [],
  "error": null
}
```

Treat non-null `error` as failure even when HTTP status is `200`.

## Common Read Actions

### `version`

```json
{"action":"version","version":6}
```

### `deckNames`

```json
{"action":"deckNames","version":6}
```

### `modelNames`

```json
{"action":"modelNames","version":6}
```

### `modelFieldNames`

```json
{
  "action": "modelFieldNames",
  "version": 6,
  "params": {
    "modelName": "Basic"
  }
}
```

### `findNotes`

```json
{
  "action": "findNotes",
  "version": 6,
  "params": {
    "query": "deck:\"小初高::数学::一二年级练习\""
  }
}
```

### `notesInfo`

```json
{
  "action": "notesInfo",
  "version": 6,
  "params": {
    "notes": [1776566792691]
  }
}
```

## Common Write Actions

### `createDeck`

```json
{
  "action": "createDeck",
  "version": 6,
  "params": {
    "deck": "小初高::数学::一二年级练习"
  }
}
```

### `addNote`

```json
{
  "action": "addNote",
  "version": 6,
  "params": {
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
  }
}
```

### `addNotes`

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
          "Front": "[二年级] 6 × 4 = ?",
          "Back": "24"
        },
        "options": {
          "allowDuplicate": false,
          "duplicateScope": "deck"
        },
        "tags": ["math", "grade2", "multiplication"]
      }
    ]
  }
}
```

### `updateNoteFields`

```json
{
  "action": "updateNoteFields",
  "version": 6,
  "params": {
    "note": {
      "id": 1776566792691,
      "fields": {
        "Back": "12\n提示：先凑十。"
      }
    }
  }
}
```

### `addTags`

```json
{
  "action": "addTags",
  "version": 6,
  "params": {
    "notes": [1776566792691],
    "tags": "math grade1 reviewed"
  }
}
```

### `removeTags`

```json
{
  "action": "removeTags",
  "version": 6,
  "params": {
    "notes": [1776566792691],
    "tags": "reviewed"
  }
}
```

## Query Patterns

- Entire deck: `deck:"牌组名"`
- Specific tag: `tag:grade1`
- Combined filter: `deck:"小初高::数学::一二年级练习" tag:grade2`

## Practical Notes

- Prefer discovering note ids with `findNotes` before updating fields or tags.
- When the user asks for curriculum imports, prefer `addNotes` plus tags grouped by grade and topic.
- Keep payloads in `/tmp/*.json` for batch imports so the file can be reviewed and replayed.
- If `Basic` is not present or fields differ, query the available model and switch to the actual field names.

# Command Output Formats

Commands with `--json` return structured data for parsing.

## JSON Output Schemas

**Create notebook:**
```
$ notebooklm create "Research" --json
{"id": "abc123de-...", "title": "Research"}
```

**Add source:**
```
$ notebooklm source add "https://example.com" --json
{"source_id": "def456...", "title": "Example", "status": "processing"}
```

**Generate artifact:**
```
$ notebooklm generate audio "Focus on key points" --json
{"task_id": "xyz789...", "status": "pending"}
```

**Chat with references:**
```
$ notebooklm ask "What is X?" --json
{"answer": "X is... [1] [2]", "conversation_id": "...", "turn_number": 1, "is_follow_up": false,
 "references": [{"source_id": "abc123...", "citation_number": 1, "cited_text": "Relevant passage..."},
                {"source_id": "def456...", "citation_number": 2, "cited_text": "Another passage..."}]}
```

**Source fulltext:**
```
$ notebooklm source fulltext <source_id> --json
{"source_id": "...", "title": "...", "char_count": 12345, "content": "Full indexed text..."}
```

**List / status schemas:**
```json
{"notebooks": [{"id": "...", "title": "...", "created_at": "..."}]}
{"sources": [{"id": "...", "title": "...", "status": "ready|processing|error"}]}
{"artifacts": [{"id": "...", "title": "...", "type": "Audio Overview", "status": "in_progress|pending|completed|unknown"}]}
```

**Status values:**
- Sources: `processing` → `ready` (or `error`)
- Artifacts: `pending` or `in_progress` → `completed` (or `unknown`)

## Understanding Citations

`cited_text` is often a snippet or section header, not a full quoted passage. `start_char`/`end_char` reference NotebookLM's internal chunked index, not raw fulltext. Use `SourceFulltext.find_citation_context()` to locate:

```python
fulltext = await client.sources.get_fulltext(notebook_id, ref.source_id)
matches = fulltext.find_citation_context(ref.cited_text)  # Returns list[(context, position)]
if matches:
    context, pos = matches[0]  # check len(matches) > 1 for duplicates
```

## Extract IDs

Parse the `id`, `source_id`, or `task_id` field from JSON output.

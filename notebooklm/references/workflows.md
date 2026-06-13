# NotebookLM Common Workflows

## Research to Podcast (Interactive)
**Time:** 5-10 minutes

1. `notebooklm create "Research: [topic]"` — if fails: check auth with `notebooklm login`
2. `notebooklm source add` for each URL/document — if one fails: log warning, continue with others
3. Wait: `notebooklm source list --json` until all `status=READY` — required before generation
4. `notebooklm generate audio "Focus on [specific angle]"` (confirm when asked) — if rate limited: wait 5 min, retry once
5. Note artifact ID returned
6. Check `notebooklm artifact list` later for status
7. `notebooklm download audio ./podcast.mp3` when complete (confirm when asked)

## Research to Podcast (Automated with Subagent)
**Time:** 5-10 minutes, continues in background

1. Create notebook and add sources
2. Wait for sources: `source wait` or check `source list --json`
3. `notebooklm generate audio "..." --json` → parse `artifact_id`
4. Spawn background agent:
   ```
   Wait for artifact {artifact_id} in notebook {notebook_id} to complete, then download.
   Use: notebooklm artifact wait {artifact_id} -n {notebook_id} --timeout 600
   Then: notebooklm download audio ./podcast.mp3 -a {artifact_id} -n {notebook_id}
   ```
5. Main conversation continues while agent waits

**Error handling in subagent:**
- `artifact wait` exit code 2 (timeout) → report timeout, suggest checking `artifact list`
- download fails → check if artifact status is COMPLETED first

## Document Analysis
**Time:** 1-2 minutes

1. `notebooklm create "Analysis: [project]"`
2. `notebooklm source add ./doc.pdf` (or URLs)
3. `notebooklm ask "Summarize the key points"`
4. Continue chatting as needed

## Bulk Import
**Time:** Varies

```bash
notebooklm create "Collection: [name]"
notebooklm source add "https://url1.com"
notebooklm source add "https://url2.com"
notebooklm source add ./local-file.pdf
notebooklm source list  # verify
```

## Bulk Import with Source Waiting (Subagent Pattern)

1. Add sources with `--json` to capture IDs:
   ```bash
   notebooklm source add "https://url1.com" --json  # → {"source_id": "abc..."}
   ```
2. Spawn background agent:
   ```
   For each source_id: notebooklm source wait {id} -n {notebook_id} --timeout 120
   Report when all ready or if any fail.
   ```
3. Once sources are ready, proceed with chat or generation

**Why wait?** Sources must be indexed before chat or generation (10-60 seconds per source).

## Deep Web Research (Subagent Pattern)
**Time:** 2-5 minutes, runs in background

1. `notebooklm create "Research: [topic]"`
2. `notebooklm source add-research "topic query" --mode deep --no-wait`
3. Spawn background agent:
   ```
   notebooklm research wait -n {notebook_id} --import-all --timeout 300
   Report how many sources were imported.
   ```

**Blocking alternative:** omit `--no-wait` (blocks up to 5 min):
```bash
notebooklm source add-research "topic" --mode deep --import-all
```

**Modes:**
- `--mode fast`: specific topic, quick overview (5-10 sources, seconds)
- `--mode deep`: broad topic, comprehensive (20+ sources, 2-5 min)

**Sources:** `--from web` (default) or `--from drive` (Google Drive)

## Processing Times

| Operation | Typical time | Suggested timeout |
|-----------|--------------|-------------------|
| Source processing | 30s - 10 min | 600s |
| Research (fast) | 30s - 2 min | 180s |
| Research (deep) | 15 - 30+ min | 1800s |
| Notes | instant | n/a |
| Mind-map | instant (sync) | n/a |
| Quiz, flashcards | 5 - 15 min | 900s |
| Report, data-table | 5 - 15 min | 900s |
| Audio generation | 10 - 20 min | 1200s |
| Video generation | 15 - 45 min | 2700s |

Poll every 15-30 seconds when checking status manually.

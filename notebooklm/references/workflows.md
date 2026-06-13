# NotebookLM Common Workflows

## Research to Podcast (Interactive)
**Time:** 5-10 minutes

1. `notebooklm create "Research: [topic]"`
2. `notebooklm source add` for each URL/document
3. Wait: `notebooklm source list --json` until all `status=READY`
4. `notebooklm generate audio "Focus on [specific angle]"` (confirm when asked)
5. Note artifact ID, check `notebooklm artifact list` for status
6. `notebooklm download audio ./podcast.mp3` when complete

## Research to Podcast (Automated with Subagent)

1. Create notebook and add sources
2. Wait for sources: `source wait` or check `source list --json`
3. `notebooklm generate audio "..." --json` → parse `artifact_id`
4. Spawn background agent:
   ```
   Wait for artifact {artifact_id} in notebook {notebook_id}.
   Use: notebooklm artifact wait {artifact_id} -n {notebook_id} --timeout 600
   Then: notebooklm download audio ./podcast.mp3 -a {artifact_id} -n {notebook_id}
   ```

## Document Analysis
1. `notebooklm create "Analysis: [project]"`
2. `notebooklm source add ./doc.pdf` (or URLs)
3. `notebooklm ask "Summarize the key points"`

## Bulk Import with Source Waiting

1. Add sources with `--json` to capture IDs
2. Spawn background agent to wait for all sources:
   ```
   For each source_id: notebooklm source wait {id} -n {notebook_id} --timeout 120
   Report when all ready or if any fail.
   ```

## Deep Web Research (Subagent Pattern)

1. `notebooklm create "Research: [topic]"`
2. `notebooklm source add-research "topic query" --mode deep --no-wait`
3. Spawn background agent:
   ```
   notebooklm research wait -n {notebook_id} --import-all --timeout 300
   ```

**Modes:** `--mode fast` (5-10 sources, seconds) vs `--mode deep` (20+ sources, 2-5 min)

## Processing Times

| Operation | Typical time | Suggested timeout |
|-----------|--------------|-------------------|
| Source processing | 30s - 10 min | 600s |
| Research (fast) | 30s - 2 min | 180s |
| Research (deep) | 15 - 30+ min | 1800s |
| Mind-map | instant | n/a |
| Quiz, flashcards | 5 - 15 min | 900s |
| Report, data-table | 5 - 15 min | 900s |
| Audio generation | 10 - 20 min | 1200s |
| Video generation | 15 - 45 min | 2700s |

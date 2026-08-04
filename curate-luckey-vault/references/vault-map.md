# Luckey vault map

This is an orientation snapshot. Always inspect the live filesystem and read `luckey/00_meta/rules/` before editing.

## Authority order

1. Current user request and repository `AGENTS.md` instructions.
2. `luckey/00_meta/rules/routing-rules.md` for destinations.
3. `luckey/00_meta/rules/metadata-schema.md` for frontmatter.
4. Existing canonical note in the target area.
5. AutomationDocs and archived material as historical context only.

Older PKM documents may still mention `type`, `domain`, `status`, `created`, and `updated`. Those generic fields were retired; the current metadata rule defaults ordinary notes to a stable `id` only.

## Main areas

| Path | Purpose |
|---|---|
| `luckey/00_meta` | Current routing, metadata, and system rules |
| `luckey/01_inbox` | Unresolved captures awaiting classification |
| `luckey/02_notes` | Reusable personal knowledge organized by primary domain |
| `luckey/03_projects` | Project-specific facts, decisions, procedures, and history |
| `luckey/04_sources` | Material whose main value is preserving an external source |
| `luckey/06_life` | Life, household, health, interests, and receipts |
| `luckey/07_assets` | Non-Markdown attachments |
| `luckey/09_generated` | Reproducible program- or AI-generated output |
| `luckey/90_archived` | Retired structures and historical rules; do not route new work here |
| `.claude/AutomationDocs` | Documentation for repository automation and operations |
| `.claude/plans` | Implementation plans required by repository instructions |
| `.claude/skills` | Skills submodule; `.agents/skills` is the preferred compatibility entry |

Legacy directories such as `002 Cards` and `010 GameDev` still exist. Do not route new content into them unless a live rule or an existing canonical note requires it.

## Reusable note domains

Current `02_notes` domains include `ai_agent`, `career`, `daily`, `devops`, `gamedev`, `knowledge_management`, `software`, `toolchain`, `unity`, and `unreal`. Use the unique tests and precedence table in `routing-rules.md`; keyword occurrence alone does not determine the domain.

## Project roots

Current `03_projects` roots include `astro`, `bump`, `cardgame`, `cyancook`, `personal`, `tps`, and `tr`. Inspect the selected project before inventing a new subdirectory. Topic-focused subdirectories are appropriate when several documents share one operational subject.

## Link and identity conventions

- Obsidian links are relative to the `luckey` vault root, for example `[[03_projects/cyancook/ragflow/README|RAGFlow 部署]]`.
- Preserve a note's `id` when renaming or moving it.
- Use `aliases` for meaningful old titles, not every filename variation.
- A dated filename is appropriate for incidents and daily records; stable runbooks use descriptive names.
- Project records preserve evidence. Reusable notes preserve the generalized rule and link back to project context.

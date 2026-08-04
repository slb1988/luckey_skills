---
name: curate-luckey-vault
description: Understand and curate the Luckey Obsidian vault by mapping its live structure, routing inbox or project notes, consolidating and moving Markdown documents, repairing Obsidian links and metadata, and harvesting durable knowledge from the current session into canonical notes. Use when asked to inspect the knowledge-base structure, organize files under luckey, classify captures, clean up project documentation, find the right destination for a note, or preserve reusable session learnings in the appropriate .md file.
---

# Curate Luckey Vault

Treat the live vault and its current rules as the source of truth. Preserve user content and existing worktree changes while turning session results into maintainable knowledge rather than a transcript.

## Ground in the vault

1. Locate the repository root and confirm `luckey/00_meta/rules/` exists.
2. Read these files completely before deciding destinations or metadata:
   - `luckey/00_meta/rules/routing-rules.md`
   - `luckey/00_meta/rules/metadata-schema.md`
   - the repository `AGENTS.md` or equivalent instructions supplied by the user
3. Run the read-only scanner for a quick live map:

```powershell
powershell -ExecutionPolicy Bypass -File .agents/skills/curate-luckey-vault/scripts/scan_vault.ps1
```

Use `.claude/skills/curate-luckey-vault/` if the `.agents/skills` compatibility link is unavailable. Add `-Query "ragflow"` to list relevant files without printing their contents.

4. Read [vault-map.md](references/vault-map.md) when the target area is unfamiliar or routing is ambiguous. Live rules and filesystem state override this snapshot.
5. Inspect candidate documents, headings, inbound links, nearby directory conventions, and `git status` before asking the user questions. Ask only for product intent or a material tradeoff that cannot be discovered.

## Route content

Apply the first matching rule from `routing-rules.md`:

- Keep project-only facts, decisions, incidents, and constraints in `03_projects/<project_slug>`.
- Put reusable personal knowledge and runbooks in the matching `02_notes/<primary_domain>`.
- Keep external-source material in `04_sources`, attachments in `07_assets`, reproducible generated output in `09_generated`, and unresolved captures in `01_inbox`.
- Do not create a new top-level directory to solve uncertainty.
- When project work reveals reusable knowledge, preserve the project history and extract a separate general note that links back.

Prefer an existing canonical note over a new file. Search titles, aliases, filenames, and content before creating anything.

## Organize documents

1. State each document's role before editing. For a deployment or operational topic, prefer:
   - an overview or entry page;
   - one canonical setup/runbook;
   - dated incident records that retain evidence and link to the runbook.
2. Move files without overwriting. Treat untracked files as user-owned content and preserve them exactly until the intended rewrite is clear.
3. Preserve existing `id` values across moves and renames. Give a new ordinary note one unique stable `id`; add aliases only for useful former titles.
4. Replace stale path references and filename prose with explicit vault-relative Obsidian links. Use exact heading anchors.
5. Remove duplicated procedures and incomplete pseudo-commands. Keep one executable canonical version; historical records should link to it.
6. Reconcile conflicting instructions by identifying current behavior, environment-dependent alternatives, and historical state. Do not silently rewrite history.
7. Follow the user's explicit privacy choice, but do not spread credentials into additional notes. Apply `ai_ignore` only when the user or live rules require it.

## Harvest session knowledge

Harvest after an authorized organizing or editing task. For read-only requests, report candidates without writing them.

Keep only knowledge that remains useful after the session:

- verified system behavior, constraints, decisions, reusable procedures, failure signatures, and validation methods;
- the reason a non-obvious document structure or routing choice is correct;
- distinctions between current instructions, fallbacks, and historical evidence.

Skip chat chronology, tool logs, dead ends, temporary process IDs, completion reports, and facts already clear from the canonical note.

Choose the destination using the same routing rules. Update the narrowest existing authoritative note when possible. If a new note is necessary, give it a descriptive non-dated name unless it is genuinely an incident or daily record. Integrate knowledge into a useful section; never append a raw "session summary" dump.

Before writing, formulate each candidate as:

```text
Durable fact or procedure -> evidence from this session -> canonical destination
```

If evidence is incomplete or two sources disagree, label the uncertainty instead of converting it into a rule.

## Automation documentation

Use `.claude/AutomationDocs/` only for automation implementation or operation documentation. Update an existing category first. When a genuinely new category is required, create it and update `.claude/AutomationDocs/README.md`. Do not create temporary completion or explanation documents.

## Verify

After edits:

1. Confirm source files were moved as intended and no unrelated files changed.
2. Search the whole vault for old paths, former filename references, placeholders, and duplicated canonical commands.
3. Validate frontmatter delimiters, unique top-level note IDs, balanced code fences, link targets, and exact heading anchors.
4. Run `git diff --check`, then review `git status` and the scoped diff. Do not discard or commit unrelated user changes.
5. Summarize destinations, harvested knowledge, and checks performed; do not claim live commands or links were validated when only statically checked.

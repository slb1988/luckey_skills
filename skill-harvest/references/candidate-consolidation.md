# Candidate consolidation

This workflow is conditional on the **current workspace** providing the v2 standard-library writer at `.team/scripts/memory_hits.py`. Other clones/workspaces are not assumed to have been migrated. Check local capability before invoking commands; do not copy another member's environment or assume P4.

## What counts

A knowledge candidate is an atomic system property with explicit applicability and provenance. Routing scores only suggest an owner.

Only independently verified reuse/recurrence or explicit user confirmation contributes to the three-session gate. Reads, search matches, injected context, repeated extraction and model paraphrases do not count. Count distinct root sessions, not tool calls; correlate workers when reliable root identity exists. Legacy hits without event evidence are review clues, not fabricated validation.

Different claims/versions/conditions must not be merged because their keywords resemble each other. Private preferences, credentials, local machine inventories and temporary states are not team rules. Never persist credentials into a candidate.

## Inspect and propose

1. Read the workspace's TEAM_MEMORY_RULES and check `memory_hits.py --help` supports `--queue`, `--preview` and `--promote`.
2. In Pi, prefer `/knowledge-review [id] [--team]`; it presents a version-bound confirmation. Otherwise use the CLI below.
3. Inspect one ready claim, its conditions and real sources, then check the current narrow target for overlap/conflicts. Existing coverage becomes a link, not another copy of the same fact.
4. Review only explicitly team-scoped candidate contributions when aggregating across members; never load all personal feedback/reference files.
5. Present the exact proposed additions, evidence and target. A count of three is eligibility, not approval.

```sh
python .team/scripts/memory_hits.py --queue --json
python .team/scripts/memory_hits.py --queue --team --json
python .team/scripts/memory_hits.py --preview <candidate-id> --team --json
```

The default pool comes from the local currentMember setting; an explicit authorized pool can use `--root .team/<member>/candidates`. An unbound candidate needs a narrow repo-relative `--target`; include that same binding in both preview and apply.

## Apply only after explicit approval

```sh
python .team/scripts/memory_hits.py --promote <candidate-id> --team --expected <preview-token> --approve --json
```

- Do not obtain a new token silently after the user approved an old preview. Version drift requires re-review.
- Short durable rules go into the narrowest existing SKILL.md. Long claims go into references plus a short pointer; keep the skill within its 200-line budget. Do not automatically restructure unrelated sections to force acceptance.
- The writer does not run VCS commands. Arrange authorized checkout/permissions for a read-only target; perform scoped Git/submodule/P4 completion under the current repository's rules. No blind add-all, submit or push.
- Read the receipt and verify the written target. An extraction returning, a process exiting zero or a missing error is not proof of persistence.
- Preserve personal evidence/history. Afterwards, replace only duplicated current general rules with the authoritative link during scoped curation; do not delete the whole source file.
- A final promotion receipt is stored under the approving member's pool. Other members' notes are not rewritten. Interrupted writes need their original approved token; foreign changes block recovery.

## Unavailable pipeline or old counters

If the local script is missing, is an older counter-only version, or no real evidence can establish independence, report that limitation. Do not derive multiple sessions by hashing changing source files and do not grant every rule in a large note that file's historical hit count.

Users may explicitly authorize a normal documentation edit after reviewing a legacy rule; that is a separate authorization path, not an excuse to backfill fictional candidate hits.

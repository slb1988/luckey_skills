---
name: skill-harvest
title: Post-Task Knowledge Harvest
description: 任务结束后，从会话中提取结构性/架构性知识（继承链、正确 API、配置配对、扩展点模式）并写入对应 SKILL.md。用户说"整理到SKILL.md"、"document this"、"add to skill"、"总结一下"时触发；也在发现类层次、API 表面、配置耦合等知识后主动触发。只捕获"系统如何工作"，不记录错误日志或调试过程。
tags: [Documentation, SKILL-md, Knowledge-Management, ProjectLungfish, Workflow, Post-Task]
disable-model-invocation: true
---

# Post-Task Knowledge Harvest

## The core filter

Before writing anything, ask: **"Does this describe how the system works?"**

If yes → harvest it.
If it describes what went wrong and how it was fixed → skip it.

The fix that forced a discovery is not the knowledge. The system property that made the fix necessary is. A verified root cause can qualify when expressed as a system property rather than a repair diary.

| Harvest (knowledge) | Skip (experience) |
|---|---|
| `UDynamicEntryBoxBase` inherits `UWidget`, not `UPanelWidget`; children via `GetAllEntries()` | "Got C2027 because the container header only forward-declares the type" |
| CommonUI must appear in both `Build.cs` AND `.uplugin` `"Plugins"` array | "Had to p4 edit before writing" |
| `UCommonActivatableWidgetStack` only activates the top entry; `IsVisible()` returns false for the rest | "First tried Cast<UPanelWidget>, it didn't work" |
| Branch table showing all 4 `ForWidgetAndChildren` cases and their APIs | "Tried a few approaches before landing on this" |

## What belongs (harvest these)

- **Inheritance chains** that aren't obvious from the type name — especially when the natural assumption is wrong
- **The correct API** for a container type and why the obvious one doesn't apply
- **Configuration pairings** that must stay in sync (Build.cs + .uplugin, includes that must come as a pair, etc.)
- **Extension point shapes** — "to add a 5th case to this pattern, follow this structure"
- **Design intent** — why a subsystem works a certain way; what constraint drives a non-obvious API choice

## What to skip

- Error messages and their resolution steps
- Debugging dead ends
- Operational friction (file checkout, permission issues, etc.)
- Generic UE knowledge covered in official docs
- Anything directly readable from the current code without context

**Second test:** "Would a new engineer reading only this section understand how this subsystem works?" If the answer is "they'd understand what to avoid but not how it works" — rewrite from the system's perspective.

## Thematic alignment

Only harvest knowledge directly related to the session's main topic. A session about widget tree traversal → document the widget container type hierarchy. Tangential modules briefly touched → skip unless the discovery is substantial and standalone.

## Finding the right SKILL.md

Check `SKILL.index.json` for the tightest-fit file. Write at the narrowest scope that applies; don't duplicate across tiers.

| Scope | File |
|---|---|
| Specific plugin | `Main/Plugins/<Plugin>/SKILL.md` |
| Cross-plugin UMG/UI pattern | `Main/Plugins/SKILL.md` |
| Engine or Marketplace code | `Engine/SKILL.md` |
| Game-level pattern | `Main/SKILL.md` |

## Format patterns

Choose the format that makes the knowledge most skimmable:

**API/branch table** — for "which API to use for which type":
```markdown
| Branch | Cast target | API | Covers |
|---|---|---|---|
| 3 | `UDynamicEntryBoxBase` | `GetAllEntries()` | UUIExtensionPointWidget, any dynamic entry box |
| 4 | `UCommonActivatableWidgetContainerBase` | `GetWidgetList()` | Stack, Queue |
```

**Inheritance note** — for non-obvious class relationships:
```markdown
`UDynamicEntryBoxBase` → `UWidget` (not `UPanelWidget`). Active entries live in a
private `FUserWidgetPool`; use `GetAllEntries()` — `GetChildAt()` doesn't exist.
```

**Configuration pairing** — for deps that must stay in sync:
```markdown
Build.cs dep: `"CommonUI"`. Also required in `.uplugin` `"Plugins"` array — plugin-level
dependency wiring is separate from module-level. Missing either causes a warning or load failure.
```

**Include chain** — when two headers are needed for one type:
```cpp
#include "Widgets/FooContainer.h"  // UFooContainer (forward-declares UFooItem)
#include "FooItem.h"               // Full definition needed to call UFooItem methods
```

## Workflow

1. **Identify the session topic** and the atomic structural knowledge it revealed; distinguish personal-only facts from team-reusable rules.
2. **Draft in bullet form**, with applicability and real evidence. Search existing authoritative docs before creating another rule.
3. **Automatic harvesting** uses the workspace's candidate policy: verified independent reuse is evidence; reading/searching is not. Where the v2 writer exists, accumulate candidates and queue human review at ≥3 independent sessions, never silently publish shared skills.
4. **Explicitly authorized documentation maintenance** may update the narrow target directly; do not mechanically wait for three sessions when the user requested the edit.
5. **Respect the actual VCS**: Git workspaces do not run p4. In P4, check out before writing and keep the skill with the related code CL. For Git submodules follow the repository's scoped commit/push policy; never sweep unrelated changes.

## Consolidate candidate knowledge

When asked to consolidate/promote a candidate pool, use [candidate-consolidation.md](references/candidate-consolidation.md).

- First verify this workspace provides `.team/scripts/memory_hits.py` with preview/promote support. Do not assume an extension comment proves it is installed; never call a hardcoded Sora/member script or silently fall back to unverified counters.
- Three independent verified sessions make a team rule **eligible for human review**, not permission to edit SKILL.md. Personal preferences/local paths do not become shared rules through popularity.
- Preview the exact claim, scope, evidence and destination diff; wait for explicit confirmation bound to those versions. Changed candidates/targets need another preview.
- Shared aggregation reads only declared team candidates; do not sweep other members' personal memories. Keep personal differences/history and replace only duplicate current rules with authority links.
- An unavailable local pipeline is a visible limitation, not a reason to invent evidence IDs or report promotion success. Normal explicitly authorized documentation edits remain available.

## Worked example: RAGFlow retrieval tuning

A session on debugging retrieval misses surfaced these system properties. Harvest them as knowledge, not as fixes.

### Mixed retrieval scoring

RAGFlow blends dense and keyword similarity per chunk:

```text
similarity = vector_similarity_weight × vector_similarity
           + (1 - vector_similarity_weight) × term_similarity
```

Default `vector_similarity_weight = 0.3` means keyword matching dominates. Project column names (e.g. `食用效果`) are strong term signals; missing them can push data rows below the cutoff.

### Keyword layer is split across dataset and chat

| Layer | Config key | Scope | Effect |
|---|---|---|---|
| Index-time | `parser_config.auto_keywords` | Dataset | Tags each chunk with auto-extracted keywords at parse time |
| Query-time | `prompt_config.keyword` | Chat assistant | Uses an LLM to expand the user question into weighted term matches at retrieval time |

Both are needed. `auto_keywords` alone does not inject question keywords into the term match.

### From retrieval to LLM context: two truncation points

1. `top_k` — how many vector candidates enter the hybrid pool.
2. `top_n` — how many of the re-ranked candidates are actually passed to the LLM as `{knowledge}`.

Enumerative questions ("list all foods with Debuff") are sensitive to `top_n`; a small value drops correct rows even when retrieval returned them. `similarity_threshold` is a hard floor on the final `similarity` score.

### Chunking strategy determines signal-to-noise per chunk

| Method | What it produces | Risk / benefit |
|---|---|---|
| `naive` | 1024-token sliding blocks | Merges unrelated table rows into one chunk; dense relevance is diluted by neighbor content |
| `table` | One chunk per table row, header repeated | Keeps each row self-contained; enumerative lookups become stable |

Excel files with heterogeneous sheets should use `table` chunking for data rows.

### Document config update endpoint shape

Updating `chunk_method` must target the per-document endpoint:

```text
PUT /api/v1/datasets/{dataset_id}/documents/{document_id}
{ "chunk_method": "table" }
```

Batch `PUT /api/v1/datasets/{dataset_id}/documents` with `"ids": [...]` returns `405 Method Not Allowed`.

## SKILL.md Length Budget

Target SKILL.md files to **≤ 200 lines**. When a file approaches this limit:

- Move large reference sections (detailed API tables, extended examples, full command lists) to `references/<topic>.md` in the same directory
- Keep a one-line pointer in SKILL.md: `> 详细参考：[topic](references/topic.md)`
- The SKILL.md body must stay skimmable at a glance — if reading it takes more than 2 minutes, it's too long

If a file already exceeds 200 lines when you harvest, split it as part of the harvest commit rather than making it longer.

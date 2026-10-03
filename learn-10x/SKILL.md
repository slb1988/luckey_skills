---
name: learn-10x
description: "Systematic learning system - transforms any topic into structured, vault-integrated study via 6 prompts (Learning Ladder, 20-Hour Plan, Quiz Me Until I Break, Cheat Sheet, Signal in the Noise, Feynman Loop). Triggers: learn/study/understand [topic], learning plan, quiz me, cheat sheet, resources to learn, continue learning, where did I leave off. Reads existing vault notes to resume where the user left off."
---

# learn-10x: Systematic Learning System

The core insight this skill is built on: random Q&A feels like learning but nothing sticks.
Real learning needs **path → test → compress → repeat**, and it needs to build on what you
already know rather than starting from zero every time.

## How to use this skill

When a user mentions a topic they want to learn, run through the phases below in order.
You don't have to complete every phase in one session — check what the user needs and which
phase fits. Always start with Phase 0 to know where they stand.

---

## Phase 0: Vault Scan — Know What Already Exists

Before generating anything, read `luckey/AGENTS.md` and the current `luckey/00_meta/rules/` (routing, naming, metadata), then search for existing knowledge on the topic. Those rules override legacy paths/frontmatter in the bundled references; do not recreate old folders or introduce status/date/domain fields.

**Search these locations:**
- `luckey/02_notes/<primary_domain>/` — concept and technical cards; read their content and learning evidence
- `luckey/03_projects/personal/learning/` — existing learning plans and study notes (for example `ue-slate-learning-plan.md`)
- `luckey/04_sources/` — related books, courses and external sources

**What to look for:**
1. Any card or file whose title or content matches the topic
2. Learning evidence in the body/session checkboxes; if an old file has `status`, treat it as a historical hint, not a required schema
3. Related topics that already exist (for wikilinks later)
4. Any existing learning plan card (`[topic]-learning-plan.md`)

**Report to the user:**
- What prior knowledge cards exist and their maturity level
- Whether a learning plan already exists (if so, read it and resume from the last session)
- Which ladder levels are likely covered based on prior explanations and quiz evidence

Use `seed` / `growing` / `evergreen` as learning-stage labels in the body, not YAML fields.
If nothing exists → start from Phase 1 at Level 1.
If `seed` evidence exists → consider Level 2–3 on the ladder, checking basics as needed.
If `growing` evidence exists → skip to Phase 3 (Quiz Me) to identify remaining gaps.
If `evergreen` evidence exists → ask whether to review or go deeper; a label alone is not proof of mastery.

---

## Phase 1: Map — Learning Ladder + 20-Hour Plan

### 1a. Learning Ladder

Use the Learning Ladder prompt (see `references/prompts.md` → Prompt 1).

Replace `[topic]` with the user's topic. If vault scan found existing knowledge, ask Claude
to begin the ladder at the appropriate level — state this explicitly in the prompt:
"The learner already understands [existing concepts], so start at Level [N]."

The output gives the user a complete map: where they are, what mastery looks like at each
level, what to practice, and what the next milestone is.

### 1b. 20-Hour Plan (optional, offer after ladder)

Use the 20-Hour Plan prompt (Prompt 2). This finds the core 20% of concepts and structures
them into 10 focused sessions.

If an existing learning plan card already exists, read it first and skip sessions already
marked complete. Only plan the remaining sessions.

**Save output to vault:**
```
luckey/03_projects/personal/learning/[topic-slug]-learning-plan.md
```
Reuse an existing plan at its stable path. For a new plan use a kebab-case topic slug and only a stable, unused `id` in YAML, per the vault metadata rules (the example id is not a reusable value):
```yaml
---
id: n-example-learning-plan
---
```
Keep stage labels, quiz results and next steps in the body, not mandatory metadata.
Include a `## Sessions` section with checkboxes so the user can track progress:
```markdown
## Sessions
- [ ] Session 1: [goal]
- [ ] Session 2: [goal]
...
```

---

## Phase 2: Curate — Signal in the Noise

Use the Signal in the Noise prompt (Prompt 5). Run this once per topic, at the start.

This identifies the 5 highest-leverage resources and builds a 7-day starter path.

**Save as a section inside the learning plan card** (append a `## Resources` section),
or as a standalone `[topic-slug]-resources.md` beside the plan in `luckey/03_projects/personal/learning/` if the user
prefers to keep them separate. External source material itself belongs under `04_sources/` per the routing rules.

---

## Phase 3: Study Loop — Quiz Me Until I Break

Run after each study session to surface real gaps before they silently accumulate.

Use the Quiz Me prompt (Prompt 3): "I just studied [topic specifically: the concepts from
Session N]". Engage interactively — ask one question at a time, wait for answers, grade
each response, re-explain gaps.

**After Quiz Me completes:**
- If the user scored ≥ 7/10 average AND has no major gaps: record the score and a
  `seed` → `growing` learning-stage update in the relevant card's body
- Tell the user explicitly that the quiz shows working understanding and that a
  Feynman Loop pass is the next check; do not create a YAML `status` field.

Mark the completed session checkbox in the learning plan card.

---

## Phase 4: Compress — Cheat Sheet + Feynman Loop

### 4a. One-Page Cheat Sheet

Use the Cheat Sheet prompt (Prompt 4) to generate a scannable 5-minute review.

**Save as a concept card:**
```
luckey/02_notes/[primary_domain]/[topic-slug].md
```
Choose the actual domain from `routing-rules.md` (for example UE concepts → `unreal`, general language concepts → `software`); reuse any existing authoritative card. New notes default to a stable, unused `id` only:
```yaml
---
id: n-example-concept
---
```
Put the initial `seed` stage and learning evidence in the body. Uncurated, regenerable AI drafts go to `09_generated/` until adopted as reusable notes.

At the bottom of the card, include `[[wikilinks]]` to any related cards found in Phase 0:
```markdown
## Related
- [[related-card-1]]
- [[related-card-2]]
```

### 4b. Feynman Loop (for shaky concepts)

When the user flags something as confusing or Quiz Me reveals a persistent gap, use the
Feynman Loop prompt (Prompt 6).

This is interactive — Claude explains, user explains back, Claude corrects gaps, repeat.
The final output of the loop is a clean explanation the user can copy into their card.

**After a clean Feynman Loop pass:** record the explanation evidence and `growing` →
`evergreen` stage in the card's body. Tell the user explicitly; no YAML status update.

---

## Learning-Stage Progression Summary

These labels describe body-level learning evidence, not vault metadata.

| Phase completed | Learning stage |
|---|---|
| Cheat Sheet created (Phase 4a) | `seed` |
| Quiz Me score ≥ 7/10 (Phase 3) | `growing` |
| Clean Feynman Loop (Phase 4b) | `evergreen` |

---

## Chaining Guide

The recommended sequence for a new topic:
```
Phase 0 (scan) → Phase 2 (curate resources) → Phase 1 (map + plan) →
[study sessions] → Phase 3 (quiz) → Phase 4a (cheat sheet) →
Phase 3 again (quiz on full topic) → Phase 4b (Feynman) → evergreen
```

For a topic the user is mid-way through:
- Read the existing learning plan card to find the last completed session
- Jump to Phase 3 (quiz on that session's material)
- Continue from there

For a quick review before an exam/interview/project:
- Jump straight to Phase 4a (cheat sheet) if one doesn't exist
- If it exists, run Phase 3 (quiz) as a fast recall check

---

## Reference Files

- `references/prompts.md` — all 6 verbatim prompts with [topic] placeholders
- `references/vault-conventions.md` — historical learning-stage background only; its old directories and frontmatter schema are superseded by `luckey/AGENTS.md` and `00_meta/rules/`
- `references/workflow.md` — decision tree for which phase to run next

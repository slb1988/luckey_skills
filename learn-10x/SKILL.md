---
name: learn-10x
description: |
  Systematic learning system — transforms any topic into a structured, vault-integrated
  learning engagement using the 6-prompt framework (Learning Ladder, 20-Hour Plan,
  Quiz Me Until I Break, One-Page Cheat Sheet, Signal in the Noise, Feynman Loop).

  ALWAYS use this skill when the user says any of the following:
  - "learn [topic]", "study [topic]", "I want to learn X"
  - "understand [topic] deeply", "teach me [topic] step by step"
  - "make a learning plan for [topic]", "how do I get good at [topic]"
  - "quiz me on [topic]", "test my understanding of [topic]"
  - "cheat sheet for [topic]", "summarize [topic] for review"
  - "what resources should I use to learn [topic]"
  - "continue learning [topic]", "where did I leave off on [topic]"
  - "I've been studying [topic], what next"

  Also use when the user asks about their learning history or progress on any topic —
  this skill can read existing vault notes to assess current knowledge state.

  This is NOT a one-off answer skill. Its purpose is to build durable, compounding
  knowledge that persists in the Obsidian vault across sessions.
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

Before generating anything, search the user's vault for existing knowledge on the topic.

**Search these locations:**
- `luckey/002 Cards/` — concept and technical cards; check the `status` frontmatter field
- `luckey/210 Learning & Reading/` — existing learning plans and study notes

**What to look for:**
1. Any card or file whose title or content matches the topic
2. The `status` of matched files: `seed` | `growing` | `evergreen` | `archived`
3. Related topics that already exist (for wikilinks later)
4. Any existing learning plan card (`[topic]-learning-plan.md`)

**Report to the user:**
- What prior knowledge cards exist and their maturity level
- Whether a learning plan already exists (if so, read it and resume from the last session)
- Which ladder levels are likely already covered based on existing `evergreen` cards

If nothing exists → start from Phase 1 at Level 1.
If `seed` cards exist → start from Level 2–3 on the ladder, skip basics.
If `growing` cards exist → skip to Phase 3 (Quiz Me) to identify remaining gaps.
If `evergreen` cards exist → the topic is already mastered; ask if user wants to go deeper.

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
luckey/210 Learning & Reading/[topic]-learning-plan.md
```
Use this frontmatter:
```yaml
---
type: project
domain: ["[inferred domain]"]
status: seed
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [learning-plan, learn-10x]
source: learn-10x skill
---
```
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
or as a standalone `[topic]-resources.md` in `luckey/210 Learning & Reading/` if the user
prefers to keep them separate.

---

## Phase 3: Study Loop — Quiz Me Until I Break

Run after each study session to surface real gaps before they silently accumulate.

Use the Quiz Me prompt (Prompt 3): "I just studied [topic specifically: the concepts from
Session N]". Engage interactively — ask one question at a time, wait for answers, grade
each response, re-explain gaps.

**After Quiz Me completes:**
- If the user scored ≥ 7/10 average AND has no major gaps: upgrade the relevant concept
  card's status from `seed` → `growing`
- Tell the user explicitly: "Your [topic] card is now `growing` — you've demonstrated
  working understanding. One more Feynman Loop pass will push it to `evergreen`."

Mark the completed session checkbox in the learning plan card.

---

## Phase 4: Compress — Cheat Sheet + Feynman Loop

### 4a. One-Page Cheat Sheet

Use the Cheat Sheet prompt (Prompt 4) to generate a scannable 5-minute review.

**Save as a concept card:**
```
luckey/002 Cards/[topic].md
```
Use this frontmatter:
```yaml
---
type: concept
domain: ["[inferred domain]"]
status: seed
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [cheat-sheet, learn-10x]
---
```

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

**After a clean Feynman Loop pass:** upgrade the concept card's status from `growing` →
`evergreen`. Tell the user explicitly.

---

## Status Progression Summary

| Phase completed | Card status |
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
- `references/vault-conventions.md` — frontmatter schema and status lifecycle
- `references/workflow.md` — decision tree for which phase to run next

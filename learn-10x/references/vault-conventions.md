# Vault Conventions for learn-10x

Source: `luckey/210 Learning & Reading/knowledge-management-sop.md`

---

## Frontmatter Schema

All cards in the vault use this frontmatter structure:

```yaml
---
type: concept | technical | project | literature | fleeting
domain: ["domain1", "domain2"]   # e.g., ["ai", "unreal", "fullstack", "math"]
status: inbox | seed | growing | evergreen | archived
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: []
source: ""    # optional: URL, book, skill name
---
```

### `type` values
- `concept` — abstract idea, theory, mental model
- `technical` — tool, library, language, framework, implementation
- `project` — plan, roadmap, learning schedule, initiative
- `literature` — book notes, article notes, video notes
- `fleeting` — quick capture, not yet processed

### `status` lifecycle
```
inbox → seed → growing → evergreen → archived
```
- `inbox` — just captured, not yet processed
- `seed` — basic structure exists, needs development
- `growing` — actively being developed, frequently referenced
- `evergreen` — mature, stable, well-connected to other notes
- `archived` — no longer actively maintained

---

## Card Locations by Type

| Card type | Location | Naming |
|---|---|---|
| Learning plan | `luckey/210 Learning & Reading/` | `[topic]-learning-plan.md` |
| Concept/cheat sheet | `luckey/002 Cards/` | `[topic].md` |
| Resource list | `luckey/210 Learning & Reading/` | `[topic]-resources.md` (optional) |

---

## Status Transitions in learn-10x

| Trigger | Transition |
|---|---|
| Cheat Sheet generated (Phase 4a) | `inbox` → `seed` |
| Quiz Me score ≥ 7/10 (Phase 3) | `seed` → `growing` |
| Clean Feynman Loop pass (Phase 4b) | `growing` → `evergreen` |

Always update the `updated` date when changing status.

---

## Learning Plan Card Template

```markdown
---
type: project
domain: ["[domain]"]
status: seed
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [learning-plan, learn-10x]
source: learn-10x skill
---

# [Topic] Learning Plan

## Core 20%
<!-- The key concepts from the 20-Hour Plan prompt -->

## Sessions
- [ ] Session 1: [goal]
- [ ] Session 2: [goal]
- [ ] Session 3: [goal]
- [ ] Session 4: [goal]
- [ ] Session 5: [goal]
- [ ] Session 6: [goal]
- [ ] Session 7: [goal]
- [ ] Session 8: [goal]
- [ ] Session 9: [goal]
- [ ] Session 10: [goal]

## Resources
<!-- Output from Signal in the Noise prompt -->

## Capstone Project
<!-- Final project from 20-Hour Plan prompt -->

## Notes
<!-- Running notes across sessions -->
```

---

## Concept Card Template

```markdown
---
type: concept
domain: ["[domain]"]
status: seed
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [cheat-sheet, learn-10x]
---

# [Topic]

<!-- One-Page Cheat Sheet output goes here -->
<!-- Definition, key concepts, examples, common mistakes, checklist, rapid-fire Qs -->

## Related
- [[related-card-1]]
- [[related-card-2]]
```

---

## Domain Values (Common)

When inferring domain from the topic:
- `ai` — machine learning, LLMs, neural networks, prompt engineering
- `unreal` — Unreal Engine, game development, Blueprints, C++ game
- `fullstack` — web, APIs, databases, frontend, backend
- `math` — calculus, linear algebra, statistics, probability
- `cs` — algorithms, data structures, systems, OS
- `design` — UI/UX, graphic design, visual communication
- `writing` — copywriting, technical writing, creative writing
- `finance` — investing, accounting, economics
- `language` — foreign language learning

Use the most specific match. Multiple domains are allowed.

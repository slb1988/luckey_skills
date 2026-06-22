# Workflow Decision Tree

Use this to decide which phase to run based on the user's intent and vault state.

---

## Entry Point: What does the user want?

```
User mentions a topic to learn
        │
        ▼
Phase 0: Vault Scan
(always run first)
        │
        ├─ No vault content found ──────────────────────► Start: Phase 2 → Phase 1 → sessions
        │
        ├─ seed cards found ────────────────────────────► Start: Phase 1 at Level 2-3
        │
        ├─ growing cards found ─────────────────────────► Start: Phase 3 (quiz to find gaps)
        │
        └─ evergreen cards found ───────────────────────► Ask: "go deeper?" or pick sub-topic
```

---

## Intent Routing

| User says | Jump to |
|---|---|
| "I want to learn [topic]" | Phase 0 → Phase 2 → Phase 1 |
| "Make me a learning plan" | Phase 0 → Phase 1b (20-Hour Plan) |
| "Quiz me on [topic]" | Phase 0 → Phase 3 directly |
| "Cheat sheet for [topic]" | Phase 0 → Phase 4a directly |
| "What resources for [topic]" | Phase 2 (Signal in the Noise) |
| "I don't understand [concept]" | Phase 4b (Feynman Loop) |
| "Continue learning [topic]" | Phase 0 → read plan card → resume from last session |
| "Where did I leave off" | Phase 0 → read plan card → report progress |

---

## Session Resume Flow

When the user returns to a topic mid-way:

1. Read `luckey/210 Learning & Reading/[topic]-learning-plan.md`
2. Find the last checked-off session (`- [x] Session N`)
3. The next unchecked session is where to resume
4. Offer: "You're on Session N+1: [goal]. Want to study that now, or quiz first on Session N?"

If no learning plan exists but a concept card does:
- Read the card's status
- `seed` → run Phase 3 (quiz)
- `growing` → run Phase 4b (Feynman Loop)

---

## Full Sequence (new topic, no prior knowledge)

```
1. Phase 0   — Vault scan (confirm nothing exists)
2. Phase 2   — Signal in the Noise (pick 5 resources, 7-day starter path)
3. Phase 1a  — Learning Ladder (full map of the topic)
4. Phase 1b  — 20-Hour Plan (10 sessions, save to learning plan card)
5. [User studies Session 1]
6. Phase 3   — Quiz Me on Session 1 material
7. [Repeat steps 5-6 for sessions 2-10]
8. Phase 4a  — One-Page Cheat Sheet (save as concept card, status: seed)
9. Phase 3   — Quiz Me on full topic
   → score ≥ 7/10: upgrade concept card to growing
10. Phase 4b — Feynman Loop on any remaining gaps
    → clean pass: upgrade concept card to evergreen
```

---

## Accelerated Sequence (user already knows basics)

```
1. Phase 0   — Vault scan (find existing seed/growing cards)
2. Phase 1a  — Learning Ladder starting at appropriate level
3. Phase 3   — Quiz Me to identify exact gaps
4. Phase 4b  — Feynman Loop on gaps only
5. Phase 4a  — Update/create cheat sheet card
```

---

## Quick Review Sequence (before exam/interview/project)

```
1. Phase 0   — Find existing cheat sheet card
   → exists: proceed to step 2
   → missing: run Phase 4a first
2. Phase 3   — Quiz Me (fast 10-question recall check)
3. Phase 4b  — Feynman Loop on any questions you missed
```

---

## When to Save What

| Output | Where to save | When |
|---|---|---|
| Learning Ladder output | Inside learning plan card (## Ladder section) | After Phase 1a |
| 20-Hour Plan | `luckey/210 Learning & Reading/[topic]-learning-plan.md` | After Phase 1b |
| Resource list | As `## Resources` in learning plan card | After Phase 2 |
| Cheat Sheet | `luckey/002 Cards/[topic].md` | After Phase 4a |
| Feynman final explanation | Append to concept card as `## Clean Explanation` | After Phase 4b |

---

## Card Status Update Checklist

After each phase, check whether a status upgrade is due:

- [ ] Cheat Sheet just created → set status: `seed`
- [ ] Quiz Me score ≥ 7/10 average → set status: `growing`, update `updated` date
- [ ] Feynman Loop passed cleanly → set status: `evergreen`, update `updated` date

Always tell the user explicitly when a status changes:
> "Your [topic] card just upgraded from `seed` → `growing`. You've demonstrated working
> understanding. One more Feynman Loop will make this `evergreen`."

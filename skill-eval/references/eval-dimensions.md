# Eval Dimensions Rubric

Use this rubric when grading a skill during static analysis (Tier 1 evaluation).
Read the skill's `SKILL.md` and score each dimension. Sum the scores to get the
overall rating.

---

## Dimension 1: Structural Validity

**Score: Pass / Fail (gates all other scoring)**

Run `quick_validate.py`. A failing skill is rated **Incomplete** regardless of
other scores. Do not proceed to further dimensions if this fails — report the
specific errors and advise the user to fix them first.

Checks performed by `quick_validate.py`:
- YAML frontmatter is present and parseable
- `name` field is non-empty
- `description` field is non-empty
- SKILL.md file itself exists and is readable

---

## Dimension 2: Description Quality

**Score: 0–3 pts**

The `description` field is the primary triggering mechanism. Claude uses it to
decide when to invoke the skill, so it needs to be specific enough to match the
right user intents and broad enough not to miss edge cases.

| Check | Points |
|---|---|
| Non-empty and >50 characters | 1 pt |
| Describes **what** the skill does (functional summary) | 1 pt |
| Contains **when** to trigger — specific phrases, user intents, or contexts | 1 pt |

**Common failure modes:**
- Description is generic boilerplate ("a skill for X")
- No triggering signals — user would have to type `/skill-name` explicitly
- Too narrow — only matches exact phrasing, misses paraphrases

---

## Dimension 3: Body Completeness

**Score: 0–3 pts**

The SKILL.md body is what Claude reads when the skill is active. It needs to
give Claude enough detail to complete the task without having to invent the
workflow on the fly.

| Check | Points |
|---|---|
| Has step-level instructions (numbered steps, clear sequence) | 1 pt |
| Has at least one concrete example or realistic scenario | 1 pt |
| Specifies the expected output format (structure, file names, content shape) | 1 pt |

**Common failure modes:**
- Only has a vague description with no actionable steps
- No examples — Claude has to guess what "success" looks like
- Output format undefined — each invocation produces inconsistent results

---

## Dimension 4: Progressive Disclosure

**Score: 0–2 pts**

Skills load fully into context on every invocation. Bloated SKILL.md files
inflate token cost and reduce effective context for the actual task.

| Check | Points |
|---|---|
| SKILL.md body is under 500 lines | 1 pt |
| Large reference documents are in `references/`, not inlined in SKILL.md | 1 pt |

**Bonus signals (not scored, just noted):**
- Reusable scripts are in `scripts/` (avoids regenerating them per invocation)
- References file has a table of contents if >300 lines
- `assets/` used for output templates

---

## Dimension 5: Eval Coverage (Bonus)

**Score: Bonus — not included in the 0–8 pt total, but always reported**

Evals are the only way to measure whether the skill actually improves Claude's
performance. Without them, quality is purely subjective.

| State | Report |
|---|---|
| `evals/evals.json` exists with ≥2 test cases | ✅ Covered (N test cases) |
| `evals/evals.json` exists with 1 test case | ⚠️ Minimal coverage (1 test case) |
| No `evals/evals.json` | ⚠️ No evals — add via `/skill-creator` |

---

## Scoring Summary

| Dimension | Max Points |
|---|---|
| Structural Validity | Pass/Fail |
| Description Quality | 3 |
| Body Completeness | 3 |
| Progressive Disclosure | 2 |
| **Total** | **8** |

**Ratings:**

| Score | Rating |
|---|---|
| 7–8 pts and structural pass | **Healthy** |
| 4–6 pts, or structural pass with notable gaps | **Needs work** |
| <4 pts, or structural validation fails | **Incomplete** |

When writing the recommendation list, prioritize the lowest-scoring dimensions
first. Be specific: instead of "improve the description", say "add triggering
phrases that match how users would naturally ask for this — e.g. 'convert X to
Y', 'export as Z'."

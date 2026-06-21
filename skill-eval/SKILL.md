---
name: skill-eval
description: >
  Evaluate one skill or all skills in the project for quality, completeness,
  and benchmark performance. Use whenever the user wants to audit a skill,
  check if it's well-structured, run its benchmark test cases, or get a
  project-wide health report. Triggers on: "evaluate this skill",
  "audit all skills", "run skill evals", "skill report", "check skill quality",
  "/skill-eval", or when the user asks which skills are missing test cases,
  underspecified, or of poor quality. Also use proactively after creating or
  modifying a skill if the user hasn't explicitly chosen to skip evaluation.
---

# Skill Eval

Evaluate one skill deeply (Tier 1 static + optional Tier 2 benchmark) or audit
all skills in the project (Tier 1 static only, project-wide summary report).

## Constants

```
SC=/Users/sun/Documents/ObsidianVault/.claude/skills/skill-creator
SKILLS_ROOT=/Users/sun/Documents/ObsidianVault/.claude/skills
SELF_DIR=/Users/sun/Documents/ObsidianVault/.claude/skills/skill-eval
```

---

## Mode Detection

- **Single-skill mode**: user passes a skill name or path (`/skill-eval frp-tunnel-setup`, `/skill-eval ./some/path`)
- **Project-wide mode**: user runs `/skill-eval` with no arguments

---

## Single-Skill Mode

### Step 1: Resolve the skill path

If the argument looks like a name (no slashes), expand to `$SKILLS_ROOT/<name>`.
Confirm the directory exists; if not, tell the user and stop.

### Step 2: Structural validation

```bash
python $SC/scripts/quick_validate.py <skill-path>
```

If validation fails, report the errors clearly and stop — structural issues
must be fixed before a meaningful quality evaluation can happen.

### Step 3: Static analysis (Tier 1)

Read `$SELF_DIR/references/eval-dimensions.md` for the full scoring rubric,
then read the skill's `SKILL.md` and grade each of the five dimensions inline.
Record scores and evidence notes.

### Step 4: Check for benchmark evals

Check whether `<skill-path>/evals/evals.json` exists.

- **No evals**: skip to Step 7 (report). Note that the user can add evals via
  `/skill-creator`.
- **Has evals**: continue to Step 5.

### Step 5: Tier 2 benchmark

Create workspace at `$SKILLS_ROOT/<skill-name>-eval-workspace/`.

Spawn all **with-skill** and **without-skill** runs for every test case in
`evals/evals.json` **in a single turn** (parallel subagents). Don't wait for
with-skill to finish before launching baseline runs.

While runs are in progress: show the user the assertions you're testing so they
can follow along.

Once all runs complete:

1. Grade each run — spawn a grader subagent using `$SC/agents/grader.md`.
   Save `grading.json` to each run directory using fields `text`, `passed`,
   `evidence` (the viewer requires these exact names).

2. Aggregate:
   ```bash
   cd $SC && python -m scripts.aggregate_benchmark \
     $SKILLS_ROOT/<name>-eval-workspace/iteration-1 \
     --skill-name <name>
   ```

3. Analyst pass — read `$SC/agents/analyzer.md` (Analyzing Benchmark Results
   section) and surface non-discriminating assertions, high-variance evals, and
   time/token tradeoffs.

4. Launch viewer:
   ```bash
   nohup python $SC/eval-viewer/generate_review.py \
     $SKILLS_ROOT/<name>-eval-workspace/iteration-1 \
     --skill-name "<name>" \
     --benchmark $SKILLS_ROOT/<name>-eval-workspace/iteration-1/benchmark.json \
     > /dev/null 2>&1 &
   ```
   In headless/no-display environments, use `--static <output.html>` instead.

### Step 6: Tell the user

Tell them the viewer is open, what the two tabs show (Outputs for qualitative
review, Benchmark for stats), and to come back when done.

### Step 7: Save and print the report

Save a per-skill report to `$SKILLS_ROOT/<name>-eval-workspace/skill-eval-report.md`.

See the **Report Format** section below for the exact structure.

Print a console summary: overall rating, top 2–3 findings, benchmark delta if
available (e.g., "+48 pp pass-rate improvement with skill").

---

## Project-Wide Mode

### Step 1: Discover all skills

```bash
python $SELF_DIR/scripts/scan_skills.py --root $SKILLS_ROOT
```

This prints a JSON array of absolute paths to every `SKILL.md` in the project.
Exclude `skill-eval` itself from the results.

### Step 2: Static analysis for every skill (Tier 1 only)

For each discovered skill, run structural validation and grade all five
dimensions inline. Do **not** run benchmarks — spawning 20+ subagent runs is
too heavy for a health audit. The goal is a fast inventory, not deep testing.

### Step 3: Save the summary report

Save to `$SKILLS_ROOT/skill-eval-report-<YYYY-MM-DD>.md`.

See **Report Format → Project-wide summary** below.

### Step 4: Print console summary

Counts by rating and a short list of skills needing immediate attention.

---

## Report Format

### Per-skill block

```markdown
## <skill-name>

**Rating:** Healthy / Needs work / Incomplete
**Path:** /absolute/path/to/skill

### Structural Validity
✅ PASS   or   ❌ FAIL: <reason>

### Description Quality  [N/3]
- ✅ / ❌ Non-empty and >50 chars
- ✅ / ❌ Contains triggering signals
- ✅ / ❌ Describes what the skill does

### Body Completeness  [N/3]
- ✅ / ❌ Has step-level instructions
- ✅ / ❌ Has at least one example or scenario
- ✅ / ❌ Specifies output format

### Progressive Disclosure  [N/2]
- ✅ / ❌ Body is NNN lines (under 500)
- ✅ / ❌ Large docs are in references/, not inlined

### Eval Coverage
✅ Has evals/evals.json with N test cases
⚠️  No evals/evals.json — add via /skill-creator

### Benchmark Results  (Tier 2 — if run)
| Config         | Pass Rate   | Time  | Tokens |
|----------------|-------------|-------|--------|
| with_skill     | 82% ± 5%    | 45 s  | 3 800  |
| without_skill  | 34% ± 8%    | 31 s  | 2 100  |

Delta: +48 pp

### Recommendations
1. ...
2. ...
```

Rating thresholds (see `references/eval-dimensions.md` for dimension details):
- **Healthy**: 7–8 pts and structural validation passes
- **Needs work**: 4–6 pts or a soft issue
- **Incomplete**: <4 pts or structural validation fails

### Project-wide summary (prepend to report)

```markdown
# Skill Health Report — YYYY-MM-DD

Skills scanned: N

| Rating      | Count | Skills                          |
|-------------|-------|---------------------------------|
| Healthy     |   8   | anki, cli-anything-obsidian, …  |
| Needs work  |  12   | daily-report, drawio-skill, …   |
| Incomplete  |   3   | investment-analyzer, …          |

## Skills Needing Immediate Attention
- **investment-analyzer**: Incomplete — description is 1 character
- **teamcity-tool**: Incomplete — description is 1 character

## Eval Coverage
1 of N skills has evals/evals.json.
To add evals, invoke `/skill-creator` on the skill.

---
```

Followed by one per-skill block for every scanned skill.

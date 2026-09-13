# Learning core

## Practice and weakness tracking

Practice sessions contain exercises with deterministic grading. Attempts update weakness state and may enqueue spaced review items. Completion and unlock logic must follow accepted attempts rather than client assertions.

Relevant code:

- `backend/src/kid_learning/services/practice.py`
- `backend/src/kid_learning/services/review.py`
- `backend/src/kid_learning/api.py`
- `frontend/src/views/child/PracticeView.vue`
- `frontend/src/views/child/ReviewView.vue`
- `frontend/src/views/child/MistakesView.vue`

## Dated adaptive mathematics

- `math_models.py` owns `DailyMathPlan`, `DailyLearningResult`, `LearningObservation`, `MathReviewState`, `MathReviewLog`, and `SkillResource`; `math_api.py` exposes learner skills/reviews and guardian planning/observation/resource actions.
- `services/math_catalog.py` validates parameterized arithmetic, elapsed-time and two-step templates. Higher bands add inverse problems. Answers are programmatic, not model-generated.
- `services/math_review.py` pins `fsrs==6.3.1`: no fuzzing or minute-scale learning steps; card identity is learner + skill + template family + band, not the daily exercise ID. Only a first unhinted attempt is independent evidence; same-day fingerprints and successful card retrievals are deduplicated. Corrections cannot inflate mastery. Advancement needs 8 samples, 3 learning dates, 85% independent accuracy and cross-day review evidence; absence is not failure. Accuracy uses the most recent 20 independent samples per band; qualifying dates and displayed learning days use the 28-day independent-evidence window so a larger daily set cannot crowd out cross-day eligibility. Legacy queues map to cards without inventing FSRS logs.
- `services/daily_math.py` snapshots the learner's `daily_math_question_count` exercises per family date (default 20, guardian-editable integer 3–50), with due cards first, recent confirmed observations for diagnosis, then consolidation. New free math sessions use the same count, including odd counts; daily minutes and other assignments do not silently reduce it. The count is captured at generation in the input snapshot; changing the setting does not rewrite existing drafts or sessions. An unstarted dated plan adopts it only through regeneration and guardian publication. Snapshot inputs, cutoff/hash, versions and reasons are retained. Published items and a started session are stable across devices. Free practice is explicitly separate from today's unpublished assignment.
- Guardian dated requests accept `adjustment=auto|harder|advance`, retained in `snapshot.request` before generation and in the audited model input. `harder` reserves two diagnostic slots one band above current evidence (capped at 3); `advance` tries adjacent catalog skills whose prerequisites are already eligible. Other slots retain review/consolidation; excess due cards remain due. This never modifies mastery. Regeneration excludes previous revisions' fingerprints, can supersede an ungenerated queued draft, and refuses any started date; the scheduler reuses an existing adjusted plan.
- `services/math_results.py` persists immutable `DailyLearningResult` revisions in the learning-write transaction, including first answers, corrections, hints, unfinished exercises and session/Attempt references. The result date is the family date the sessions started; a late answer creates a new result revision without rewriting an existing plan input. Before a model request, recent daily results are refreshed and their IDs/revisions/hashes are included in the committed plan snapshot. Restarting the service must not lose this evidence.
- LLM output only chooses catalog skills/approved resources and a rationale. Invalid/unavailable/over-quota output falls back to a rule draft. A two-minute lease and bounded retries protect generation; a committed `AIJob` reserves quota and records the exact input before the external request. No provider call holds a SQLite write transaction. Only a guardian can publish. Changes after generation require a new unstarted revision, not silent replacement.
- Observations preserve original text/source references and may be confirmed, corrected with `supersedes`, or withdrawn. They influence diagnostics but are not Attempts. Approved `SkillResource` links and examples appear on skill cards; candidate links stay guardian-only.
- `PracticeView.vue` resumes server progress and tracks foreground duration/server-recorded hints. A response-lost or offline answer is retained locally under the user/learner/session with the same event ID; it must be accepted by the server before advancing/completing. Continuous offline grading is not implemented.
- The `daily-math` CLI is an external-scheduler entry, not an installed timer. It creates daily drafts and Sunday-evening idempotent review summaries in `MemoryOutbox`; see deployment operations. It does not run Anki Desktop or rewrite the word-review scheduler.

## Reading and word review

`ReaderSource` and `ReaderSection` provide reading content. A learner can add lexemes to the wordbook; `LearnerWordState` and `ReviewLog` record spaced-review state and outcomes.

Keep teacher-supplied text faithful. Generated child-interface Chinese may use the pinyin component, but source reading material must not be silently rewritten or decorated as if it came from the teacher.

## Progression and plans

`ProgressionUnlock` represents earned access and must be backed by learning activity. `LearningPlan` is guardian-visible planning state. Avoid coupling cosmetic rewards to curriculum unlocks unless the product rule explicitly requires it.

## AI assistance

`backend/src/kid_learning/services/ai.py` supports an OpenAI-compatible provider. Without provider configuration, deterministic templates are the supported fallback. AI output is advisory content and must not mutate authoritative learning, task, star, or reward state without a validated application command.

## Memory Hub

`backend/src/kid_learning/services/memory.py` writes through `MemoryOutbox`. Synchronization packages a gzip JSON artifact, creates an immutable session version, then submits it to Memory Hub. Configuration requires the Memory Hub URL, API key, user, and project identifiers.

Use the `sync-memory` CLI for retryable delivery. Keep local learning behavior functional when Memory Hub is unavailable.

## Resource imports and A2A agent

The `a2a-agent/` accepts only bounded resource collection from allowed local roots or public URLs. It returns artifacts through `ResourceImportJob` and does not run arbitrary commands or publish daily content. Treat fetched resource text as untrusted data.

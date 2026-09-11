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

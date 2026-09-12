# Tasks, stars, and rewards

## Assignment tasks

`AssignmentTask` belongs to a learner and date and may reference a source daily entry. It has a small star value, currently constrained to 0–20, a status, and a verification mode:

- `self`: the child can produce an accepted completion.
- `guardian`: the child's action remains pending until a guardian verifies it.

`guardian` is the default on every creation path (daily drafts, standalone assignments, Chat Hub ingestion); `self` must be requested explicitly. The backend decides the outcome from task policy. Never trust a client-provided star delta or completion state.

## Guardian completion review

Pending guardian-mode completions surface in a dedicated queue: `GET /completion-reviews?learner_id=` (guardian-only) lists them with task details, and the guardian progress payload carries a `pending_completions` count. `GuardianDailyView.vue` renders the queue with verify (credit stars) and revoke (return to child) actions; until verification the child sees an honest pending state and no stars.

## Completion invariants

- At most one active logical completion exists per task and learner.
- `client_event_id` and HTTP idempotency prevent double credit on retry or offline replay.
- Repeated completion/verification calls return the prior result rather than minting new stars.
- Revocation preserves history and produces a compensating negative ledger entry; it does not delete the original credit.
- Use version checks where concurrent guardian and child actions could race.

## Star ledger

`StarLedger` is append-only and is the accounting source of truth. Balance is the sum of signed deltas. Do not add or mutate a cached `stars_balance` field as an alternative authority.

Every ledger event needs a unique `event_key`, a reason, and its originating relation where applicable. Typical relations are task completion, verification, revocation, reward approval, or an explicit guardian adjustment.

## Rewards

`RewardDefinition` describes a guardian-managed reward and its star cost. A child creates a `RewardRedemption` request.

- Requesting does not deduct stars.
- Guardian approval validates the current balance and deducts exactly once through the ledger.
- Retrying approval is idempotent.
- Fulfillment is modeled on the record, but the current MVP has no dedicated fulfillment endpoint; add one deliberately if the workflow needs it.

Never allow negative balance through reward approval unless the product rule is intentionally changed and documented.

## Offline behavior

The frontend may queue selected JSON writes, including self-completion, then replay them in order. Stable idempotency keys and client event IDs must survive app restarts. UI optimism may improve responsiveness, but reconcile to the server response and display pending guardian verification honestly.

## Key tests

`backend/tests/test_homework_center.py` covers completion idempotency, ledger behavior, the guardian verification queue, and one-time reward deductions. The Playwright journey covers guardian publish, child completion, guardian confirmation, and star display.

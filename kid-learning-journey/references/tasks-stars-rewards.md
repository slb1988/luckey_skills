# Tasks, stars, and rewards

## Review policy

`LearnerProfile.star_review_required` is a server-persisted boolean, default false for both new and migrated learners. `GET/PATCH /learners/{learner_id}/star-policy` exposes it; only an associated guardian may PATCH, with CSRF. The child's own account may read it. This is not a browser preference and never changes teacher-content publication permissions.

Task `verification_mode` remains `guardian` by default across creation paths. Effective review is `star_review_required AND verification_mode == guardian`; explicit `self` tasks remain self-completing when review is enabled. Task payloads carry `requires_review`; day and reward responses carry `star_policy`.

| Action | Review disabled (default) | Review enabled |
| --- | --- | --- |
| Complete guardian-mode task | Accepted and credited immediately | Pending until guardian verification |
| Complete self-mode task | Accepted and credited immediately | Accepted and credited immediately |
| Redeem reward | Approved and debited immediately | Requested without debit; approval debits later |

Changing policy never bulk-settles records or changes ledger history. A historical pending completion may be explicitly completed again when review is disabled. Historical requested redemptions remain available to guardians for manual processing; they are not silently approved or merged with new requests.

## Assignment completion

`AssignmentTask` belongs to a learner/date, may reference a daily entry, and has a 0–20 star value. New completion/verification requires an active task and a published source entry. Never trust a client-provided star delta, balance or final state.

- One logical `TaskCompletion` exists per task/learner; client event IDs are unique. Cross-task event reuse is rejected.
- Pending acceptance does not increment `version`; automatic acceptance and guardian verification use `completion:{id}:award:{version}` for the same award.
- Only completing a revoked task starts a new version. Revocation preserves history with a compensating negative event, not deletion.
- Child complete, guardian verify and revoke use the same write transaction boundary and read current state under the lock. Duplicate complete returns the existing result; a different-key verify of an already accepted task retains its 409 state rejection, while the original successful key replays its receipt.
- Recognized unique conflicts may be retried after rollback and reread; unrelated integrity errors must not be disguised as success.

## Guardian completion review

`GET /completion-reviews?learner_id=` is guardian-only and lists actual pending completions. Guardian progress carries the real `pending_completions` count. `GuardianDailyView.vue` keeps historical queues visible even with review disabled, but hides empty review controls. Disabling review does not zero counters or hide pending history.

## Star ledger and transactions

`StarLedger` is append-only and the balance authority is the sum of signed deltas, not a separate mutable balance field. Each event has a unique `event_key`, reason and originating relation.

Star mutations use `api.py::_idem_tx` with `services/stars.py`: SQLite `BEGIN IMMEDIATE` precedes policy/balance/state reads, and business changes plus the idempotency receipt commit together. A business rejection rolls back its mutation savepoint before storing the refusal; a receipt failure rolls back the whole transaction. Distinct connections must not spend the same remaining balance twice.

## Rewards

`RewardDefinition` is guardian-managed. Creation of any redemption and first approval require an active reward and sufficient server balance. A disabled reward returns `409 REWARD_INACTIVE`; insufficient funds returns `409 INSUFFICIENT_STARS`. Both reject new debit/creation, and a rejected approval preserves its existing requested record.

Automatic and guardian settlement share the event `redemption:{id}:approve`. A successful replay or repeated approval of an already settled record returns the existing result without another debit, even if the reward was subsequently disabled. `approved` means exchanged, not physical fulfillment. There is no dedicated fulfillment, cancellation or refund endpoint; add compensating operations deliberately if requested.

## Client recovery and offline behavior

`frontend/src/services/redemptions.ts` persists one unresolved exchange intent per actor/learner before POST. Unknown results (including timeout, 5xx and malformed responses) reuse its original target, body and key across reloads. Success or a contract-defined inactive/insufficient refusal closes the intent; a later explicit exchange uses a new key. Fingerprint conflicts are not ordinary refusals to bypass with a new key. The optional `client_actor_id` is compared with the actual authenticated user to reject stale-login replays; it grants no authority.

Redemptions require connectivity and never enter the offline queue. Task completion may queue using existing stable IDs, but queued stars are not spendable until server confirmation. The homework view refreshes state after mutations, reentry/focus, and successful outbox replay. Cached receipts may contain old balance snapshots, so fetch current balance after replay.

## Key tests

- `backend/tests/test_star_policy.py`: defaults, both modes, pending acceptance, replay/fingerprint rules, inactive rewards, independent-connection concurrency and rollback when receipt persistence fails.
- `backend/tests/test_star_policy_migration.py`: fresh/old databases, default false and unchanged historical ledger/completion/redemption/receipt data.
- Frontend `HomeworkStars`, `StarPolicySettings`, `redemptions` specs; E2E `stars.spec.ts` exercises direct completion, committed-but-lost exchange recovery, independent browser balance and the persisted guardian switch at desktop/phone sizes.

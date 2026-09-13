# API, authentication, and authorization

## Contract authority

`kid-learning-journey/contracts/openapi.yaml` is the authoritative transport contract. Update it in the same change as route payloads, responses, statuses, or security requirements. Standard errors use:

```json
{"error":{"code":"stable_code","message":"human-readable message"}}
```

## Browser security

- Browser clients use the session cookie.
- State-changing browser requests require CSRF validation.
- Route decorators enforce login and role; learner endpoints also resolve `GuardianRelation` or the authenticated child's own learner identity.
- Do not accept a learner identifier as proof of access.
- Protected asset streaming applies the same learner authorization.

## Idempotency

Use `Idempotency-Key` for retried writes with business effect. `IdempotencyRecord` scopes keys by actor and endpoint and stores the response status and body. Reject reuse when the request meaning conflicts; return the cached result for a true retry.

Domain-level event keys remain necessary for ledger and completion invariants even when HTTP idempotency exists.

Star mutations use `_idem_tx`, not the legacy `_idem`: SQLite write lock, business mutation and receipt are one transaction. New receipts fingerprint the HTTP method, concrete path and JSON body; legacy receipts with no fingerprint remain replayable. A business rejection rolls back its mutation savepoint before the refusal is cached. Other legacy `_idem` callers retain their existing transaction behavior; do not reuse that helper for new automatic financial effects.

A cached 409 remains a refusal on same-key replay. For redemptions, only success and contract-defined no-effect refusals (`INSUFFICIENT_STARS`, `REWARD_INACTIVE`) close the client intent. Unknown/5xx results retain the key; fingerprint conflicts require reconciliation, not a fresh key. New responses include balance; pre-migration cached redemption receipts may omit it. Read current balance after all replays.

## Public API surface

The daily learning endpoints under `/api/v1` include:

- subjects and teachers;
- daily-entry draft creation, listing, editing, asset upload, and publication;
- learner day and calendar views;
- protected asset content;
- image print requests dispatched to a local command;
- assignments and complete/verify/revoke actions;
- star summary, per-learner `GET/PATCH /learners/{learner_id}/star-policy`, rewards, immediate or reviewed redemptions, and guardian approvals.

Star review defaults off and is guardian-editable only. Day/reward responses expose `star_policy`, and tasks expose server-derived `requires_review`. New Web redemption requests carry an optional `client_actor_id` stale-login guard that must match the authenticated user; it cannot authorize an operation. Content publication remains guardian-only regardless of the star policy.

The original learning routes in `api.py` cover health, sessions and preferences, today, practice, reading, wordbook, review, mistakes, progression, guardian progress/plans, imports, AI coach/audit, memory outbox sync, and device pairing.

Consult OpenAPI and route code for exact payloads rather than duplicating them here.

## Internal API surface

`/internal/v1/content-ingestions` supports a service-only two-phase upload:

1. Create ingestion metadata.
2. `PUT` each declared asset using its client asset ID.
3. Finalize into a `pending_review` daily entry.
4. Query ingestion status.

Internal endpoints use bearer tokens and trusted-actor configuration, not browser sessions. They deliberately provide no publish endpoint.

Other internal routes accept restricted resource-import artifacts and memory digests.

## Boundary rules

- Never expose local paths, raw chat IDs, secrets, or database rows directly.
- Validate dates, enum states, MIME/size/signature, ownership, and state transitions server-side.
- Treat all imported text and files as untrusted data.
- Keep publication a guardian-authorized transition.

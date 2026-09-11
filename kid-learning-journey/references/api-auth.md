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

## Public API surface

The daily learning endpoints under `/api/v1` include:

- subjects and teachers;
- daily-entry draft creation, listing, editing, asset upload, and publication;
- learner day and calendar views;
- protected asset content;
- assignments and complete/verify/revoke actions;
- star summary, rewards, redemption requests, and approvals.

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

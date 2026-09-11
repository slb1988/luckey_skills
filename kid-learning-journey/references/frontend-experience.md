# Frontend experience

## Application structure

The frontend uses Vue 3, TypeScript, Vite, Pinia, and PWA support. The API client is `frontend/src/services/api.ts`; offline mutation replay is `frontend/src/services/offline.ts`; authentication and preferences live in Pinia stores.

The API base defaults to `/api/v1` and may be overridden by `VITE_API_BASE_URL`. Requests include credentials; browser writes attach the CSRF token and business writes may attach an idempotency key.

## Cross-device browser capability boundary

The frontend is used across devices, including LAN HTTP origins. `localhost` and loopback are potentially trustworthy browser contexts, but a LAN HTTP address is not; successful cookie/CSRF authentication does not change this distinction.

| Browser API | Availability relevant to this frontend |
| --- | --- |
| `crypto.randomUUID()` | Requires a secure context and browser support. |
| `crypto.getRandomValues()` | Also available outside secure contexts; provides cryptographic randomness for UUID generation over LAN HTTP. |

Both HTTP idempotency keys and attempt/completion IDs in JSON bodies use the API service's common client-ID generator. This gives all business-write flows the same browser capability baseline while retaining cryptographic UUID entropy. These identifiers correlate and deduplicate writes; they do not authorize them.

Journey tests use loopback, so ordinary E2E success does not establish LAN capability compatibility. Exercise this boundary by disabling only `crypto.randomUUID` before page startup, retaining `getRandomValues` and the real API, and covering both guardian publication and child writes.

## Routes

Public:

- `/login`

Child:

- `/child/today`
- `/child/homework`
- `/child/practice/:kind`
- `/child/reader`
- `/child/review`
- `/child/mistakes`
- `/child/progress`

Guardian:

- `/guardian/dashboard`
- `/guardian/daily`
- `/guardian/content`
- `/guardian/settings`

Route guards and the backend must both enforce roles. Frontend hiding is not authorization.

## Daily content presentation

- `views/guardian/GuardianDailyView.vue`: compose, upload, review, and publish daily material.
- `views/child/HomeworkDayView.vue`: view current or historical daily entries and tasks.
- `components/ContentBlockRenderer.vue`: preserve ordered mixed blocks and use native image, audio, and video presentation.

Resolve media URLs through the API service so absolute and relative deployments work. Keep audio/video controls touch-friendly and allow range-based playback from the backend.

## Child design

For every child-facing visual change, read and follow [../../kid-learning-princess-theme/SKILL.md](../../kid-learning-princess-theme/SKILL.md). That skill is the canonical source for the approved fresh princess-castle palette, assets, spacing, typography, responsive rules, and visual validation.

Additional product rules:

- Child UI should feel encouraging, readable, and low-friction rather than administrative.
- Generated Chinese interface copy may use `PinyinText` where the design calls for it.
- Teacher-authored text remains plain and faithful; do not generate pinyin inside the teacher's material.
- Completion, pending verification, stars, and reward cost must have clear, distinct states.

Guardian and administration screens stay adult-neutral, compact, and information-dense. Do not apply the princess theme globally.

## Responsive and accessibility baseline

Validate child flows at 1440×900 and 390×844; include tablet coverage when layout behavior changes. Preserve keyboard focus, semantic controls, readable contrast, reduced-motion preferences, and labels for non-text controls.

## Offline behavior

Queue only explicitly supported JSON mutations. Replay in order with original idempotency identifiers. Media uploads and publication require connectivity and should surface a recoverable error rather than pretending success.

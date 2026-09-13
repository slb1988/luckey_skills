# Frontend experience

## Application structure

The frontend uses Vue 3, TypeScript, Vite, Pinia, and PWA support. The API client is `frontend/src/services/api.ts`; offline mutation replay is `frontend/src/services/offline.ts`; authentication and preferences live in Pinia stores.

The API base defaults to `/api/v1` and may be overridden by `VITE_API_BASE_URL`. Requests include credentials; browser writes attach the CSRF token and business writes may attach an idempotency key.

## Loading and asset budget

- Route layouts and views use dynamic imports. Authentication completes before initial route resolution; the HTML startup status stays visible until `router.isReady()` and Vue mounting, without rendering protected content early.
- `services/pinyin.ts` shares the optional dictionary import and a bounded character-reading cache. `PinyinText` renders accessible plain text while loading or on failure; disabled annotations do not load/convert the dictionary or create per-character DOM. Explicit `enabled` props still override the preference.
- Theme PNG masters stay in `frontend/public/assets/`. Runtime views and CSS use committed WebP derivatives in `frontend/src/assets/`, bundled with content hashes. After changing a PNG master, run `bash scripts/optimize-theme.sh` from `frontend/` with `cwebp` installed, then rebuild. Preserve dimensions and alpha; no layout redesign is implied by conversion.
- Service Worker registration waits for page load. Its offline precache includes built chunks and WebP, not PNG masters; this background offline preparation is distinct from the foreground route's request budget.
- `e2e/playwright.loading.config.ts` validates an already-built production frontend with mocked APIs and Service Workers blocked: pending-auth paint and role isolation, route/dictionary requests, theme transfer budget and desktop/mobile output. It never connects to the live learning backend.

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

- `views/guardian/GuardianDailyView.vue`: compose, upload, review, and publish daily material; confirm or return child task completions from the guardian review queue.
- `views/child/HomeworkDayView.vue`: view current or historical entries/tasks; default direct completion and redemption update the server balance without guardian approval. Actual pending responses remain visibly pending; historical pending tasks become actionable when their `requires_review` is false.
- `components/StarPolicySettings.vue`, embedded in `GuardianSettingsView.vue`: guardian-only server-persisted star review switch, disabled until loaded and while saving; failures restore the prior display and offer a fresh read. `GuardianDailyView.vue` hides inactive review controls but retains historical pending queues and exchange records.
- `components/ContentBlockRenderer.vue`: preserve ordered mixed blocks, use native image/audio presentation, and delegate video to `components/VideoPlayer.vue`. Image blocks open `components/ImageLightbox.vue`, a fullscreen viewer with pinch zoom around the moving midpoint, single-pointer pan clamped to the image overflow, double-tap zoom toggle (fit ↔ 250% at the tap point), mouse-wheel and keyboard (`+`/`-`/`0`) zoom, and a bottom zoom toolbar; dismissal stays via Escape, backdrop/empty-stage tap, or the close button, with scroll lock, focus restore, gesture-aware click suppression, and `prefers-reduced-motion` respected, so children can inspect worksheets up close. Image blocks offer a print button that posts to `/assets/{asset_id}/print` (idempotent, 10-minute duplicate window, dispatched via the backend's configured `PRINT_COMMAND` or held pending). Decorative character art stays non-interactive.

<memory category="core-rules">
- Image-block overlays (the 🔍 zoom badge) anchor to the image **top-right**, never bottom-anchored: worksheet photos are tall and their lower region is blank white paper visually indistinguishable from the card background, so a bottom-anchored badge sits at the CSS-correct position yet reads as floating/「错位」 mid-card. When a user reports overlay misalignment on a photo, pixel-measure against the CSS first — the position can be exact while the visual anchor is wrong.
- The caption row under an image (filename + 🖨 print) is `display: grid; grid-template-columns: minmax(0, 1fr) auto`: `minmax(0, 1fr)` forces long filenames to ellipsis-truncate while the print button stays right-aligned on the same row. Both flex alternatives fail — `flex-wrap` pushes the button onto its own row; nowrap flex max-content (filename + button) overflows the parent grid's auto track and causes horizontal page overflow.
</memory>

Resolve media URLs through the API service so absolute and relative deployments work. Keep audio/video controls touch-friendly and allow range-based playback from the backend.

### Video and WebView compatibility

`VideoPlayer.vue` uses pinned Plyr 3.8.4 for inline play/pause, seeking, mute, time and automatic control hiding. Controls sit inside the picture with 20px icons, at least 44px hit targets and an unobtrusive dark gradient. Hide with opacity only, not Plyr's default translating toolbar: moving touch targets can become unreachable during scroll/focus. When a touch starts with hidden controls, prevent its cancelable touchend default so a synthesized mouse event cannot seek through the newly revealed slider. Do not cancel touchstart/move (page scrolling must remain usable). A More button exposes rotation inline; expanded mode exposes rotation directly. Menus and keyboard focus keep controls visible. Autoplay and persisted volume/mute are disabled; starting another video pauses other video instances.

Keep one inline `<video>` node with fitted dimensions and `playsinline`/`webkit-playsinline`. Page enlargement fixes the existing container without recreating/moving the video. Plyr's fullscreen manager is disabled: the component exclusively owns standard/WebKit native requests, rejected/missing API fallback, focus/scroll restore, and CSS quarter-turn rotation (picture only, no OS orientation-lock requirement). Keep ancestors free of transforms/containment that capture the fixed viewport. ResizeObserver schedules fitting on the next animation frame to avoid layout writes in its delivery cycle. Escape/browser fullscreen exit restores inline state. Preserve prior body overflow even when Plyr.destroy resets it.

Plyr assets are served locally, never through its default CDN. Its package exports do not expose the SVG sprite; the matching 3.8.4 sprite and MIT license are vendored under `frontend/src/assets/plyr/`, imported as a hashed Vite asset with external sprite loading disabled. Keep filenames in text/ARIA attributes, not custom HTML strings. Media errors offer reload and the same protected URL in a separate tab; UI replacement does not modify or analyze teacher audio.

A visible player cannot fix an unsupported codec. The backend compatibility job must run for imported videos; a Chromium fixture/viewport test is not proof of Via device decoder compatibility.

## Child design

For every child-facing visual change, read and follow [../../kid-learning-princess-theme/SKILL.md](../../kid-learning-princess-theme/SKILL.md). That skill is the canonical source for the approved fresh princess-castle palette, assets, spacing, typography, responsive rules, and visual validation.

Additional product rules:

- Child UI should feel encouraging, readable, and low-friction rather than administrative.
- Generated Chinese interface copy may use `PinyinText` where the design calls for it.
- Teacher-authored text stays faithful in storage. Child homework opts text blocks into `ContentBlockRenderer`'s `pinyin` mode: display-only `PinyinText` annotations follow the global switch while preserving the original wording, line breaks, punctuation and English. Shared guardian previews remain plain by default; image/audio/video materials are unchanged.
- Completion, pending verification, stars, and reward cost must have clear, distinct states.

Guardian and administration screens stay adult-neutral, compact, and information-dense. Do not apply the princess theme globally.

## Responsive and accessibility baseline

Validate child flows at 1440×900 and 390×844; include tablet coverage when layout behavior changes. Preserve keyboard focus, semantic controls, readable contrast, reduced-motion preferences, and labels for non-text controls.

## Offline behavior

Queue only explicitly supported JSON mutations. Replay in order with original idempotency identifiers. Media uploads and publication require connectivity and should surface a recoverable error rather than pretending success.

Redemptions also require connectivity and never use the offline outbox. `services/redemptions.ts` persists an unresolved intent before sending, scoped by actor and learner. A lost response/5xx/reload reuses the original key and offers a dedicated retry even when the current shelf no longer permits a fresh exchange. Only a successful result or an inactive/insufficient no-effect refusal clears the intent; an idempotency conflict does not. Storage failures stop new requests rather than risking an unrecorded debit. The body carries `client_actor_id` as a server-checked stale-login guard.

The homework view serializes wallet writes, shows queued completion as awaiting sync without spendable credit, and refreshes authoritative state on completion, focus/reentry and `kid-learning-outbox-synced`. Old cached receipts can contain a stale or absent balance. The existing global task outbox's cross-account isolation and poison-message handling are separate limitations; the new exchange recovery does not fix or reuse that queue.

<memory category="core-rules">
- The write outbox (`kid-learning-write-outbox-v1`, offline.ts) is stored browser-globally, not keyed per account; `flushOutbox` (`main.ts:24-25`) replays under the currently logged-in identity, so after an account switch the previous account's queued writes execute under the new identity with stale keys (the server's actor-scoped receipts then miss). `flushOutbox` also stops at the first business error (e.g. 409), so one poison message permanently blocks the rest of the queue.
- `HomeworkDayView.vue` `redeem()` regenerates the idempotency key on every click (`makeIdempotencyKey('reward-request')`), so redemption retries have no cross-click dedup today. A fixed key per redemption intent must rotate only after a deterministic response — see the `_idem` caching rules in [api-auth.md](api-auth.md).
</memory>

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

- `views/guardian/GuardianDailyView.vue`: compose, upload, review, and publish daily material; confirm or return child task completions from the guardian review queue.
- `views/child/HomeworkDayView.vue`: view current or historical daily entries and tasks.
- `components/ContentBlockRenderer.vue`: preserve ordered mixed blocks, use native image/audio presentation, and delegate video to `components/VideoPlayer.vue`. Image blocks open `components/ImageLightbox.vue`, a fullscreen viewer with pinch zoom around the moving midpoint, single-pointer pan clamped to the image overflow, double-tap zoom toggle (fit ↔ 250% at the tap point), mouse-wheel and keyboard (`+`/`-`/`0`) zoom, and a bottom zoom toolbar; dismissal stays via Escape, backdrop/empty-stage tap, or the close button, with scroll lock, focus restore, gesture-aware click suppression, and `prefers-reduced-motion` respected, so children can inspect worksheets up close. Image blocks offer a print button that posts to `/assets/{asset_id}/print` (idempotent, 10-minute duplicate window, dispatched via the backend's configured `PRINT_COMMAND` or held pending). Decorative character art stays non-interactive.

<memory category="core-rules">
- Image-block overlays (the 🔍 zoom badge) anchor to the image **top-right**, never bottom-anchored: worksheet photos are tall and their lower region is blank white paper visually indistinguishable from the card background, so a bottom-anchored badge sits at the CSS-correct position yet reads as floating/「错位」 mid-card. When a user reports overlay misalignment on a photo, pixel-measure against the CSS first — the position can be exact while the visual anchor is wrong.
- The caption row under an image (filename + 🖨 print) is `display: grid; grid-template-columns: minmax(0, 1fr) auto`: `minmax(0, 1fr)` forces long filenames to ellipsis-truncate while the print button stays right-aligned on the same row. Both flex alternatives fail — `flex-wrap` pushes the button onto its own row; nowrap flex max-content (filename + button) overflows the parent grid's auto track and causes horizontal page overflow.
</memory>

Resolve media URLs through the API service so absolute and relative deployments work. Keep audio/video controls touch-friendly and allow range-based playback from the backend.

### Video and WebView compatibility

`VideoPlayer.vue` keeps one inline `<video>` node with explicit fitted dimensions and `playsinline`/`webkit-playsinline`. Page enlargement changes the container to fixed positioning without moving or recreating the video, preserving playback. Keep its ancestors free of transforms/containment that would capture the fixed viewport. Rotation is a 90° CSS turn of the picture, not an OS orientation lock; fit dimensions swap for quarter turns, while controls stay upright and reachable. ResizeObserver and viewport resize listeners handle device rotation.

Play/pause, seek, mute, enlarge, rotate and fullscreen are independent touch controls (44px minimum), not browser-native fullscreen controls. Request fullscreen on the whole player synchronously from the click, using the standard or WebKit-prefixed container API. Missing/rejected fullscreen leaves the page-sized viewer usable, including over LAN HTTP; never require secure-context orientation APIs for rotation. Closing/Escape restores scrolling and focus, and unmount pauses playback. Media/decode failures offer reload and the same protected media URL in a separate tab.

A visible player cannot fix an unsupported codec. The backend compatibility job must run for imported videos; a Chromium fixture/viewport test is not proof of Via device decoder compatibility.

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

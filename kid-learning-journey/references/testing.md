# Testing and verification

## Backend

```powershell
cd kid-learning-journey/backend
uv run ruff check src tests
uv run pytest -q
```

The validated baseline has 63 passing backend tests (with ffmpeg/ffprobe available). `test_homework_center.py` covers dated media archiving, task/star idempotency and Chat Hub pending-review ingestion. `test_star_policy.py` adds both review modes, inactive rewards, fingerprint conflicts, receipt-failure rollback and independent-connection concurrency. `test_star_policy_migration.py` checks fresh and populated old databases without silently settling history. `test_print_jobs.py` covers image printing and authorization.

## Frontend

```powershell
cd kid-learning-journey/frontend
pnpm test -- --run
pnpm build
```

Production loading checks (build the frontend first; API responses are isolated mocks, not the live backend):

```powershell
cd kid-learning-journey/e2e
pnpm exec playwright test --config=playwright.loading.config.ts
```

The preview uses port 5175 and refuses an existing listener. `KID_LOADING_DIST` optionally selects an alternate build directory for controlled comparisons. Foreground JS/image budgets exclude Service Worker background precaching. `pinyin.spec.ts` covers deferred/shared imports, disabled/non-Han text, reading reuse and dictionary failure fallback.

The validated baseline has 71 passing frontend unit tests and a successful production build. Star-related coverage is in `HomeworkStars.spec.ts`, `StarPolicySettings.spec.ts` and `redemptions.spec.ts`. Extend tests when changing API URL resolution, offline replay, pinyin behavior, preferences, or content-block media interactions.

## End-to-end and visual

```powershell
cd kid-learning-journey/e2e
pnpm test
pnpm test:visual
```

The validated Playwright journey/video/stars baseline has fourteen passing tests and two deliberate skips across desktop/mobile; `test:visual` adds one passing screenshot flow. The default test script includes `stars.spec.ts`; for a narrow run use `pnpm exec playwright test tests/stars.spec.ts` directly. It uses frontend port 5174 and backend port 5101, with a temporary SQLite database and data root for each run. Both servers refuse to reuse an existing listener. The test frontend receives an explicit `VITE_API_BASE_URL` pointing to 5101 so tests cannot mutate the normal development backend on 5100.

The video E2E suite requires ffmpeg with libx264/AAC and creates a short local test-pattern clip; it does not download external material. It exercises the real Plyr instance and verifies decoded frames, continuous playback through expansion/rotation, rejected Fullscreen API fallback, opacity-only control hiding, touch reveal without accidental seek, 44px hit targets, focus/scroll restoration, no external asset/media requests and desktop/phone/tablet/landscape screenshots. Unit tests cover missing, synchronous-error, Promise-rejected and WebKit Fullscreen APIs, Escape, media errors, and teardown. Backend `test_media_playback.py` converts a real 4:4:4/odd-sized clip and uses ffprobe to assert H.264 Main/yuv420p/AAC, even dimensions, frame rate, faststart and protected Range/conditional responses; it explicitly skips the real codec test if ffmpeg/ffprobe is absent. These tests do not replace Via real-device playback with the affected source file.

The daily publication journey explicitly enables review before testing pending completion and the guardian queue. The star journey exercises default direct credit/debit, a committed response deliberately lost before client receipt, same-key recovery after reload, balance in another browser context, and persisted guardian review toggling. It captures direct/review states at 1440×900 and 390×844. Generated screenshots under `kid-learning-journey/artifacts/` are ignored.

Non-failing baseline warnings include legacy Alembic `get_engine` deprecation and the existing ContentBlockRenderer `<figcaption>` nesting warning. These are not changes to star behavior.

`PinyinText` renders Chinese strings as per-character `<ruby>` fragments; the full string survives only in the container's `aria-label`, so Playwright `hasText`/`getByText` matches against multi-character titles break whenever the pinyin preference is on. Specs that locate Chinese text must disable pinyin up front via `addInitScript` setting localStorage `kid-learning-pinyin-enabled` to `'false'` (see `disablePinyin` in `journey.spec.ts`).

## Contract and deployment validation

- Parse `contracts/openapi.yaml` after contract edits.
- Run `docker compose config` after Compose or environment-shape changes.
- Exercise conditional/range playback after asset-serving or proxy changes.
- Test a migration from the previous schema for nontrivial data changes.

## Chat Hub

Targeted non-image attachment test:

```powershell
node --test --test-name-pattern="transaction: 非图片媒体" .pi/extensions/chat-hub/daemon/test/units.test.ts
```

This targeted test passes. The full Chat Hub unit suite currently has 13 pre-existing Windows-specific failures around `fsync` permissions, `chmod`, and path separators. Do not present those as regressions from learning-system changes without reproducing and isolating them.

## Change-oriented matrix

| Change | Minimum verification |
| --- | --- |
| Model or migration | Ruff, backend tests, migration upgrade |
| Public/internal payload | Backend tests, OpenAPI parse, affected frontend/integration test |
| Media archive or serving | Homework backend tests, range/playback check, manifest inspection |
| Task/star/reward logic | Backend idempotency tests and end-to-end journey |
| Child UI | Frontend unit/build, desktop and mobile visual checks, theme skill checklist |
| Guardian UI | Frontend unit/build and affected end-to-end flow |
| Chat Hub bridge | Targeted daemon tests plus pending-review integration test |
| Compose/runtime config | `docker compose config` and service health check |

Report actual results rather than inheriting the baseline counts in this document.

# Testing and verification

## Backend

```powershell
cd kid-learning-journey/backend
uv run ruff check src tests
uv run pytest -q
```

The current baseline has 19 passing backend tests. `test_homework_center.py` covers dated image/audio/video archiving, task/star idempotency, one-time reward deduction, and Chat Hub pending-review ingestion.

## Frontend

```powershell
cd kid-learning-journey/frontend
pnpm test -- --run
pnpm build
```

The current baseline has four unit tests and a successful production build. Extend tests when changing API URL resolution, offline replay, pinyin behavior, or preferences.

## End-to-end and visual

```powershell
cd kid-learning-journey/e2e
pnpm test
pnpm test:visual
```

The current Playwright baseline has six passing tests and two deliberate skips. It uses port 5174 to avoid the local Memory Hub service on 5173 and creates a temporary SQLite database and data root for each run.

The main daily journey is guardian publish → child view → completion → updated stars. Visual coverage targets 1440×900 and 390×844. Generated screenshots under `kid-learning-journey/artifacts/` are ignored.

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

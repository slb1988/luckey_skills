# Project map

## Purpose

Kid Learning Journey turns scattered teacher messages and media into a dated, reviewable family learning feed. A guardian curates content; a child consumes it, completes assignments, earns stars, and requests rewards.

## Source precedence

When documentation disagrees, use this order:

1. Current migrations and executable code.
2. `contracts/openapi.yaml` for the transport contract.
3. `README.md` for supported workflows and setup.
4. This skill for stable architecture and operational guidance.
5. `.claude/plans/老师资料与家庭作业中心实现方案.md` for original design context.

Update the lower-priority source after changing an authoritative source.

## Repository map

| Path | Responsibility |
| --- | --- |
| `backend/src/kid_learning/` | Flask application, models, routes, security, services, and CLI commands |
| `backend/migrations/` | Alembic schema history; production schema changes belong here |
| `backend/tests/` | API and service behavior tests |
| `frontend/src/` | Vue 3 + TypeScript application, Pinia state, routes, components, and styles |
| `frontend/tests/` | Vitest unit tests |
| `contracts/openapi.yaml` | Authoritative public/internal HTTP transport shapes |
| `a2a-agent/` | Restricted proxy agent that creates reviewable imports |
| `e2e/` | Playwright journeys and visual checks |
| `docker-compose.yml` | Local container topology and persistent data volume |
| `.pi/extensions/kid-learning-publisher.ts` | Pi tool that submits trusted Chat Hub material |
| `.pi/extensions/chat-hub/daemon/` | Chat Hub transaction context and daemon bridge |

## Technology baseline

- Backend: Flask, Flask-SQLAlchemy, Flask-Migrate/Alembic, SQLite, Gunicorn.
- Frontend: Vue 3, TypeScript, Vite, Pinia, PWA; Capacitor Android scaffolding exists.
- Media: local filesystem originals and derived files; protected HTTP streaming.
- Integration: explicit internal ingestion API for Chat Hub and service actors.

Keep the system intentionally small. Do not add a second database, queue, object store, or microservice unless a measured constraint requires it.

## Product roles

- Child: reads published content, practices, self-marks allowed tasks, views stars, and requests rewards.
- Guardian: manages learners, imports/reviews/publishes content, verifies work, manages rewards, and sees progress.
- Service actor: submits bounded ingestion/import jobs but cannot publish child-visible content.

Guardian relationships, not a client-provided role string, determine learner access.

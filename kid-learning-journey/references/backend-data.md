# Backend and data model

## Application lifecycle

- Factory: `backend/src/kid_learning/__init__.py`, `create_app`.
- Route modules: `api.py` for the original learning APIs and `homework_api.py` for daily content, tasks, stars, rewards, and ingestion.
- Configuration: `config.py`; security helpers: `security.py`; extensions: `extensions.py`.
- Production schema setup uses `flask db upgrade`. Do not depend on `create_all` in production.
- CLI commands include `init-db`, `seed-db`, `process-media`, and `sync-memory`.

## SQLite policy

SQLite is the only structured datastore for the expected family-scale workload. When no database URI is provided, the database is `DATA_ROOT/kid_learning.db`. File-backed connections enable foreign keys, a 5000 ms busy timeout, and WAL mode.

Keep transactions short. Let constraints enforce uniqueness and use application-level idempotency for externally retried writes. Store file metadata and keys in SQLite, never file bodies.

## Model ownership

### Identity and access

- `User`, `LearnerProfile`, `GuardianRelation`: `LearnerProfile.star_review_required` defaults false in both ORM and database, scoped to the learner and editable only by related guardians.
- `TrustedDevice`, `DevicePairingCode`

### Learning core

- `SkillNode`, `ExerciseItem`, `LearningSession`, `Attempt`
- `WeaknessState`, `ReviewQueueItem`
- `Lexeme`, `LearnerWordState`, `ReviewLog`
- `ReaderSource`, `ReaderSection`
- `ProgressionUnlock`, `LearningPlan`

### Jobs and integration

- `ResourceImportJob`, `AIJob`, `MemoryOutbox`
- `IdempotencyRecord`: unique by actor, endpoint, and key, with cached status/response and nullable `request_fingerprint` for legacy compatibility. Star routes commit receipts and business effects atomically.
- `PrintJob`: child-initiated image print requests, dispatched to a local command or held pending as a spool.

### Daily learning center

- `Subject`, `Teacher`, `DailyEntry`
- `MediaAsset`, `EntryBlock`, `MediaJob`
- `ContentIngestion`, `ContentIngestionAsset`
- `AssignmentTask`, `TaskCompletion`
- `RewardDefinition`, `RewardRedemption`, `StarLedger`

Read [daily-content-media.md](daily-content-media.md) and [tasks-stars-rewards.md](tasks-stars-rewards.md) for invariants around these records.

## Migration discipline

For a model change:

1. Define the domain invariant and compatibility behavior.
2. Change the SQLAlchemy model.
3. Add and inspect an Alembic migration.
4. Update seed data only when local demonstrations require it.
5. Update `contracts/openapi.yaml` if the API shape changes.
6. Test both a fresh database and an upgraded database when risk warrants it.

Never rewrite an already-deployed migration to represent a new schema change.

For additive SQLite columns on referenced tables, use native `op.add_column` with a literal server default rather than a batch rebuild: dropping/recreating `learner_profiles` can fail with foreign keys enabled once history exists. The star-policy migration adds default-false review and a nullable receipt fingerprint without rewriting history. Its native DROP COLUMN downgrade requires SQLite 3.35+. Old-schema test fixtures must insert through reflected tables or version-appropriate SQL, not current ORM seed code that assumes newer columns.

## Time and identifiers

- Daily content uses the family's calendar date; default timezone is `Asia/Singapore`.
- Audit timestamps are UTC.
- Public entities use opaque identifiers. Do not expose disk paths, chat identifiers, or other sensitive source details.

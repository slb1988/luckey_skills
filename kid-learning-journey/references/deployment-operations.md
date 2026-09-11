# Deployment and operations

## Local development

Backend:

```powershell
cd kid-learning-journey/backend
uv sync --all-extras
uv run flask --app kid_learning:create_app db upgrade
uv run flask --app kid_learning:create_app seed-db
uv run flask --app kid_learning:create_app run --port 5100
```

Frontend:

```powershell
cd kid-learning-journey/frontend
pnpm install
pnpm dev
```

Vite normally serves on 5173 and proxies backend requests to 5100. Copy `.env.example` to `.env` and keep real secrets out of source control.

## Docker

From `kid-learning-journey/`:

```powershell
docker compose up -d --build
```

The frontend is exposed on 8088 and the backend on 5100. The backend runs Gunicorn with one worker and four threads, appropriate for the current SQLite workload. A named volume persists `/data/kid-learning`, including `kid_learning.db`, staging files, and published media.

## Configuration boundaries

- `DATA_ROOT` controls database and media placement.
- When no explicit database URI is set, SQLite lives below `DATA_ROOT`.
- The application creates staging and media directories.
- Production startup must run migrations before serving requests.
- Demo seed credentials are for local use only (`parent`/`parent123`, `star`/`1234`).

## Backup and restore

A valid backup includes:

1. A consistent SQLite snapshot made with the SQLite backup mechanism so WAL state is included.
2. The entire media tree and manifests from the same logical point in time.
3. Deployment configuration with secrets stored separately.

On restore, run integrity checks, verify manifest hashes against representative entries, and test protected playback. Copying only the `.db` file while writes are active is not a reliable backup.

## Production security

- Replace application secrets and all demo credentials.
- Do not seed demo accounts in production.
- Put TLS and a reverse proxy in front of the service.
- Restrict backend port 5100 to the trusted LAN, VPN, or proxy.
- Use device pairing if unattended child devices need it.
- Never expose the SQLite file, staging directory, or media root as public static storage.
- Limit upload size and disk consumption, and monitor failed media jobs and free space.

## Operational commands

- `flask db upgrade`: apply schema migrations.
- `flask process-media`: process pending derived-media jobs.
- `flask sync-memory`: retry Memory Hub outbox delivery.
- `docker compose config`: validate Compose expansion before deployment.

Keep original assets when derivative generation fails; surface the job state for diagnosis without blocking otherwise playable content.

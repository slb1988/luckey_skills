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
- `PRINT_COMMAND` optionally names a local command that receives the absolute image path of each print job; without it print jobs stay pending as a spool for a later bridge (for example a NAS-side printer).
- Print dispatch runs the command synchronously (60s timeout): the command string is shell-split, the image path is appended as the final argument, exit 0 marks the job `dispatched`, and non-zero exit, timeout, or spawn `OSError` marks it `failed` with captured stderr in `print_job.error` (exposed by the API) plus an app-log warning.
- No worker retries jobs left `pending`; adding `PRINT_COMMAND` later does not drain the existing spool. An external bridge must explicitly consume pending jobs.
- On the QNAP host deployment, native `lp` is unavailable; CUPS runs in the `cups-server` Docker container with the `brother` queue. `PRINT_COMMAND` points at the host wrapper `/share/CACHEDEV1_DATA/Container/kid-learning/bin/print-image.sh`, which pipes the image via stdin into `docker exec -i cups-server lp -d brother -o fit-to-page -`.
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
- QNAP host lifecycle lives in `/share/CACHEDEV1_DATA/Container/kid-learning/bin/` (`start-all.sh` / `stop-all.sh`); on QNAP `pkill -f` does not match long command lines reliably and `ps aux` prints PID in the first column, so stop scripts must kill by PID. Gunicorn exits a few seconds after SIGTERM—verify the port is free before restarting.

Keep original assets when derivative generation fails; surface the job state for diagnosis without blocking otherwise playable content.

# Deploy Checklist — Staging & Production

Runbook for the self-hosted deploy on the shared Windows host. Written after an
incident where **both** staging and production ran for hours with no database
connection at all: `DATABASE_URL` pointed at a hostname that did not exist, and
`/health` returned 200 because it touched nothing, so CI reported every deploy
as successful while every business endpoint returned 500.

The rule that follows from it: **a deploy is not verified until a request that
touches Postgres returns 200.**

---

## 0. One-time migration to the current layout

Only needed on hosts that still run containers created before
`compose.deploy.yml` declared `postgres`/`redis` itself. Symptom: `docker
compose ls` lists two config files for a project, or a container named
`<project>-db-1` exists.

```powershell
docker compose -p solodesk-backend-staging    down --remove-orphans
docker compose -p solodesk-backend-production down --remove-orphans
```

`down` without `-v` keeps named volumes, so `<project>_postgres_data` (and all
data in it) survives. The next deploy recreates everything from
`compose.deploy.yml`, with the service renamed `db` → `postgres` reusing the
same volume.

- [ ] Legacy `-db-1` containers gone (`docker ps -a`)
- [ ] `docker volume ls` still lists `solodesk-backend-{staging,production}_postgres_data`

---

## 1. Environment configuration (GitHub → Settings → Environments)

Per environment (`staging`, `production`):

| Kind | Name | Value |
|---|---|---|
| Secret | `DATABASE_URL` | `postgresql+asyncpg://<user>:<pass>@postgres:5432/<db>` |
| Secret | `REDIS_URL` | `redis://redis:6379/0` |
| Secret | `POSTGRES_PASSWORD` | same `<pass>` as in `DATABASE_URL` |
| Variable | `POSTGRES_USER` | same `<user>` as in `DATABASE_URL` |
| Variable | `POSTGRES_DB` | same `<db>` as in `DATABASE_URL` |
| Variable | `API_PORT` | `8001` staging · `8000` production |
| Variable | `CORS_ORIGINS` | frontend origin(s), comma-separated |

- [ ] Host in `DATABASE_URL` is **`postgres`** — the compose service name, not
      `localhost`, not `db`, not a placeholder like `staging-db-host`
- [ ] Host in `REDIS_URL` is **`redis`**
- [ ] `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` match the
      credentials embedded in `DATABASE_URL` exactly — Postgres applies them
      only when the data volume is first created, so a mismatch on an existing
      volume shows up as an authentication failure, not a fresh database
- [ ] Secrets that gate features are set: `JWT_SECRET_KEY`, `SECRET_KEY`,
      `GEMINI_API_KEY`, `OPENAI_API_KEY`, `STRIPE_*`
- [ ] Production has **Required reviewers** enabled

---

## 2. Deploy

Triggered by push to `main`. The pipeline runs unit tests → integration tests →
build images → deploy staging → deploy production.

- [ ] `migrate` exited 0 (`docker compose -p <project> -f compose.deploy.yml ps -a migrate`)
- [ ] "Verify API is healthy" step passed — it now probes `/health/ready`,
      which fails when Postgres or Redis is unreachable

---

## 3. Post-deploy verification — run every time

Substitute `<project>` = `solodesk-backend-staging` or
`solodesk-backend-production`, and `<port>` = `8001` or `8000`.

### 3.1 Dependencies are actually reachable

```powershell
docker compose -p <project> -f compose.deploy.yml exec api `
  python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/ready').read().decode())"
```

- [ ] `"status": "ready"` with `database: ok` **and** `redis: ok`

A 503 body names the failing dependency. `fail: gaierror` means the hostname
does not resolve — check `DATABASE_URL` (step 1) before anything else.

### 3.2 Schema is current

```powershell
docker compose -p <project> -f compose.deploy.yml exec postgres `
  psql -U solodesk -d solodesk -c "select version_num from alembic_version"
```

- [ ] Revision matches `alembic heads` for the deployed commit
- [ ] `\dt` lists the expected tables (not an empty schema)

### 3.3 A real endpoint, end to end

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:<port>/api/v1/public/freelancers
```

- [ ] **200**, not 500 — this is the check that would have caught the incident.
      `/health` alone proves only that the process is running.

### 3.4 Isolation between environments

```powershell
docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' <project>-api-1
```

- [ ] api, worker, beat, postgres and redis are all on `<project>_default`
- [ ] Staging and production containers never share a network
- [ ] `docker ps` shows no published port for any `postgres` or `redis`
      container — datastores must not be reachable from outside the host

### 3.5 Logs are clean

```powershell
docker compose -p <project> -f compose.deploy.yml logs --tail 100 api worker beat
```

- [ ] No `gaierror`, no `ConnectionRefusedError`, no repeating traceback
- [ ] Celery worker logged `ready`

---

## 4. Rollback

Images are currently tagged `:latest` only, so there is **no version to roll
back to** — the previous image is unreferenced as soon as a new one is pushed.
Until images are tagged by commit SHA, recovery means reverting the commit on
`main` and letting the pipeline rebuild.

- [ ] Revert merged to `main`
- [ ] Pipeline green
- [ ] Section 3 re-run in full

---

## Known gaps (tracked, not yet fixed)

- Images are not tagged by commit SHA — no rollback, and no way to tell which
  commit is serving traffic.
- `MOMO_*` real merchant credentials (`MOMOIM8G20260729`) were set on both the
  `staging` and `production` GitHub Environments on 2026-08-19. `Deploy /
  Staging` picked them up automatically (succeeded 2026-08-19T18:37Z, after
  the secrets were written). `Deploy / Production` did NOT, because it
  requires a manual approval (`environment: production`, required reviewer)
  that had gone unaddressed: every `main`-branch run back to at least
  2026-08-03 was stuck at `status: waiting` on that gate — meaning production
  had been running stale code/`.env` for weeks, not just missing the MoMo
  credentials. Approved the pending run manually on 2026-08-20
  (`gh api .../pending_deployments`, `state: approved`); `Deploy / Production`
  then completed successfully (2026-08-19T19:47-19:48Z run timestamps —
  the run itself was created 2026-08-19, approval just happened a day later).
  Production is now current. **Open question, not yet answered:** why the
  required-reviewer approval was going unaddressed for weeks — worth deciding
  whether to add a reminder/alert for pending production approvals, or
  reconsider whether a manual gate that nobody was watching is the right
  control here.
- CI does not run `make check` (ruff + mypy).
- The `db` / `redis-host` network aliases in `compose.deploy.yml` exist only to
  tolerate stale `.env` values; remove them once every environment uses
  `postgres` / `redis`.

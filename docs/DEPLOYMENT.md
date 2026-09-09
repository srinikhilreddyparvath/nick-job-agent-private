# Production deployment

RoleCall is designed as four independently restartable components backed by PostgreSQL and persistent artifact storage:

- `api`: FastAPI web/API service
- `worker`: long-running application queue consumer with database leases
- `scheduler`: periodic discovery and morning-report trigger
- `frontend`: standalone Next.js dashboard, or an independent Vercel deployment

The worker image is based on Microsoft's Playwright Python image and includes headless Chromium. It does not depend on an interactive desktop.

The project has no built-in authentication. Local and deployed instances open directly to the dashboard.

## Required production secrets

Configure these in the hosting provider, never in source control:

- `DATABASE_URL=postgresql+psycopg://...`
- `OPENAI_API_KEY=...`
- `ENCRYPTION_KEY=` a Fernet key if encrypted high-sensitivity persistence is used
- object-storage credentials if the S3 adapter is implemented/configured

Set `ENVIRONMENT=production` and explicit `CORS_ORIGINS`. CORS supports browser interoperability and is not used as access control. Credentialed CORS is disabled.

## Database

Run migrations before the API/worker/scheduler start:

```bash
alembic upgrade head
```

Use the managed PostgreSQL provider's automated backups and point-in-time recovery. The included SQLite-to-PostgreSQL copier defaults to dry-run:

```bash
python scripts/migrate_sqlite_to_postgres.py --target "$DATABASE_URL"
python scripts/migrate_sqlite_to_postgres.py --target "$DATABASE_URL" --execute
```

The copier checks primary keys before insert and does not delete source data.

## Local production simulation

```bash
docker compose build
docker compose up -d postgres api worker scheduler frontend
docker compose ps
docker compose exec api alembic current
docker compose exec worker python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); print(b.version); b.close(); p.stop()"
```

Keep `APPLICATION_MODE=manual` and `AUTO_SUBMIT_ENABLED=false` during initial deployment.

## ATS validation scope

Ashby is the only ATS application workflow validated against a real public form. Validation covers inspection, filling, resume upload, submit-control detection, and durable submission-state handling. Real application history belongs in private operational data, not public documentation.

Greenhouse and Lever application adapters are fixture-tested but have not completed a real submission. Workday application submission has not been validated. Generic/custom ATS behavior is best-effort and must be tested per site. Do not interpret connector-based job discovery support as equivalent to validated application-submission support.

## Practical Railway topology

1. Create one Railway project and managed PostgreSQL database.
2. Add three services from `backend/Dockerfile`: API (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`), worker (`python -m app.worker`), and scheduler (`python -m app.scheduler`).
3. Give all three the same `DATABASE_URL`, OpenAI configuration, policy configuration, and persistent artifact/object-storage configuration.
4. Configure an API pre-deploy command: `alembic upgrade head`.
5. Attach a persistent volume to `/generated` for the API and worker, or implement/configure the S3 adapter.
6. Deploy `frontend/` to Vercel or as the included container. Set `NEXT_PUBLIC_API_URL` to the HTTPS API/reverse-proxy URL.
7. Set `CORS_ORIGINS` to the exact frontend origin.
8. Verify `/health`, `/operations/status`, worker/scheduler heartbeats, and a local fixture browser run.
9. Complete and verify the first user-triggered application receipt.
10. Only then intentionally set `APPLICATION_MODE=auto_submit` and `AUTO_SUBMIT_ENABLED=true`. The receipt prerequisite and pause switch remain enforced.

Emergency stop:

```bash
curl -X POST "$API_URL/operations/pause" -H "Content-Type: application/json" -d '{"value":true}'
```

The dashboard exposes the same `PAUSE AUTONOMY` control.

## Limitations

The initial S3 class is an explicit interface placeholder; local/persistent-volume storage is active. The scheduler is intended as a single service instance; database advisory locking should be added before running multiple scheduler replicas.

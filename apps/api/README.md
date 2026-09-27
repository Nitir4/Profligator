# Profligator API

The first backend slice provides:

- a FastAPI application and OpenAPI document;
- normalized connector contracts and records;
- fixture-only LeetCode and GeeksforGeeks connectors because automated collection is not permitted without approval;
- a live Codeforces connector using the official public API;
- SQLAlchemy persistence, an initial Alembic migration, and dashboard aggregation;
- PostgreSQL and Redis infrastructure through `infra/compose.yaml`.
- candidate registration/sign-in with Argon2 password hashes, signed access tokens, and rotating refresh sessions.

## Local development

```bash
uv sync --project apps/api --dev
uv run --project apps/api uvicorn profligator_api.main:app --app-dir apps/api/src --reload
```

The default database is a local SQLite file so the API works without infrastructure. To use PostgreSQL:

```bash
docker compose -f infra/compose.yaml up -d postgres redis
cp apps/api/.env.example apps/api/.env
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
```

If the default host ports are already in use, override them with
`PROFLIGATOR_POSTGRES_PORT` and `PROFLIGATOR_REDIS_PORT` before starting Compose, and update the corresponding application URLs.

Run the tests with:

```bash
uv run --project apps/api --dev pytest -c apps/api/pyproject.toml apps/api/tests
```

The API currently uses a fixed demo user until authentication is implemented. `inline` sync execution remains the zero-infrastructure development and test default. To exercise background jobs, set `PROFLIGATOR_SYNC_BACKEND=rq`, start Redis, and run a worker from the repository root:

```bash
npm run api:worker
```

`POST /api/v1/syncs` returns `202 Accepted`. In RQ mode it initially returns a `pending` run; clients poll `GET /api/v1/syncs/{id}` until the run succeeds or fails. Worker jobs apply bounded exponential-backoff retries for transient provider failures.

Run a single sync worker for the current MVP. Codeforces request spacing is enforced inside each connector job; a distributed rate limiter is required before horizontally scaling workers.

## Authentication

Registration, login, refresh, logout, and current-user endpoints live under `/api/v1/auth`. Access and refresh values are stored in HttpOnly cookies; only a SHA-256 digest of each opaque refresh token is persisted. Refresh calls rotate and revoke the previous session. Candidate profile, sync, and dashboard routes require authentication and derive ownership from the validated access token.

Before any non-development deployment, set a random `PROFLIGATOR_AUTH_SECRET_KEY` of at least 32 characters and enable `PROFLIGATOR_AUTH_COOKIE_SECURE`. Production startup rejects the development secret or insecure cookies.

## Dashboard analytics

`GET /api/v1/dashboard` derives all visible dashboard datasets from the authenticated candidate's active, solved problem records:

- daily activity counts and current/longest streaks;
- up to six provider-supplied topic assignments;
- normalized Easy/Medium/Hard difficulty counts;
- latest successful-sync freshness;
- explicit `empty`, `partial`, or `ready` data state with missing-metadata reasons.

Topic percentages use total topic assignments because one problem can have multiple provider tags. Difficulty percentages exclude unrated records, which are reported separately. Unique totals remain provisional normalized-title counts until semantic matching is implemented.

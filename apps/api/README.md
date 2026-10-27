# Profligator API

The backend provides:

- a FastAPI application and OpenAPI document;
- normalized connector contracts and records;
- public LeetCode and GeeksforGeeks collectors with explicit coverage and optional offline fixtures;
- a live Codeforces connector using the official public API;
- SQLAlchemy persistence, versioned Alembic migrations, and dashboard aggregation;
- PostgreSQL and Redis infrastructure through `infra/compose.yaml`.
- candidate registration/sign-in with Argon2 password hashes, signed access tokens, and rotating refresh sessions.
- candidate/recruiter authorization and revocable, consented public profile sharing;
- source records, unique problem clusters, exact statement matching, and configurable Ollama/Groq semantic matchers;
- an authenticated browser-extension duplicate-check endpoint with source/submission links;
- Codeforces contest history, ratings/rank, partial-data coverage, and a periodic sync scheduler;
- a normalized public-data service adapter for configurable LeetCode/GFG integration.

The [report-to-backend mapping](../../docs/backend-design.md) includes the original ER, CFD and DFD images, API contracts, model evaluation, migration details, and remaining external acceptance work.

The [collector guide](../../docs/public-collectors.md) documents run commands, live checks against ranked public accounts, source limitations and provider access conditions. LeetCode imports its recent public accepted window, not lifetime solved history. GFG compares the returned solved list with the profile total. Both fetch available public statements within a bounded budget.

## Local development

From the repository root, `npm run dev` starts the API and web app together
and configures the web proxy for the API port. To run only the API, use
`npm run api:dev`.

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

The API derives candidate ownership from authenticated sessions. `inline` sync execution remains the zero-infrastructure development and test default. To exercise background jobs, set `PROFLIGATOR_SYNC_BACKEND=rq`, start Redis, and run a worker from the repository root:

```bash
npm run api:worker
```

`POST /api/v1/syncs` returns `202 Accepted`. In RQ mode it initially returns a `pending` run; clients poll `GET /api/v1/syncs/{id}` until the run succeeds or fails. Worker jobs apply bounded exponential-backoff retries for transient provider failures.

Run a single sync worker for the current MVP. Codeforces request spacing is enforced inside each connector job; a distributed rate limiter is required before horizontally scaling workers.

## Authentication

Google sign-in and explicit linking for password accounts are implemented. Configure the server's Google OAuth client using the [setup guide](../../docs/google-sign-in.md), then restart the API. Secrets remain server-side; no frontend Google secret is needed.

Registration, login, refresh, logout, and current-user endpoints live under `/api/v1/auth`. Access and refresh values are stored in HttpOnly cookies; only a SHA-256 digest of each opaque refresh token is persisted. Refresh calls rotate and revoke the previous session. Candidate profile, sync, and dashboard routes require authentication and derive ownership from the validated access token.

Before any non-development deployment, set a random `PROFLIGATOR_AUTH_SECRET_KEY` of at least 32 characters and enable `PROFLIGATOR_AUTH_COOKIE_SECURE`. Production startup rejects the development secret or insecure cookies.

## Dashboard analytics

`GET /api/v1/dashboard` derives all visible dashboard datasets from the authenticated candidate's active, solved problem records:

- daily activity counts and current/longest streaks;
- up to six provider-supplied topic assignments;
- normalized Easy/Medium/Hard difficulty counts;
- latest successful-sync freshness;
- explicit `empty`, `partial`, or `ready` data state with missing-metadata reasons.

Topic percentages use total topic assignments because one problem can have multiple provider tags. Difficulty percentages exclude unrated records, which are reported separately. Unique totals count confirmed clusters and distinct unchecked records; title similarity alone does not merge problems. Source totals and history completeness remain separate from ingested record counts. Contest records do not contribute to problem totals.

## Periodic sync and matching

Run one scheduler from the repository root with `npm run api:scheduler` or `apps/api/.venv/bin/python scripts/run_scheduler.py`. By default it refreshes active profiles every six hours and skips recent or active runs. RQ mode also requires the worker and Redis.

Set `PROFLIGATOR_MATCHING_BACKEND=ollama` and `PROFLIGATOR_MATCHING_MODEL` to an installed model to enable semantic comparison. The default disabled setting still supports exact statement matching. Provider failures retain imported data. Launch model accuracy, cost, and latency still require evaluation against an agreed dataset.

For hosted comparisons, use `PROFLIGATOR_MATCHING_BACKEND=groq`, `PROFLIGATOR_MATCHING_MODEL=openai/gpt-oss-120b` and `PROFLIGATOR_GROQ_API_KEY` in `apps/api/.env`. The adapter uses existing `httpx` dependencies and strict structured responses. Cached comparisons, shared request pacing and provider cooldown reduce quota consumption; unavailable or oversized comparisons stay unchecked. See [Groq setup and verification](../../docs/groq-matching.md) for limits, live checks and evaluation commands.


## Account identity and photos

Account settings supports display name, a case-insensitive unique username, a short bio, and photo upload/removal. `account_profile.py` validates owner-only updates and normalizes bounded JPEG/PNG/WebP uploads to metadata-stripped 384px JPEGs. Migration `20261027_0013` adds the account fields, unique username index and separate `user_avatars` storage. Existing immutable account IDs, email/Google connections, refresh/extension sessions, linked platform handles, history and share tokens are retained.

Owner photo reads require an account session; shared photo reads require an active share token and stop working when sharing is revoked or the photo is removed. See [profile fields, endpoints and checks](../../docs/account-profile.md). Persistent web login uses rotating refresh sessions (30 days by default). Separate account verification/profile proof and recovery endpoints use independently configured verification/recovery SMTP senders; private passwords stay in environment files.

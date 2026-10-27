# Deployment and acceptance

The full container setup contains PostgreSQL 16, Redis 7, a migration task, API, one RQ worker, one scheduler, and the built web application served by Nginx. The API and web containers run as non-root users. Source `.env` files, databases and development dependencies are excluded from runtime images.

The web container proxies `/api/` to the API and serves SPA routes. Only its HTTP port is published, on host loopback; PostgreSQL, Redis and the API remain on the internal Docker network. Put an HTTPS reverse proxy in front of that port for a public deployment.

## Configure and start

Copy `infra/.env.production.example` to `infra/.env.production`. Set a random hexadecimal database password, a separate random auth secret of at least 32 characters, and the actual HTTPS web origin. Leave environment `production` and secure cookies enabled.

Configure Google with the production web application's OAuth client values. Add the exact callback URL, normally `https://your-domain/api/v1/auth/google/callback`, to Google's authorized redirect URIs. Use the backend setup in [Google sign-in](google-sign-in.md). Rebuild the extension for the same production web origin as described in [extension installation](browser-extension.md).

```sh
docker compose --env-file infra/.env.production -f infra/compose.production.yaml config --quiet
docker compose --env-file infra/.env.production -f infra/compose.production.yaml build api web
docker compose --env-file infra/.env.production -f infra/compose.production.yaml up -d --wait
```

Compose starts database-dependent services after database readiness and successful migration completion. The migration task must exit successfully. Keep one worker and one scheduler for this release. History locks, shared provider pacing and Groq cooldown coordination are implemented; PostgreSQL lock/pacing behavior passed the deployment VM deployment check. Multi-scheduler operation and representative load acceptance remain separate work. Defaults leave semantic matching disabled; enable the Groq values from [its setup guide](groq-matching.md) after setting the host's credentials and validating quota/latency there. The local development key is not copied into an image.

Inspect health with `/health`: the API's JSON must report `database: "ok"`, not just an HTTP 200. API container health checks inspect that value. Worker/scheduler startup is verified, but they do not yet have custom liveness checks or production monitoring.

## Local staging check

Use a **separate Compose project and environment file** with random test secrets, `PROFLIGATOR_ENVIRONMENT=development`, secure cookies false, web URL `http://localhost:18080`, port `18080`, LC/GFG connectors `fixture`, and statement budget zero. This is an HTTP staging configuration; do not use it for a public deployment.

```sh
docker compose --env-file /path/to/staging.env -f infra/compose.production.yaml -p profligator-release-check build api web
docker compose --env-file /path/to/staging.env -f infra/compose.production.yaml -p profligator-release-check up -d --wait
apps/api/.venv/bin/python scripts/verify_deployment.py --origin http://127.0.0.1:18080
```

The HTTP runner creates a synthetic staging account, imports fixture history through the actual worker, and verifies consent/revocation. It first checks the fixture descriptor and refuses to register against a live-collector instance. It is not real signed-in platform, Google, TLS or Groq acceptance.

## Repeat browser and infrastructure checks

Install locked development dependencies with `uv sync --project apps/api --frozen --dev`, npm dependencies with `npm ci`, then browser dependencies with `apps/api/.venv/bin/python -m playwright install --with-deps chromium` on supported CI hosts. Locally an installed Chromium executable also works.

```sh
npm run browser:test -- --output-dir artifacts/browser
```

This starts isolated web/API servers and exercises real UI registration, profile validation/linking, fixture sync, dashboard/search, sharing/public view/revocation and logout/login. It also covers recruiter guards, mobile layout and stale shared-profile clearing. Traces, logs and screenshots are saved per run. No Google or provider browser sessions are used. The runner follows [Playwright's CI guidance](https://playwright.dev/python/docs/ci).

For PostgreSQL/RQ acceptance, provision an **empty dedicated test database** whose name starts with `profligator_acceptance`. Set `PROFLIGATOR_TEST_DATABASE_URL` and `PROFLIGATOR_TEST_REDIS_URL`, then run:

```sh
apps/api/.venv/bin/python scripts/verify_infrastructure.py --output-dir artifacts/infrastructure
```

The runner preserves legacy seeded data through migrations, checks schema columns, queues jobs, launches actual burst workers, queries the dashboard, tests refresh rotation/replay and repeated syncs, and checks failed-job registration. It uses fixtures and a uniquely named queue. `--create-test-database` can instead create/drop a randomly named acceptance database on the configured PostgreSQL server, requiring permission to create databases. It never migrates the application's original database. Redis cleanup targets its own queue rather than flushing Redis.

## CI and remaining release gates

[The GitHub workflow](../.github/workflows/ci.yml) runs API tests, extension tests/build, web type checking/build, frontend browser acceptance, PostgreSQL/Redis/RQ acceptance and complete-container HTTP acceptance with retained artifacts. It needs no Google/Groq secrets and does not scrape live providers. Repository Actions are disabled by the owner. Publishing the workflow definition does not authorize running it; keep Actions disabled and obtain explicit approval before any execution. Use the local commands above for verification.

The app is hosted on deployment VM with HTTPS, boot startup and daily backups; see the dated deployment notes below. Real signed-in extension history, representative model/retrieval evaluation, provider failure acceptance and operational monitoring remain separate checks. Sync locks, refresh safeguards and cross-process request pacing are implemented; representative-load acceptance remains outstanding.

Before upgrades, back up the PostgreSQL volume and test restoration into a separate instance. The initial deployment VM database backup was restored into a separate database. Before later upgrades, rehearse migrations and retain compatible application images; never restore an old production dump over new writes as a routine application rollback. Normal shutdown uses `docker compose ... down`; removing volumes destroys that deployment's database and queue data.


## deployment VM deployment — 26 October 2026

The app is live at **https://profligator.example.com**. Use `infra/compose.production.yaml` with the optional `infra/compose.https.yaml` overlay and `infra/Caddyfile`; set both `PROFLIGATOR_DOMAIN` and the matching HTTPS `PROFLIGATOR_PUBLIC_WEB_URL`. The overlay publishes Caddy on 80/443 and retains certificate storage. Production Compose now forwards the separate verification SMTP settings as well as recovery SMTP.

On deployment VM, `/srv/profligator/current` selects the release, `/srv/profligator/shared/production.env` stores private runtime settings, and `profligator.service` starts the stack on boot. Daily private PostgreSQL backups have seven-day retention; the first backup restored successfully into a separate database. The old hosted workload was backed up locally and removed from the VM. The deployment starts with a fresh database, so local development accounts are not present.

Both SMTP senders authenticated, the configured Groq model was available, and sampled public profile checks passed for all three platforms. On-VM PostgreSQL/RQ fixture acceptance, advisory locking/pacing and public HTTPS/browser smoke checks passed. These checks sent no real emails or paid inference requests. Real-account and representative model acceptance remain pending.

The production Google callback was subsequently configured by the user; the application supports the hosted OAuth flow without changing existing account identities. Origin-specific extension ZIP downloads are available from `/extension/connect`; Firefox temporary-install limitations are stated there. No GitHub Actions were used.


## Editable account profile release — 27 October 2026

Migration `20261027_0013` adds editable account identity and database-backed profile photos. The upgrade/downgrade/re-upgrade was rehearsed on a private PostgreSQL copy with existing row values preserved before applying the additive live migration. API, web, worker and scheduler were recreated with the existing private environment, and live HTTPS browser acceptance passed. Profile photos are included in ordinary database backups. See [profile editing and access rules](account-profile.md).

The full API suite passed 211 tests for this release. Frontend acceptance also covers 30-day persistent refresh sessions across a browser restart, shared account-menu navigation, 10-row question pagination, responsive onboarding/settings and source-local activity separated from UTC. No GitHub Actions were executed.

# Testing and evidence

Reviewed on **15 November 2026**. Run commands from the repository root. A test result should name the source revision, command, date, data source and untested boundaries; avoid calling every successful run a production acceptance test.

## Prepare local checks

```sh
npm ci
uv sync --project apps/api --frozen --dev
```

Use the Node/Python requirements in the [README](../README.md#run-locally). Application credentials are unnecessary for fixture tests. Keep provider calls and paid model inference out of routine regression; the API tests disable default hosted matching and explicitly opt into mocked provider scenarios.

## Choose the right scope

| Check | Command from repository root | What it establishes |
| --- | --- | --- |
| API regression | `npm run api:test` | Auth, roles, data contracts, collectors/matching under controlled responses, photos, verification, migrations and coordination regressions |
| Extension unit regression | `npm run extension:test` | URL/data boundaries, popup/background authorization, history cursors and tracking logic |
| Extension packaging | `npm run extension:build` | Chromium/Firefox package generation and script checks; no signing or store publication |
| Web production build | `npm run build` | TypeScript and Vite bundling; not rendered UI acceptance |
| npm dependency audit | `npm audit --json` | Advisory results for the installed/locked dependency graph at the run date |
| Public-source privacy | `python3 scripts/check_public_privacy.py` | Generic private-pattern/runtime-file checks of tracked working files |
| Reachable-history privacy | `python3 scripts/check_public_privacy.py --history` | Reachable blobs and commit metadata; not cached/unadvertised remote objects or forks |

## Browser acceptance

The current browser runners look for an installed executable named `chromium`. Playwright's downloaded Chromium alone does not satisfy that lookup. Install a system Chromium available on PATH for these runners, as well as the Python development dependencies.

```sh
npm run browser:test -- --output-dir artifacts/browser
uv run --project apps/api --dev python scripts/verify_editable_profile.py --output artifacts/profile-browser
uv run --project apps/api --dev python scripts/verify_password_recovery.py --output-dir artifacts/recovery
```

The frontend runner starts temporary web/API processes and isolated fixture data. It checks registration, profile linking/sync, search/pagination, sharing/revocation, role guards, layout and persistent refresh after a browser restart. The profile runner checks editable identity/photo persistence, access boundaries, removal, long text and responsive layouts. The recovery runner uses a loopback SMTP server and disposable accounts; it does not send external mail.

The profile runner can also take `--base-url`, which creates test accounts on that target and records IDs for operator cleanup. That mode has write side effects and is not a read-only production smoke check. Use only a target authorized for acceptance and clean up only the recorded synthetic identities.

Installed-extension and real-owner-history checks are described in [browser-extension.md](browser-extension.md). An owner-history import writes persisted coding history and needs the actual user's consent/session. Browser fixture pages can establish correct handling of controlled responses while live provider access still fails.

## Database, queues and containers

- `scripts/verify_infrastructure.py` uses an isolated acceptance database and Redis queue to exercise PostgreSQL migrations and real RQ execution. Its database-name checks matter; do not point it at application data.
- `scripts/verify_deployment.py` targets a separate fixture-backed Compose stack. It refuses live collectors before synthetic registration; it is not a generic production test command.
- Schema/head inspection is read-only. Running Alembic upgrades changes a database; migration acceptance requires a backup and a separate rehearsal before a real upgrade.
- Existing SQLite/create-all behavior does not prove PostgreSQL query, locking or migration behavior. Container startup does not prove durable queue processing or scheduler liveness.

See [deployment prerequisites and acceptance](deployment.md) for exact infrastructure variables and commands. Operator backups, rollback images and incident evidence are managed privately.

## Verification recorded for this review

Actual execution date: **15 November 2026**. No application feature source was changed for this documentation update.

| Executed check | Observed result |
| --- | --- |
| `uv run --project apps/api --dev pytest -q -c apps/api/pyproject.toml apps/api/tests` | 211 passed |
| `npm run extension:test` | 17 passed |
| `npm audit --json` | 0 vulnerabilities |

Documentation validation also checks local links, named runner paths, migration head, privacy boundaries, ignored private runbooks and the per-commit changed-line limit. Local logs and detailed publication evidence stay under ignored artifacts.

Earlier October evidence includes web builds, frontend/profile browser acceptance, loopback SMTP, PostgreSQL/RQ and hosted HTTPS checks. These were not repeated by merely reviewing the guides. This November review does not claim fresh real-account OAuth/SMTP/provider/model acceptance, a live deployment check, Firefox signing or a load/restore exercise.

The requested spacing of documentation commit timestamps does not change this actual execution date. Commit metadata is not evidence that these checks ran on separate earlier days.

## Record failures honestly

A failed provider request is not proof that an account has no solves. A missing timestamp is not proof of inactivity. A successful SMTP authentication is not evidence that a reset link arrived or was consumed. A clean npm audit covers known advisories in that graph, not every application security issue. A passing privacy guard cannot discover every unrecognized secret or remove downloaded copies.

Keep original failed output locally when it helps explain a correction, but inspect it for personal data before sharing. Public test reports should use synthetic users and relative source paths. Do not publish cookies, request headers containing credentials, email links, browser profiles or database contents.

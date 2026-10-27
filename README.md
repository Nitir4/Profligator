# Profligator

Profligator brings coding practice from LeetCode, GeeksforGeeks and Codeforces into one profile. It shows imported solves, groups confirmed duplicates across platforms, and lets candidates share a read-only view of their progress.

Deployment origins and operator contact details are configured privately; the public repository uses example domains only.

## What you can do

- Sign up with email/password or Google, with candidate and recruiter roles. Rotating refresh sessions keep you signed in across browser restarts for up to 30 days.
- Edit your Profligator display name, unique username, short bio and profile photo in **Account menu → Edit profile**. Changes appear in the header, dashboard and active shared profile.
- Link supported coding profiles, check their availability, synchronize public history, and see which imports are complete, partial or unavailable.
- View imported and unique problem totals, provider-supplied topics, difficulty, available activity calendars and supported contest statistics. Search/filter solved questions, with 10 entries per page.
- Check account-email ownership and prove linked-profile control with a temporary public-profile challenge. Password recovery and account verification use independently configured SMTP senders.
- Enable a share link for recruiters or others, then revoke it when needed. Shared pages never trigger a new provider sync.
- Connect the browser extension to check questions against your history, import available owner-authorized history, and optionally track provider-confirmed accepted submissions.
- Use exact statement matching without an external model, or configure Groq/Ollama for semantic comparisons with stored source evidence.

Documentation, privacy, terms, service status and contact pages are available in the app. Privacy and terms are draft project-preview pages.

## Supported coding platforms

| Platform | Current integration | Coverage limits |
| --- | --- | --- |
| LeetCode | Public profile/accepted-result collection, available calendars and question metadata; extension imports from the signed-in owner's available history | Public history can be partial. The extension can recover additional available solves and dates, but cannot recover deleted/private history or guarantee a first-ever solve date. Contest statistics are disabled by default. |
| GeeksforGeeks | Public solved-question collection, profile totals and available statements/metadata | Completeness depends on the provider response. Source-local dates stay separate from UTC dates when their time zone is unknown. |
| Codeforces | Official public API for profiles, submissions and supported contest/rating data; public statement recovery | Availability, request limits and inaccessible statements can interrupt collection. Previously imported records are retained. |

CodeChef, HackerRank, AtCoder, Kaggle and GitHub are not enabled coding-history connectors. Checking that a public profile exists is separate from proving you control it.

Source totals, imported records and confirmed duplicate coverage are shown separately. Missing dates or topics remain unknown; the app does not invent them. See [collector behavior and limits](docs/public-collectors.md).

## Run locally

Use Node.js **22.20+ on the 22.x line**, Python **3.12+**, and [uv](https://docs.astral.sh/uv/). Run these commands from the repository root:

```sh
npm ci
uv sync --project apps/api --frozen --dev
npm run dev
```

Open **http://localhost:5173**. The development runner starts FastAPI and Vite together, chooses another API port if 8000 is busy, and updates the web proxy accordingly. Keep port 5173 available when using an extension built for the default origin.

A fresh checkout uses SQLite and inline synchronization, so PostgreSQL and Redis are optional for local development. Public collectors are the default. For an offline fixture demo, set these variables before starting:

```sh
PROFLIGATOR_LEETCODE_CONNECTOR=fixture PROFLIGATOR_GEEKSFORGEEKS_CONNECTOR=fixture npm run dev
```

Only LeetCode/GFG switch to fixtures with that command. Codeforces remains a public API connector.

For PostgreSQL/Redis, background jobs and API-only startup, follow the [API setup](apps/api/README.md). Databases already managed by Alembic must be upgraded before running newer API code:

```sh
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
```

The current schema includes migration `20261027_0013` for editable account profiles and persistent photos.

## Optional services and private configuration

Keep credentials, deployment origins and operator email addresses in ignored environment files or host-managed settings. Public examples use reserved example domains and contain no actual sender identities. Run `python3 scripts/check_public_privacy.py --history` before publishing; an ignored `--private-terms-file` can add operator-specific checks.

| Feature | Configuration and guide |
| --- | --- |
| PostgreSQL, Redis, sync worker/scheduler | [API environment example](apps/api/.env.example) and [API guide](apps/api/README.md) |
| Google sign-in | [OAuth setup](docs/google-sign-in.md); example callback: `https://profligator.example.com/api/v1/auth/google/callback` |
| Password reset and email verification | [SMTP/recovery setup](docs/password-recovery.md); use separate recovery and verification sender settings |
| Semantic matching | [Groq configuration/evaluation](docs/groq-matching.md), or the API's Ollama settings; exact matching works with matching disabled |
| HTTPS/container deployment | [Deployment guide](docs/deployment.md) and [production environment example](infra/.env.production.example) |

The browser and extension call Profligator's API. Google client secrets, SMTP app passwords, model keys and coding-platform session cookies are not bundled into either client. Owner-history collection uses the coding site's session inside the user's browser rather than uploading that session to Profligator.

## Browser extension

On your hosted instance, open **Account settings → Browser extension**, or the `/extension/connect` route, for downloads and connection controls.

For a local build:

```sh
npm run extension:build
```

In Chrome/Chromium, open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select `apps/extension/dist/chrome`. Open the extension popup, choose **Connect with Profligator**, sign in, and authorize the browser connection.

Firefox development packages can be loaded through `about:debugging` → **This Firefox → Load Temporary Add-on** using `apps/extension/dist/firefox/manifest.json`. Temporary installs disappear when Firefox closes. The build also creates an unsigned XPI with a stable extension ID; persistent Firefox installation still requires Mozilla signing. A signing account/package is not configured yet.

Build for the hosted origin when packaging an extension for the deployed site:

```sh
PROFLIGATOR_EXTENSION_WEB_ORIGIN=https://profligator.example.com npm run extension:build
```

The API origin defaults to the same origin. Generated browser folders, ZIPs and unsigned XPI files stay out of Git. See [installation, permissions and acceptance checks](docs/browser-extension.md).

## How it is built

| Area | Current implementation |
| --- | --- |
| Web | React, TypeScript and Vite; shared CSS styles, React state and native browser navigation/forms; custom chart components |
| API | FastAPI, Pydantic, SQLAlchemy and Alembic |
| Storage | SQLite for simple development; PostgreSQL for the hosted stack; processed profile photos stored separately in the database |
| Synchronization | Inline development mode or Redis/RQ workers, with scheduling, sync claims and provider request pacing |
| Collection | Source-specific Python/httpx collectors and optional authorized WebExtension history imports |
| Duplicate detection | Source identity/exact normalized statements, lexical/topic candidate retrieval, and optional Groq/Ollama comparison |
| Authentication | Argon2 password hashes, JWT access cookies, rotating refresh sessions, server-side Google OAuth and scoped extension sessions |
| Deployment | Docker Compose, Nginx and Caddy HTTPS on the Azure VM |
| Verification | Pytest, Node's test runner and Playwright browser/infrastructure acceptance scripts |

```text
apps/api/          FastAPI, collectors, matching, migrations and tests
apps/web/          React application and shared UI assets
apps/extension/    Chromium/Firefox extension, tests and packaging
infra/             Local services, production containers and HTTPS proxy
scripts/           Development runner and acceptance/diagnostic tools
docs/              Architecture, collection, extension and deployment guides
.github/workflows/ CI definition; repository Actions remain disabled
```

Raw source records retain their platform identities and links. Matching groups supported evidence into confirmed clusters; uncertain or unchecked records remain distinguishable. Web, shared-profile and extension views use the same persisted history.

## Verification

After installing dependencies, run:

```sh
npm run api:test
npm run extension:test
npm run extension:build
npm run build
npm audit
python3 scripts/check_public_privacy.py
```

For browser acceptance, install Chromium and run:

```sh
uv run --project apps/api --dev playwright install chromium
npm run browser:test -- --output-dir artifacts/browser
uv run --project apps/api --dev python scripts/verify_editable_profile.py
```

The browser runners use an isolated database and controlled data. Logs and screenshots go under ignored `artifacts/`. Dedicated PostgreSQL/RQ and container checks are described in the [deployment guide](docs/deployment.md).

The 27 October profile release passed **211 API tests**, the web build, frontend browser acceptance and live HTTPS profile-editing checks at desktop/tablet/phone widths. Its PostgreSQL migration was rehearsed on a private database copy before deployment. These results do not establish representative model accuracy or complete access to every provider's history.

After `npm audit fix` on 27 October, the lockfile uses Vite **7.3.7** and `npm audit` reports **0 vulnerabilities**. The web build, 17 extension tests, extension packages and both frontend/profile browser runners passed with the updated dependency.

The GitHub workflow definition is included for review, but **GitHub Actions remains disabled**. Local checks are used; workflow execution requires the owner's explicit approval.

## Current limits and remaining work

- Complete real signed-in owner-history and acceptance-tracking checks across the supported browsers/providers.
- Obtain Mozilla signing for persistent Firefox installation; store publication remains separate work.
- Evaluate semantic matching on a representative labeled dataset, including difficult non-duplicates and larger histories. Synthetic smoke results are not an accuracy guarantee.
- Broaden provider failure/retry, operational monitoring and representative-load checks. Public/private/deleted history limits remain visible in the product.

Deployment, navigation pages, account-email/profile ownership verification, persistent login and profile editing are implemented. The hosted stack has daily database backups and service startup on boot. See [remaining acceptance work](docs/remaining-work.md), [account profile editing](docs/account-profile.md), and [architecture](docs/backend-design.md) for details.

For general support, use [the project issue tracker](https://github.com/Nitir4/Profligator/issues). Keep personal account details out of public issues.

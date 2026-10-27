# Browser extension

Implemented on **3 October 2026**. This phase follows the user's order: extension → scraper improvements → LLM evaluation → deployment.

## Visual source

The popup and notification use the original [Profligator Figma frame](https://www.figma.com/) and report Figure 11.10. The notification card is node `2603:1342`: white surface, slate text, `#4f46e5` primary actions, `#f8fafc` inset cards, `#e2e8f0` borders and the indigo accent gradient. Original exported icons and local Inter fonts are packaged for both browsers. Notification details come from the actual previous attempt; absent dates and similarity percentages are not filled with the design's sample values.

On 7 October the palette correction passed extension tests/build and installed Chromium acceptance with controlled platform pages. The dedicated real-account browser popup was also reloaded and checked for white background, indigo buttons, Inter and the original loaded logo. [Recorded design verification](verification/extension-design-2026-10-07.json).

## Public Codolio reference

Codolio's [extension guide](https://codolio.com/help-center/article/codolio-chrome-extension-your-coding-companion), [Question Tracker guide](https://codolio.com/help-center/article/overview-of-codolios-question-tracker) and [published Chrome listing](https://chromewebstore.google.com/detail/codolio/hhldiohknhejgggdehdeepiggieflfjo) describe a popup that acts on the current coding question and links back to the user's workspace/profile. Profligator uses that interaction structure for its existing history and duplicate-check workflow.

Codolio's documented saving, sheets, tags and linked notes are separate Question Tracker features. They are not copied into Profligator's solved history, and opening a question never marks it solved. No claim is made about Codolio's private backend or a duplicate detector in its extension. The implementation here is original repository code.

## Install locally

From the repository root, with the existing API environment and npm dependencies installed:

```sh
# Existing databases need the scoped-session table before the API runs.
apps/api/.venv/bin/alembic -c apps/api/alembic.ini upgrade head
npm run extension:build
npm run dev
```

The default build connects to **http://localhost:5173** and its `/api` proxy. Use that exact origin when signing in and authorizing. If Vite chooses another port, stop the other development server or rebuild for the actual origin as described below.

### Chrome / Chromium

1. Open `chrome://extensions` and enable **Developer mode**.
2. Choose **Load unpacked** and select `apps/extension/dist/chrome`.
3. Pin/open **Profligator**, then choose **Connect with Profligator**.
4. On the connection page, sign in with your existing Google or password account if necessary. Return to that tab and refresh its account status.
5. Choose **Connect this browser**. Open or reload a supported question tab.

### Firefox

1. Open `about:debugging#/runtime/this-firefox`.
2. Choose **Load Temporary Add-on** and select `apps/extension/dist/firefox/manifest.json` (or its ZIP).
3. Open the Profligator popup and follow the same connection flow.
4. Grant the required site access if Firefox shows a permission request. Reload existing question tabs after installing or changing site access.

Temporary Firefox installations are removed when Firefox closes. A persistent Firefox release requires signing/publication, which belongs to the later release phase. The generated ZIP files are development packages, not published store releases.

### Dedicated real-account acceptance browser

Keep its profile at `artifacts/real-account-browser`, which is ignored by Git. This replaces the earlier temporary `/tmp` profile. Start the application, then open the browser from the repository root:

```sh
PROFLIGATOR_API_PORT=8001 npm run dev
```

In a separate terminal:

```sh
chromium --user-data-dir="$PWD/artifacts/real-account-browser" --remote-debugging-port=9223 --load-extension="$PWD/apps/extension/dist/chrome" --no-first-run --new-window http://localhost:5173/extension/connect https://leetcode.com
```

Sign in to Profligator and LeetCode in that browser, link the signed-in LeetCode handle in Profligator, and choose **Connect this browser**. The acceptance checker uses only this dedicated browser and its installed extension:

```sh
apps/api/.venv/bin/python scripts/verify_owner_history.py --output artifacts/owner-history/readiness.json
apps/api/.venv/bin/python scripts/verify_owner_history.py --import --output artifacts/owner-history/import.json
```

The first command reports readiness and available coverage. The second checks the signed-in handle against the linked account, then imports one bounded batch through the actual extension. Question totals, dated acceptances, statement/difficulty coverage and any continuation cursor are recorded. Further imports follow the extension's saved progress. The reports exclude cookies, OAuth URLs, email addresses and extension credentials. Sign-in is performed by the user in the browser.

After rebuilding, use `scripts/inspect_extension_browser.py --reload` to reload through Chromium's extension manager and check the popup palette. Its default profile is the same persistent directory; `--browser-profile` supports an explicitly selected alternative test profile.

## What works now

- Detects supported LeetCode, GFG and Codeforces problem URLs and captures the visible title, statement and available topic labels. It includes LeetCode contest problem routes, GFG practice/current routes, and Codeforces contest/problemset/gym routes.
- Rechecks after navigation without a page reload and after question content loads. LeetCode title/URL agreement, Codeforces heading indices and available canonical links reject preceding question content during a route transition.
- Sends authenticated checks to `/api/v1/extension/check` through the background worker. The coding page cannot choose an arbitrary API URL.
- Shows an in-page notification only for a confirmed duplicate, plus a popup with the current question and check result.
- Opens the original submission if its provider supplied one, otherwise the previous problem. Only approved HTTPS provider URLs become links.
- Allows dismissal and manual rechecking. Old responses are discarded after navigation or a connection change.
- Keeps a connection across Chromium browser/service-worker restarts. Reconnects can replace the previous device grant.
- Supports disconnect in the popup and candidate-controlled revocation under **Account settings → Manage browser connections**. Revocation from the current browser's connection page clears existing alerts; other devices are rejected on their next authenticated request.
- Imports solved-question names and available dates for linked LeetCode, GFG and Codeforces accounts, with separate per-account tracking switches.

## Import questions and dates

Reload the rebuilt extension and existing coding tabs, connect Profligator, then open the popup's **Solved questions** section. Link accounts in the web application first. Each linked account has **Import solved history** and **Track accepted submissions** controls. Tracking is off until enabled; enabling one account replaces the tracked account for that platform in this browser.

| Platform | History import | Date evidence |
| --- | --- | --- |
| LeetCode | The signed-in tab's solved-question progress list; its username must match the selected linked handle | Actual Accepted submission timestamps; solved status and last-submitted dates do not establish an acceptance date |
| GeeksforGeeks | Existing public solved-problem collector for the selected linked handle | Provider times with a known zone become UTC; unzoned source clock values stay separately labeled |
| Codeforces | Official `user.status` accepted submissions for the selected linked handle | Provider `creationTimeSeconds` timestamps and available submission links |

Keep the LeetCode tab open during imports. Its browser session is used locally; the backend receives only allowlisted question identities, titles, actual acceptance instants, submission IDs and public difficulty/topic/statement metadata. Premium question text is excluded. The source count is retained separately from recovered names. A LeetCode run reads up to 20 pages of 100 question names and checks dates for up to 20 questions, with at most two submission pages per question. **Continue history import** resumes larger name lists. Per-question submission cursors resume older Accepted pages on later imports instead of repeatedly reading the first pages; exhausted available histories are reported as checked and skipped. Public metadata enrichment also rotates across questions, with at most 20 queries per run. Dates are the earliest retrieved acceptances, not a guaranteed first-ever solve: deleted or unavailable submissions can leave permanent gaps. Missing history and inaccessible dates remain unavailable. Account changes stop the import; interrupted imports preserve already saved questions and successful date pages. Browser progress is tied to the device session and is reset on reconnection/disconnection.

The owner-history query structure was checked against the primary [glsync progress query](https://github.com/ahmed-e-abdulaziz/glsync/blob/main/code/leetcode-graphql/user-progress-question-list-query.json) and [submission query](https://github.com/ahmed-e-abdulaziz/glsync/blob/main/code/leetcode-graphql/submission-list-query.json). The implementation is original JavaScript and reads no submission code. Real signed-in account compatibility still requires owner acceptance in a currently accessible browser.

GFG and Codeforces history imports request solved records through the backend without contest imports. Public refreshes share the profile's sync claim, use a default 60-second cooldown (`PROFLIGATOR_EXTENSION_HISTORY_COOLDOWN_SECONDS`), and stop after 20 pages or a 120-second collection timeout. Existing statements, topics, earlier observed dates and source clocks are retained. Private/unavailable GFG histories cannot be recovered through this public collector.

After the final LeetCode batch or a provider import, public metadata enrichment works through **all saved solved identities**, including questions absent from a public recent-submission window. Regular syncs use the same path for LeetCode, GFG and Codeforces. Codeforces retrieves dedicated public statement containers from problemset/contest/gym pages; GFG also supports visible statement containers when embedded data lacks text. The default budget is 20 metadata requests, with a separate 60-second enrichment timeout and persistent cache; later imports/syncs advance unchecked questions. Successful checks preceding a failure are retained. Enrichment never adds solved questions or supplies acceptance dates. Unknown/premium LeetCode statements are excluded. The popup reports statement/difficulty/date coverage, available histories checked and partial metadata failures; imported names and dates remain saved when metadata collection fails. Revoked sessions and disconnected profiles are checked again before metadata changes are applied.

For GFG and Codeforces, checking an opened question can also save its visible public text/topics through `/api/v1/extension/history/metadata`, but only when that exact source identity is already solved in the connected candidate's active history. Submission tracking retains visible text while awaiting provider confirmation, including after navigation. This path enriches candidate-owned records and never writes the shared public cache. Ordinary visits cannot create solves or acceptance dates. LeetCode text recovery uses its public-question query, which explicitly excludes premium text.

Text recovery preserves visible input/output, examples, time/memory limits, line breaks, tables, nested superscripts/subscripts and image URL/alt markers. Codeforces gym records retain gym submission links, including when older acceptances replace newer evidence. It rejects authentication boilerplate, unsupported SVG/canvas/MathML and text exceeding 50,000 characters. Image markers preserve evidence but do not establish semantic equivalence of diagrams. Missing text remains unavailable, with known source identity still usable for checks.

With tracking enabled, clicking **Submit** arms provider confirmation after about 30 seconds, with at most two later retries spaced 65 seconds apart. **Run** and opening a question do not establish a solve. LeetCode imports only a new actual Accepted result within the submission window; GFG/Codeforces refresh only the selected question when their source confirms it solved. Those public responses may identify an existing solve rather than this particular resubmission. Unknown dates are never replaced with the extension's observation time. Alarms and pending work survive worker/browser restarts; Codeforces/GFG confirmation survives page navigation. LeetCode confirmation requires an accessible signed-in tab. Disabling tracking removes pending confirmations, and a revoked/expired device cannot write history.

Imports use the same persisted records, earliest-date preservation and matching service as the dashboard and public sharing views. Browser imports leave provider account ownership unverified. Scoped history endpoints are under `/api/v1/extension/history`; the device cannot manage linked accounts or sharing settings.

On 6 October, Groq semantic comparison was added and enabled in the local development configuration. Extension checks can return semantic positives through the same API; known source identity and exact normalized statements still work without a model call. See [Groq setup and verification](groq-matching.md). Missing text, unavailable matching and API errors have separate messages. A missing match never certifies that a problem is new, and available history still depends on scraper coverage. There is no fabricated similarity percentage.

The former `/extension/duplicate-notification` web route now opens the real connection page. The old design component is retained in source as an unused reference; it is not the installed extension or a live match result.

## Connection and data boundaries

The extension reuses the existing Profligator sign-in through a content-script bridge on the configured `/extension/connect` page. It does not ask for Google or source-platform passwords. During an owner-requested LeetCode import, the browser sends its existing session cookies to LeetCode, and the content script reads the local CSRF value for that request header. Cookies and CSRF values are never uploaded to Profligator or written into import payloads. Google OAuth client configuration remains on the API.

An explicit authorization creates a random, hashed-at-rest, candidate-owned device session. The default expiry is 30 days (`PROFLIGATOR_EXTENSION_SESSION_DAYS`). Its bearer can check questions, list the owner's linked account import summaries, import history for those accounts, and read/revoke its own session. It cannot authenticate to dashboard, profile management, sharing or web-auth endpoints. Candidates can list/revoke their devices using their normal web session.

The token is kept in extension-local storage, never returned to the webpage, popup state, logs or coding page. Chrome storage is restricted to trusted extension contexts. History controls are accepted only from the installed popup; coding scripts can check the current question and arm tracking already authorized for their platform. Pairing requests must come from the exact configured Profligator origin/path. Notifications use a closed shadow root and text nodes, preventing coding pages from directly reading private attempt details or API-provided HTML.

The content detector reads problem content; it does not read submission code or infer that merely visiting a page is a successful attempt. The build requires `storage` and `alarms`, plus access to the configured application/API and supported platform hosts. Firefox declares transmitted website content, question-page browsing activity and extension authentication data in its manifest.

## Other application origins

```sh
PROFLIGATOR_EXTENSION_WEB_ORIGIN=http://localhost:5174 npm run extension:build
# Separate API, if the app's CORS/cookie configuration supports it:
PROFLIGATOR_EXTENSION_WEB_ORIGIN=https://app.example.com \
PROFLIGATOR_EXTENSION_API_ORIGIN=https://api.example.com npm run extension:build
```

The defaults use the same origin for app and API; a production `/api` proxy is the simplest configuration. Builds accept HTTPS origins and localhost HTTP origins only. Reload/reinstall the rebuilt extension after changing origins. Match patterns omit ports for Firefox compatibility; the bridge/worker still validate the exact configured trusted origin, including its port.

## Verification

```sh
npm run extension:test
apps/api/.venv/bin/python -m pytest -q apps/api/tests
npm run build

# Optional browser tooling, kept separately from API runtime dependencies:
python3 -m venv /tmp/profligator-extension-tools
/tmp/profligator-extension-tools/bin/pip install playwright selenium
/tmp/profligator-extension-tools/bin/python scripts/verify_extension.py
# Candidate/recruiter navigation, coverage, mobile sharing and revocation:
/tmp/profligator-extension-tools/bin/python scripts/verify_frontend.py
# Also check currently accessible public pages:
/tmp/profligator-extension-tools/bin/python scripts/verify_extension.py --live
# Also install/check the Firefox package (Selenium downloads geckodriver if needed):
/tmp/profligator-extension-tools/bin/python scripts/verify_extension.py --firefox
```

The browser runner starts temporary API/web servers, seeds synthetic history in a temporary SQLite database, builds separate test packages for that app origin and loads an actual Chromium extension. It verifies sign-in/explicit connection, popup current-question state, LeetCode source identity, GFG cross-platform exact matching, Codeforces source identity/fallback links, an original-submission link click, dismissal, stale DOM during SPA navigation, unrelated questions without alerts, browser restart and revocation. It also exercises all three installed history-import controls, LeetCode signed-in queries against controlled responses, UTC versus unzoned dates, opt-in tracking, Codeforces navigation after submission, and durable tracking preferences. It saves screenshots, logs and a result JSON under `/tmp/profligator-extension-check-*`, then stops its servers/browser. It leaves personal application data untouched.

API coverage includes hashed grants, expiry, forged tokens, origin checks, candidate roles, owner isolation, restricted bearer scope and self-revocation. History tests cover repeat-import idempotence, richer metadata preservation, earliest dates, UTC serialization, source clocks, disconnection, failures and rejection of payloads containing code/credentials. JavaScript tests cover URL identity, safe links, message sender/frame validation, SPA URLs, overlapping requests, signed-in account changes, Accepted-only dates, pagination, bounded date enrichment, popup-only controls, opt-in tracking and cancellation.

The coverage/frontend update passed **123 backend tests**, all three JavaScript test files, and TypeScript/web build. Installed Chromium acceptance passed under `/tmp/profligator-extension-check-xxte_s3b/`, including public statement persistence for all three providers and native DOM checks for time/memory limits, nested math, relative images and stale Codeforces headings. Frontend acceptance passed under `/tmp/profligator-frontend-check-zkawxd4v/`, including role guards, coverage, desktop/mobile shared profiles and revocation clearing displayed data. These isolated controlled checks leave personal records untouched. Temporary evidence paths can expire; the repository runner scripts are reproducible. No new database migration is required by this update.

Installed Chromium acceptance and Firefox installation/connection/popup/disconnect acceptance passed. The Firefox smoke check verifies native background/bridge APIs and backend authentication; its platform alerts remain a separate acceptance item. Chromium screenshots/results and Firefox smoke evidence are in `/tmp/profligator-extension-check-k12ajpm4/`. Backend verification passed 91 tests, and the web TypeScript/build check passed. The personal local database was backed up and upgraded from `20261002_0008` to `20261003_0009`, adding only extension-session storage.

The subsequent history-import/tracking acceptance passed with installed Chromium; the updated Firefox package's connection/popup/disconnect smoke also passed. Evidence is under `/tmp/profligator-extension-check-fy82qplz/`, including `history-imports.png` and `history-tracking.png`. Backend verification passed 106 tests, all three JavaScript test files passed, and TypeScript/web build passed. These use controlled provider responses, not a live signed-in `sample_user` history. No new database migration is required for history imports.

A final Chromium rerun under `/tmp/profligator-extension-check-z8ue9ly_/` also passed after tracking was updated to refresh LeetCode's reported solved total alongside a new accepted question. Both default development packages were rebuilt with the final sources.

Recorded live Chromium check on 3 October: GFG's public `key-pair5616` page returned HTTP 200 and exposed its title and a 503-character statement. LeetCode and Codeforces returned HTTP 403 access challenges in the automated browser, so their current live DOM compatibility remains unverified. Collection stopped at those pages; no challenge bypass was attempted. Controlled-page acceptance verifies extension behavior separately from provider access.

## Remaining acceptance

Verify real signed-in LeetCode history and new accepted submissions, real GFG/Codeforces tracking, broader submit-button layouts (including keyboard shortcuts), normal signed-in browsing on currently accessible LeetCode and Codeforces pages, broader real problem layouts, the full Firefox platform-alert/history flow, and deployed origins/cookies/latency. Missing or unsupported statement representations remain unavailable, while known source identity can still match. Store signing/publication, actual semantic matching and production acceptance follow the user's later phases.


## Hosted Firefox installation (26 October 2026)

The build also produces `firefox-unsigned.xpi` for submission to Mozilla. Ordinary Firefox requires a Mozilla-signed package for installation that survives restart. Submit this artifact through the [Mozilla Developer Hub](https://addons.mozilla.org/developers/) using unlisted self-distribution, then deploy the unchanged signed XPI as `apps/web/public/downloads/profligator-firefox.xpi`. The hosted connection page offers the persistent install only when this exact file exists and is served as `application/x-xpinstall`; otherwise it retains its clearly labeled temporary ZIP installation. The web server returns 404 for a missing signed file. No signed package or restart-persistence acceptance has been completed as part of this update. Follow [Mozilla's self-distribution instructions](https://extensionworkshop.com/documentation/publish/self-distribution/); do not disable signature checks for ordinary users.

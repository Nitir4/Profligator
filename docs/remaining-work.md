# Remaining project work

Updated on 27 October 2026 against the implemented release. Dated evidence below preserves earlier test and development history; the latest verified state takes precedence. The user set the remaining order to extension, scraper improvements, LLM evaluation, then deployment.

The user subsequently deferred LeetCode contests. Scraper work now prioritizes solved questions, usable metadata and available solving dates. LeetCode contest imports and dashboard statistics are disabled by default; fully solved contest evidence remains a source of question names. Historical data is preserved.

The database, API, public collectors, dashboards and installed extension now exist. Statement recovery and frontend fixes are implemented and locally verified. The main remaining work is real-account acceptance, representative semantic-model evaluation, Firefox signing and operational monitoring; provider-hidden history and unsupported statement formats remain explicit data limits.

**6 October update:** Groq comparison integration is implemented and enabled in the local development configuration. Its six-pair live smoke check and isolated application flow passed. Topic/DP-pattern retrieval now filters candidates locally before inference, and the backend suite passes **175 tests** after a [local classification audit](classification-audit.md) and [live duplicate audit](duplicate-audit.md). Manually authored development examples produce 56/60 matching label sets and recover 16/17 equivalents in mixed history; the separate live 18-pair diagnostic detects nine duplicates and rejects nine near misses through the extension API and clustering. An independent scraped evaluation corpus is still absent. Earlier browser/collector checks retain their recorded dates; semantic-model and retrieval release acceptance remain pending. See [Groq setup and verification](groq-matching.md).

## Current verified state

**27 October release:** the app is hosted over HTTPS on the deployment VM with boot startup and daily private database backups; initial backup restoration and the profile migration rehearsal passed. Account-email verification, linked-profile ownership challenges, password recovery, working secondary navigation, persistent login and account profile editing are implemented. The full API suite passed **211 tests**. Local/live profile editing and frontend browser acceptance passed, including phone layouts, source-local activity handling and 10-row solved-question pagination. Firefox persistent installation still needs Mozilla signing. Real signed-in owner-history/tracking and representative model/load/failure acceptance remain outstanding. GitHub Actions is disabled and must remain disabled unless the owner explicitly approves execution.

**7 October acceptance:** 175 API tests, extension tests/packages and the production web build pass. Complete UI registration → linking → fixture sync → dashboard → sharing/public view → revocation → logout/login passes. PostgreSQL legacy migrations and queries, actual Redis/RQ workers, repeat-sync idempotence, refresh rotation/replay rejection and failed-job registration pass. The complete container setup also passes HTTP acceptance through Nginx and the worker. These checks use isolated fixture data. CI is configured but its first GitHub execution remains pending. A separate Chromium window now has the unpacked extension loaded; real signed-in owner-history acceptance still requires user sign-in. See [recorded results](verification/release-2026-10-07.json) and [deployment instructions](deployment.md).

- Authentication, candidate/recruiter API restrictions, profile linking/disconnection, sync jobs, dashboard aggregation, consented sharing, public profile rendering, clusters, and an extension-check API are implemented.
- The current configuration uses SQLite, inline sync execution, Groq semantic matching for local development, and no configured aggregation service. The repository example still defaults to disabled matching.
- Codeforces has a live connector implementation. LeetCode/GFG now default to public collectors, verified against ranked accounts; their coverage and access conditions are recorded in the [collector guide](public-collectors.md).
- Real public samples are verified in a separate preview database; the later public deployment has running scheduling; broader real-account provider acceptance remains outstanding.
- Backend tests: **175 passed** again on 7 October, covering Google/collector/history behavior, extension grants, candidate roles, bearer scope, expiry, ownership and revocation, plus Groq configuration, protocol, caching, quota/error handling, semantic clustering and topic/DP-pattern candidate filters. Retrieval regressions also cover incidental/ambiguous DP mentions, negative constraints, alternative knapsack prose, compact subtype tags, edit-operation synonyms and long descriptions with irrelevant vocabulary. Enrichment checks cover all three providers, saved questions missing from public history, progressive caches across restarts, partial metadata failure, preserved acceptance evidence, wrong-page redirects and revocation during collection.
- TypeScript check and production web build: **passed** on this review.
- Installed Chromium acceptance and the frontend browser runner passed against isolated databases and controlled provider responses. Frontend checks cover recruiter navigation/guards, candidate sharing, matching/date/text coverage, mobile rendering and revocation clearing a displayed shared profile.
- Most deterministic tests use SQLite, fixtures, and mocked providers/queues. Separate acceptance now verifies PostgreSQL and actual Redis/RQ operation, including container HTTP requests. Earlier live collector checks establish response compatibility for four sampled public accounts. Representative model accuracy remains unverified. Public-host operation was subsequently checked in the October deployment described above.

## Required for the report's core release

### 1. Real LeetCode and GeeksforGeeks collection

- [x] Implement source-specific public collectors and record provider access conditions.
- [x] Normalize individual solved IDs/URLs, difficulty and available topics/statements/timestamps.
- [x] Defer LeetCode contest records, ratings and rank while retaining solved-question evidence and existing history.
- [x] Import LeetCode's public activity calendar by year, preserving historical progress and optional calendar failures independently of question imports.
- [x] Record complete/partial coverage and reconcile source totals with imported records.
- [x] Verify real responses from ranked public accounts and test pagination, source errors and repeat syncs.
- [ ] Verify live onboarding through the browser and deployed scheduling/worker operation.
- [x] Add owner-authorized LeetCode history imports and visible public statement recovery for already-solved GFG/Codeforces questions. These are implemented recovery paths, not a provider guarantee of complete lifetime history.

Evidence: [`leetcode.py`](../apps/api/src/profligator_api/connectors/leetcode.py), [`geeksforgeeks.py`](../apps/api/src/profligator_api/connectors/geeksforgeeks.py) and [`collect_profile.py`](../scripts/collect_profile.py) implement and exercise real public collection. The optional normalized-service adapter remains available. Live observations and limits are in the [collector guide](public-collectors.md).

### 2. Problem statements and original-attempt coverage

- [x] Collect available public statements, including visible constraints, input/output and examples, with validated source identity. Use owner-authorized browser recovery when public collection lacks usable text.
- [x] Feed available public LeetCode/GFG/Codeforces statements into matching, within a bounded enrichment budget.
- [x] Preserve available LeetCode/Codeforces submission URLs and explicit absence for GFG.
- [x] Add persistent enrichment for all three providers beyond the per-sync statement budget, prioritizing unchecked questions and remembering unavailable statements.
- [x] Enrich all saved solved identities, including extension imports absent from current public results; retain successful metadata on partial failure and expose coverage in the extension.
- [x] Define and validate unsupported/unavailable statement handling, including access challenges, premium LeetCode text, wrong-page redirects, SVG/canvas/MathML and oversized text.
- [x] Resume older LeetCode Accepted-submission pages across imports, preserving earliest retrieved timestamps and reporting checked available histories.
- [x] Show statement coverage, UTC dates and unzoned source times separately on candidate/shared profiles.

Evidence: [`codeforces.py`](../apps/api/src/profligator_api/connectors/codeforces.py) enriches official API solve records using dedicated public statement containers, including gym routes. GFG supports embedded data and visible statement containers. Live public checks recovered Codeforces `4-A` (1,228 characters) and GFG `key-pair5616` (503 characters). [`extension_history.py`](../apps/api/src/profligator_api/extension_history.py) accepts scoped public metadata only for an owner's already-solved identities; visiting a question never adds a solve or date. Signed-in LeetCode imports add public text and resume older Accepted pages. Premium/private/deleted data, unknown time zones and unsupported renderings remain unavailable. Exhausting available submission pages does not establish a first-ever solve. Fixtures still have no statements.

### 3. Semantic matching acceptance

- [x] Add the Groq hosted provider, secret configuration, strict response validation, comparison caching and rate-limit cooldown.
- [x] Verify live model requests and isolated semantic clustering/dashboard/extension responses using synthetic questions.
- [x] Add local topic aliases, multiple algorithm buckets, DP subpatterns, informative-keyword ranking and bounded unknown fallback before model comparison.
- [ ] Build an agreed, representative labeled dataset of duplicates and difficult non-duplicates.
- [ ] Evaluate multiple actual models for false positives, recall, latency, availability, and cost.
- [ ] Select a model and thresholds from measured results, then configure the running application.
- [ ] Validate candidate retrieval at realistic history sizes and improve it if the lexical shortlist misses too many relevant pairs.
- [ ] Test changed statements, multiple platforms/accounts, comparison budgets, interrupted runs, and concurrent syncs.

Evidence: [`matching.py`](../apps/api/src/profligator_api/matching.py) and [`groq_matching.py`](../apps/api/src/profligator_api/groq_matching.py) supply Ollama/Groq adapters. Groq `openai/gpt-oss-120b` is enabled for local development and passed the [recorded smoke/application checks](groq-matching.md). [`matching_pairs.jsonl`](../apps/api/tests/fixtures/matching_pairs.jsonl) contains only six synthetic smoke pairs. [`evaluate_matching.py`](../apps/api/src/profligator_api/evaluate_matching.py) supports both providers and reports cost as unavailable. A confidence threshold of 0.95 has not been established as a launch accuracy guarantee.

### 4. Actual browser extension

- [x] Create the extension workspace, manifests, build/package commands, and installation instructions.
- [x] Extract platform/problem identity and statement text from supported problem pages, including navigation without a full page reload.
- [x] Implement extension authentication, API origin/permission configuration, and authenticated calls to `/api/v1/extension/check`.
- [x] Add per-account history import and opt-in accepted-submission tracking for LeetCode, GFG and Codeforces, with provider-specific dates and explicit missing-history states.
- [ ] Verify those imports and tracking against real signed-in accounts; installed Chromium acceptance currently uses controlled provider responses.
- [x] Render real responses in the page, dismiss alerts, and open the supplied original-attempt URL or available problem URL.
- [ ] Verify the supported Chrome/Firefox installation and notification flows.

Evidence: [`apps/extension`](../apps/extension) produces actual Chromium/Firefox packages, with a popup, detectors, background checks, history imports, provider confirmations and isolated alerts. Installed Chromium acceptance passes controlled LeetCode/GFG/Codeforces pages, imports and tracking on all three platforms, original-submission navigation, dismissal, SPA transitions, unrelated questions, full browser restart and revocation. Installed Firefox connection/popup/disconnect acceptance passes; its full platform-alert/history flow remains pending. A live GFG page exposed its title and statement; automated LeetCode/Codeforces pages returned access challenges. See [extension installation and verification](browser-extension.md). The old notification design component is no longer routed by the app.

### 5. Finish the frontend API integration

- [x] Show enabled platforms' contest history, ratings/rank and unavailable-data states on candidate and shared profiles; hide LeetCode contest presentation while deferred.
- [x] Display source totals versus imported coverage and data sources clearly.
- [x] Show shared/candidate historical activity, reported LeetCode difficulty totals and labeled GFG source times; group School/Basic as Fundamentals.
- [x] Display individual imported solved questions with search, platform/difficulty filters, pagination and available submission links.
- [x] Refresh owner profiles on dashboard visits with a default 15-minute cooldown; shared views read cached data. See [collection structure](profile-collection-structure.md).
- [x] Update frontend types for platform coverage, ratings, rank and refresh state.
- [x] Complete role-aware frontend types/navigation and matching availability/coverage presentation.
- [x] Use the actual profile-check response to show live or fixture connector state.
- [x] Check public account availability for LeetCode/GFG collectors while leaving ownership unverified.
- [x] Extend public availability checks to Codeforces/optional live adapters.
- [x] Implement linked-account ownership challenges separately from public availability checks, with account-email verification.
- [x] Complete role-aware route guards/navigation for recruiters; password login distinguishes candidate onboarding from recruiter Shared profiles routes.
- [x] Show actual connector descriptors and public-data status on Integrations.
- [x] Remove the Team page's obsolete message that public sharing links are inactive.
- [x] Validate the public profile's presentation, loading/error behavior, and revoked-link behavior in a browser.

Browser verification on 2 October passed for candidate/shared profile rendering, solved-question search/pagination/filtering, mobile layout, and an authenticated live LeetCode refresh. Shared views did not trigger scraping. On 3 October, [`verify_frontend.py`](../scripts/verify_frontend.py) also passed recruiter route guards, coverage presentation, same-site shared-link validation, desktop/mobile rendering and revocation clearing the displayed profile. On 7 October it additionally passed complete UI registration, password login, validation/linking, actual fixture synchronization, search, sharing and revocation using an initially unseeded candidate. Google and signed-in provider acceptance remain separate.

Evidence: [`ProfileDetails.tsx`](../apps/web/src/ProfileDetails.tsx) supplies source/date/text/matching coverage and solved-question tables to candidate and public pages. [`WorkspaceAccess.tsx`](../apps/web/src/WorkspaceAccess.tsx) guards private routes before mounting them. Team and workspace navigation now reflect the authenticated role; recruiter links open consented shared profiles. Public views retry failures and revalidate on focus/visibility, discarding stale responses after revocation.

### 6. Operate and verify the deployed application

- [x] Run and verify the actual PostgreSQL migration and queries.
- [x] Run Redis/RQ with real queued jobs, worker failures and polling.
- [ ] Verify provider retry behavior under actual failures.
- [x] Configure API, worker and scheduler services with dependency ordering and restart policies in the full container setup; verify local startup.
- [x] Configure service supervision and boot startup on the public host.
- [ ] Add worker/scheduler monitoring and operational alerting.
- [x] Implement/test sync claims and cross-process provider pacing.
- [ ] Validate representative provider failures and supported concurrency under load.
- [ ] Keep one scheduler until a distributed scheduling lock is implemented; the current scheduler has no multi-instance lock.
- [x] Configure production secrets, secure cookies, HTTPS, allowed origins and the public share-link origin.
- [x] Configure daily private database backups and verify initial restore into a separate database.
- [ ] Extend operational error monitoring and repeat restore exercises as the deployment evolves.

Evidence: [`infra/compose.production.yaml`](../infra/compose.production.yaml) now contains the complete stack; the older `compose.yaml` still supplies only local database/cache services. [`verify_infrastructure.py`](../scripts/verify_infrastructure.py) verifies migrations, queries, actual workers and failed jobs. [`verify_deployment.py`](../scripts/verify_deployment.py) verifies HTTP requests, queued sync, cookie authentication and sharing through the built web/API containers. The development runner still omits the scheduler. Local fixture acceptance establishes neither public provider access nor production operations.

### 7. Acceptance tests and CI

- [x] Add automated browser tests for registration/login → link → sync → dashboard → enable sharing → public view → revoke.
- [x] Add an isolated frontend browser runner for role access, coverage, public mobile rendering and sharing revocation.
- [x] Add an installed-extension test for real detection, previous-attempt links, and genuinely unrelated problems, using controlled platform pages and an isolated API.
- [x] Add a standalone real collector command, separate from deterministic fixtures.
- [x] Automate fixture integration checks in the local container environment, including actual worker synchronization through HTTP.
- [x] Test PostgreSQL migrations, RQ operation, refresh-session rotation/replay rejection and sequential repeated syncs.
- [ ] Test concurrent refresh sessions and concurrent sync behavior.
- [x] Add CI for API tests, extension tests/packages, frontend type checking/build, browser acceptance, PostgreSQL/RQ and full-container HTTP checks.
- [ ] Run GitHub CI only if the owner explicitly approves that execution; repository Actions remains disabled.
- [ ] Record model/provider acceptance results and the report's remaining recruiter research assumptions.

Evidence: the repository contains API/extension tests, installed-extension acceptance runners, the complete frontend browser runner, PostgreSQL/RQ and HTTP deployment runners, and [the CI workflow](../.github/workflows/ci.yml). The current recorded passes are local executions. CI has not yet run on GitHub. Browser checks complement the web production build's type and bundling checks.

## Visible secondary work

- Google sign-in and explicit account linking are implemented. The real client is configured locally, its authorization redirect was verified, and the user confirmed successful Google sign-in on 2 October. See [setup guide](google-sign-in.md). Password recovery now has request/reset screens, SMTP delivery, one-use expiring tokens and session invalidation; local browser/SMTP acceptance passes. Separate recovery/verification SMTP senders are configured privately; broader inbox and user-flow acceptance remains distinct from authentication checks. See [password recovery](password-recovery.md).
- Documentation, privacy, terms, status and support routes now work; privacy/terms remain draft project-preview content.
- Existing README references to planning files outside the repository point to absent files in this checkout; make project documentation self-contained.
- Keep the GitHub source/README checkpoint current while preserving private environment files, local artifacts and academic documents outside code publication.

## Explicitly deferred by the SRS

Additional CodeChef/HackerRank connectors, automatic topic tagging, visible similarity scores, recommendations, skill-gap analysis, progress prediction, and recruiter comparison are later scope. The Team screen does not make team invitations a first-release requirement.

## Delivery sequence

Follow the order requested on 3 October: finish the installed extension and remaining normal-browser checks; improve the scrapers and source coverage; evaluate and enable LLM matching; then deploy and resolve issues with storage, queues, scheduling, origins and full acceptance. The app is deployed, while model/provider acceptance remains necessary before claiming complete accuracy or source coverage. CI execution remains subject to the owner's separate approval.

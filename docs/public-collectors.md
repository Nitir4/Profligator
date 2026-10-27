# LeetCode and GeeksforGeeks collectors

Implemented and checked on 1 October 2026, with LeetCode `fjzzq2002` and GFG `cerberus97` rechecked on 2 October. The API now defaults to the two public collectors. No external aggregation service is needed. Codeforces continues to use its official API. Owner-triggered refreshes and question presentation follow the [profile collection structure](profile-collection-structure.md).

On 3 October, the user deferred LeetCode contests to focus on solved questions. Default syncs import no LeetCode contest records, ratings or ranks, and candidate/shared dashboards hide previously saved LeetCode contest statistics. Existing solved questions and historical contest records remain stored. Minimal fully solved contest evidence is still used to recover question names; unavailable optional evidence does not block valid recent accepted questions.

## What is collected

| Field | LeetCode | GeeksforGeeks |
| --- | --- | --- |
| Public profile | Handle, display name, total solved | Handle, display name, total solved |
| Solved records | Recent accepted problems plus question names from contests publicly reported as fully solved | Individual problems in the public solved-problem response |
| Coverage | Complete only when distinct recovered names reconcile with the source solved total; otherwise partial | Complete only when the distinct returned count equals the profile's total; otherwise partial |
| Identity | Problem slug, canonical problem URL | Problem slug, canonical problem URL |
| Metadata | Difficulty, topic tags, available public statement | Source difficulty bucket; topic tags and statement when available on the public problem page |
| Acceptance time | Earliest public acceptance observed; unknown for contest-backfilled questions | Zoned timestamps become UTC instants; unzoned source times are preserved separately and displayed with their unknown time zone |
| Activity | Public daily submission calendar by year, separate from individual acceptance dates | No verified calendar integration; unzoned source times are not added to the UTC heatmap |
| Source difficulty totals | Reported Easy/Medium/Hard counts alongside recovered metadata | Recovered source difficulty buckets; School/Basic appear as Fundamentals in dashboard summaries |
| Submission URL | Public submission ID converted to its detail URL; unavailable for backfilled questions | Unavailable; no submission URL is invented |
| Contests | Disabled by default; optional collector supports attended contests, start dates, rounded rating and contest rank | Unavailable; coding score and institute rank are not imported as contest rating/global rank |

LeetCode uses public GraphQL responses. GFG reads profile data from the current Next.js Flight stream, fetches the public `practiceapi.geeksforgeeks.org/api/v1/user/problems/submissions/` response, and reads problem metadata from `__NEXT_DATA__`. Pages are parsed as data; JavaScript is never executed. Legacy GFG `/user/` links are accepted and normalized to `/profile/`.

Recent submissions are not a lifetime solved list. A profile can have hundreds of solved problems and no public recent submissions: this was observed for LeetCode's rank 2 account. Syncs retain previously imported problems when they leave the recent window. Earlier observed acceptance times, submission links and richer problem metadata are preserved on subsequent imports. They do not establish the user's first-ever acceptance time.

The LeetCode collector also requests `problemsSolved`, `totalProblems`, and each contest's question names in the same public history query. It backfills a contest only when the account attended, the reported solved count equals the total, and the distinct question list has that exact length. This is an inference from public contest completion, rather than an individual acceptance receipt. The source checksum incorporates that contest evidence. Partial contests, rankings alone, missing lists and duplicate/inconsistent question lists cannot identify solved tasks and are excluded. Backfilled questions have no invented acceptance date or submission URL; direct acceptance evidence takes priority for overlapping problems.

Increasing the public recent-submission limit does not establish lifetime access. A live comparison of limits 20 and 1,000 returned the same 4 submissions for `fjzzq2002`, zero for `neal_wu`, and zero for `Yawn_Sean`, despite source solved totals of 231, 253 and 1,082. The public progress query supplies counts by difficulty. No public endpoint providing those accounts' entire historical question list has been verified. An owner-authorized complete export/import is a separate potential integration.

GFG School/Basic labels remain source labels on questions and are grouped as Fundamentals in dashboard difficulty summaries, following Codolio's documented convention. Private profiles, unavailable fields and inaccessible older contest statements remain unavailable. All public statements contain their visible examples and constraints; images retain source/alt markers and table cells retain separators. SVG/canvas/MathML statements and text beyond 50,000 characters remain unavailable to avoid unsafe exact comparisons.

## Daily calendars and question dates

LeetCode's public `userCalendar(year)` response supplies `activeYears` and `submissionCalendar`. The implementation shape was checked against the primary [calendar query implementation](https://github.com/alfaarghya/alfa-leetcode-api/blob/main/src/GQLQueries/userProfileCalendar.ts) and verified directly. Codolio documents [submission heatmaps and LeetCode privacy settings](https://codolio.com/help-center/article/frequently-asked-questions), but its exact backend implementation is not established by those docs.

Application syncs fetch at most three calendar years by default. Current and previous years support the rolling 12-month view; the remaining request budget prioritizes uncollected historical active years, followed by checks older than 24 hours. Saved year snapshots let later jobs continue progress. A limit of one fetches only the current year; use at least three for progressive historical collection. The standalone measurement command can use `--calendar-year-limit 10` to recover up to ten years in one run; it does not automatically resume calendar years from its problem-metadata cache.

Calendar days are keyed by their provider epochs and stored as UTC dates/counts, without question IDs. They never create solved-question records or fill missing per-question acceptance times. A calendar replaces dated solved-record activity for that account/year, preventing double counting. Other profiles and uncovered years retain the existing dated-record fallback, with a distinct count label. Known/unknown acceptance timestamp counts continue to refer to individual solved records. Failed or unavailable calendar requests preserve saved activity and allow valid question imports to complete. Malformed dates, wrong users, out-of-year timestamps, duplicate days, booleans and negative counts cannot become fabricated activity.

GFG's naive `user_subtime` values are normalized into `source_solved_at` with no UTC suffix. They display as source time with an unspecified time zone; `occurred_at`/`solved_at` remain null. Earlier observed source clock values survive later submissions. Neither the LeetCode recent timestamp nor the GFG source clock establishes a user's first-ever solve time.

Candidate and shared profiles now display the same historical heatmap, UTC counts, source difficulty totals and saved calendar years. Public views continue to read persisted data only. Year selection includes every saved year containing activity, and mobile users can scroll through the full year. LeetCode coverage cards explain the relevant Recent AC Problems/Submission Details privacy settings.

## Configuration and operation

Defaults in [`config.py`](../apps/api/src/profligator_api/config.py) and [`apps/api/.env.example`](../apps/api/.env.example):

```dotenv
PROFLIGATOR_LEETCODE_CONNECTOR=scraper
PROFLIGATOR_LEETCODE_COLLECT_CONTESTS=false
PROFLIGATOR_GEEKSFORGEEKS_CONNECTOR=scraper
PROFLIGATOR_SCRAPER_MIN_INTERVAL_SECONDS=2.05
PROFLIGATOR_SCRAPER_STATEMENT_LIMIT=20
PROFLIGATOR_SCRAPER_CALENDAR_YEAR_LIMIT=3
```

Set either connector to `fixture` for an offline demo. Setting `PROFLIGATOR_AGGREGATION_SERVICE_URL` overrides both with the existing normalized-service adapter. Candidate input cannot set provider endpoints or the service URL.

LeetCode contest collection and dashboard presentation remain disabled unless `PROFLIGATOR_LEETCODE_COLLECT_CONTESTS=true` is explicitly configured. The standalone measurement command also accepts `--include-contests` for an individual run. The default question query omits contest ratings, ranks and dates while retaining completion counts and question names needed for solved-question evidence. Other platforms' contest behavior is unchanged.

Each sync uses the existing authenticated link → sync → persistence → matching pipeline. Profile checking fetches public statistics for all live connectors, including Codeforces and optional adapters; it checks public availability and does not prove account ownership. The frontend displays the returned connector mode.

Requests are spaced per provider within an API/worker process, including jobs that create fresh registries. Run one sync worker; multiple processes need a distributed limiter. Application syncs persist public problem metadata and check timestamps in `problem_metadata`, shared by provider/problem identity. Unavailable metadata is also remembered for 24 hours. Each sync prioritizes unchecked questions, then the oldest expired checks; fresh cache hits consume no request budget. This resumes progress across workers and restarts instead of repeatedly enriching the first page. Cached public metadata never establishes whether another candidate solved that problem.

At most 20 distinct problem metadata requests are made per sync by default; setting the limit to zero imports records and reuses existing metadata without requesting problem pages. Application syncs spend this budget once across all persisted solved identities for LeetCode, GFG and Codeforces, including extension imports and questions absent from current public results. Extension history imports use the same enrichment after committing names/dates. Enrichment has a separate 60-second timeout; provider denial, rate limiting or metadata failures preserve history and earlier successful metadata checks. Metadata updates preserve current acceptance evidence even when dates change during collection. LeetCode/GFG paginate recovered records locally in pages of at most 1,000 even when metadata enrichment is capped. Without a database store, standalone collectors use a bounded 1,000-entry process cache. Unchecked questions beyond a run's budget remain available as solved records with whatever metadata the history response supplies. Previously observed metadata is retained while expired checks wait for their turn.

Codeforces solve/date evidence remains sourced from official `user.status` responses. Its metadata path now fetches dedicated public statement containers from problemset/contest/gym pages. GFG falls back to a visible statement container when embedded data lacks text. Final response paths must match the requested source identity; redirects to another question cannot supply text. Access challenges, incomplete/ambiguous containers, unsupported structures and unavailable pages retain existing history without fabricating statements.

The [browser extension](browser-extension.md) adds another recovery path: signed-in LeetCode imports public question metadata and resumes older Accepted-submission pages. GFG/Codeforces visible public text can enrich an already-solved identity in the owner's history. Browser metadata stays candidate-scoped and never populates the shared public cache; visiting a page creates neither a solve nor a date. The dashboard shows text, UTC-date and unzoned-source-time coverage separately. Available history exhaustion is not a first-ever acceptance guarantee.

Saved coverage reconciles all persisted solved problems for the linked account against the latest source total, including questions that have left a public recent-submission window. A source count decrease is reported as a mismatch and does not delete previously imported history.

Existing databases must apply migrations before running the updated API: `uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head`. Collector migrations run through `20261002_0008`; current head `20261003_0009` adds scoped extension sessions. New empty databases can use automatic schema creation. The migrations add problem metadata, calendar snapshots/profile fields and unzoned source submission times, preserving users, OAuth bindings and coding history. Existing local development databases were backed up and brought to the new schema; automatic table creation alone does not add columns to existing tables.

Responses are limited to 5 MB. Redirects stay on a fixed provider host list. Authentication/access denial and rate limiting stop the run without immediate retries; later scheduled/manual syncs can try again. Timeouts and server failures use the existing bounded retry policy. Failed imports preserve earlier committed records. No login cookies, credentials, CAPTCHA solving or alternate identities are used.

Run either collector independently without modifying the application database:

```bash
apps/api/.venv/bin/python scripts/collect_profile.py leetcode fjzzq2002 \
  --output /tmp/leetcode-profile.json
apps/api/.venv/bin/python scripts/collect_profile.py geeksforgeeks cerberus97 \
  --output /tmp/gfg-profile.json
# Reduce problem-page requests for a quick profile/history check:
apps/api/.venv/bin/python scripts/collect_profile.py leetcode neal_wu \
  --statement-limit 3 --output /tmp/leetcode-rank2.json
# Reuse a separate cache to advance enrichment on each invocation:
apps/api/.venv/bin/python scripts/collect_profile.py leetcode fjzzq2002 \
  --statement-limit 3 --metadata-cache /tmp/profligator-collector-cache.db \
  --output /tmp/leetcode-profile.json
```

JSON output contains the connector descriptor, profile snapshot, normalized records, checksums and explicit nulls for unavailable fields. Exit status 2 reports a structured connector error. Application sync records provide the same failure code and retain prior data.

## Live verification

### Saved-history enrichment on 3 October

Fresh question-only snapshots were imported into isolated databases, then enriched without requesting another public solve list. LeetCode `fjzzq2002` retained 96/231 known questions and four UTC acceptance dates while two runs of three metadata requests increased statement/difficulty/topic coverage from zero to three, then six. GFG `cerberus97` retained 11/11 questions and eleven unzoned source times; four runs of at most three metadata requests checked all eleven identities and recovered one public statement with topics. The other ten pages supplied no usable statement. Fresh connector/database connections were used between runs, confirming persistent progress. Artifacts are under `/tmp/profligator-coverage-oct3/`; personal application data was untouched. These are metadata gains, not additional recovered solves or proof of live signed-in extension compatibility.

The current backend suite passes **123 tests**. Coverage verifies regular sync enrichment for browser-only question identities, cache progress after restarts, retention after metadata denial, revocation during collection, concurrent acceptance updates, dedicated statement extraction, redirect identity, Codeforces availability errors and candidate-scoped browser metadata. All three extension JavaScript test files and Chrome/Firefox package builds pass. Installed Chromium and frontend browser acceptance also pass against controlled responses and isolated databases.

### Public statement recovery on 3 October

A separate live public-page check recovered Codeforces `4-A` with **1,228 statement characters** and GFG `key-pair5616` with **503 characters**. The probe used the connectors' actual metadata methods and wrote `/tmp/profligator-problem-coverage-results.json`; it did not change personal records. These are two compatible public statement samples, not new solved-history counts or live signed-in extension acceptance. Temporary artifacts can expire. Provider-blocked/deleted history, unzoned GFG times and unsupported SVG/canvas/MathML statements remain unavailable.

Accounts were selected from the public [LeetCode contest ranking](https://leetcode.com/contest/globalranking/) and a GFG [published contest leaderboard](https://media.geeksforgeeks.org/courses/syllabus/7cd8e6eaa1695967baf4f5998a1ef267.pdf). The latter identifies the winner and runner-up of its March 2022 contest; it is not a current global GFG ranking.

The measurements below precede the 3 October scope change. Their contest counts document those historical runs; current default runs import zero LeetCode contests.

| Account | Selection | Source solved total | Imported problems | Contests | Public statements | Coverage |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `fjzzq2002` | LeetCode global contest rank 1 at verification | 231 | 96 | 26 | 3 | Partial |
| `neal_wu` | LeetCode global contest rank 2 at verification | 253 | 204 | 51 | 0 | Partial |
| `cerberus97` | Published GFG contest winner | 11 | 11 | 0 | 1 | Count reconciled |
| `jatinyadav251` | Published GFG contest runner-up | 8 | 8 | 0 | 0 | Count reconciled |

The original recent-only collector recovered 4 and 0 questions for the two LeetCode accounts. The current contest backfill recovered 92 additional names for rank 1 and 204 for rank 2. The latest LeetCode verification files are under `/tmp/profligator-history-coverage/`, with statement budgets of 3 and 0 respectively; the GFG files remain under `/tmp/profligator-scraper-research/`, using budgets of 20 and 3. These observations establish current response compatibility for the sampled accounts, not uninterrupted provider availability or general lifetime-history access.

Deterministic tests cover compressed responses, fragmented Flight data, identity/schema errors, unavailable statements, pagination over 1,000 records for both platforms, bounded enrichment, duplicate submissions, safe contest backfill, rejection of ambiguous contest evidence, URL validation, denied access, rate limiting, authenticated sync, repeat-import idempotence, persisted metadata and older acceptance preservation, and retaining records after a failed sync. Tests also verify default question-only collection, optional contest-evidence failures, skipped contest imports, and hidden legacy contest data on private and shared dashboards. Test statements and identities are synthetic. Calendar tests cover progressive historical collection, partial access failures, malformed data, snapshot replacement, no double counting, sharing consent, disconnection, preserved source times and optional schema failures. Migration upgrade/downgrade preservation is verified with SQLite; PostgreSQL operation remains unverified.

### Latest measurements on 2 October

| Account | Recovered / reported questions | Questions with UTC acceptance timestamps | Questions with unzoned source times | Calendar activity days | Calendar submissions | Saved calendar years |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| LeetCode `fjzzq2002` | 96 / 231 | 4 | 0 | 73 | 450 | 2022–2026 |
| LeetCode `neal_wu` | 204 / 253 | 0 | 0 | 89 | 541 | 2018–2021, 2025–2026 |
| GFG `cerberus97` | 11 / 11 | 0 | 11 | Unverified | Unverified | — |
| GFG `jatinyadav251` | 8 / 8 | 0 | 8 | Unverified | Unverified | — |

Both LeetCode samples reconciled every year listed by their public calendar, plus the current/prior year. Years with no activity may still have empty saved snapshots. The first rank-1 calendar run timed out while fetching an older year and retained its valid recent years; a later independent measurement recovered the remaining years. Statements, question names and calendars have separate coverage. Artifacts are under `/tmp/profligator-codolio/`; temporary live snapshots are not a general uptime or completeness guarantee.

Browser checks passed for historical year selection, source difficulty totals, GFG source-time labels, saved public views, day-cell separation and desktop/mobile layout including horizontal heatmap scrolling. The sample preview uses a separate database and does not claim that different handles belong to the same person.

On 2 October, separate live runs using persisted caches retained 96/231 LeetCode questions and 26 contests while available statements increased from 5 to 8. GFG retained all 11/11 questions while available statements increased from 0 to 1 as enrichment moved past inaccessible problems. Outputs and isolated cache databases are under `/tmp/profligator-scraper-v2/`. A targeted check of the public standings API for partially solved Weekly Contest 362 returned HTTP 403; collection stopped, and that endpoint was not added to the connector. These changes improve metadata coverage, not access to a competitor's missing lifetime LeetCode history.

On 2 October, fresh outputs were saved to `/tmp/profligator-preview/leetcode.json` and `gfg.json`: 96/231 LeetCode problems with 26 contests, and 11/11 GFG problems. Browser checks verified shared views do not request source refreshes; title search, platform filtering, pagination, GFG's complete list, mobile width, and an authenticated owner refresh succeeded. A separate preview database was used. Temporary outputs are recreated using the [preview commands](profile-collection-structure.md#local-preview-with-public-samples).

### Fresh question-focused measurements on 3 October

All four profiles were fetched again on 3 October using the default disabled LeetCode contest setting, `--statement-limit 0`, and `--calendar-year-limit 1` for LeetCode. These runs measured recovered question identities without requesting statement enrichment or complete historical calendars. They did not modify the application database.

| Account | Recovered / reported questions | Questions with UTC acceptance timestamps | Questions with unzoned source times | Imported contest records |
| --- | ---: | ---: | ---: | ---: |
| LeetCode `fjzzq2002` | 96 / 231 | 4 | 0 | 0 |
| LeetCode `neal_wu` | 204 / 253 | 0 | 0 | 0 |
| GFG `cerberus97` | 11 / 11 | 0 | 11 | 0 |
| GFG `jatinyadav251` | 8 / 8 | 0 | 8 | 0 |

The recovered question counts match the prior measurements. LeetCode coverage remains partial; minimal fully solved contest evidence still supplies additional question names without importing contest records or statistics. Both GFG lists reconcile with the reported source total. Fresh JSON outputs are under `/tmp/profligator-2026-10-03-question-check/`.

## Provider access conditions

These are unofficial collectors. [LeetCode's terms](https://leetcode.com/terms/) prohibit scraping; its [robots file](https://leetcode.com/robots.txt) disallows GraphQL and other API paths. [GFG's terms](https://www.geeksforgeeks.org/legal/terms-of-use/) restrict automated extraction and systematic collection. Successful public requests do not establish provider permission or a supported integration. The optional normalized-service adapter remains available for an authorized data source.

Public response formats were investigated using the primary upstream repositories [alfa-leetcode-api](https://github.com/alfaarghya/alfa-leetcode-api) and [coding-profile-service](https://github.com/mearjuntripathi/coding-profile-service), then verified directly against the providers. The collectors are original Python implementations; no upstream application was installed or copied into the project.

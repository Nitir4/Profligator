# Profile collection structure

Implemented on 2 October 2026. This follows Codolio's published behavior rather than an unverified copy of its private scraper implementation.

## Public reference

Codolio's [Profile Tracker guide](https://codolio.com/help-center/article/building-your-ultimate-portfolio-profile-tracker) documents collection by public username, combined platform statistics and contest ratings, and an owner-triggered refresh when the signed-in owner visits their profile, with a 15-minute cooldown. Its [Question Tracker guide](https://codolio.com/help-center/article/overview-of-codolios-question-tracker) describes a separate question workspace populated through manual additions, sheets and its extension. Those descriptions do not establish access to every competitor's lifetime solved-question history.

## Implemented flow

1. Link a public handle through the platform-specific connector. Public availability is distinct from ownership verification.
2. Fetch a profile snapshot with source totals and available ratings/rank.
3. Fetch individual public solved records and contest history separately, through the shared connector contract. Public requests remain bounded and throttled.
   LeetCode public calendars supply daily activity independently of question dates. A default three-year budget refreshes recent years and advances into unchecked historical years on later visits. Calendars persist per account/year; malformed or inaccessible responses preserve saved activity. Calendar counts replace that account's dated-record activity in covered years to prevent double counting.
4. Normalize provider IDs, URLs, metadata, available timestamps and coverage. Persist records idempotently, retaining previous acceptances and richer metadata as public windows change.
   Public problem enrichment checkpoints persist separately by provider/problem identity. Each refresh spends its bounded budget on unchecked questions before expired checks; unavailable statements are remembered so later questions still advance. Metadata can be reused across candidates without treating it as evidence that another candidate solved the problem. Account coverage counts all saved solved records against the current reported total.
5. Render cached dashboard data immediately. The signed-in candidate dashboard requests refreshes of its linked accounts. The server reuses active jobs and recent attempts; the default cooldown is 900 seconds, configurable through `PROFLIGATOR_PROFILE_SYNC_COOLDOWN_SECONDS`.
6. Render platform coverage, reported LeetCode difficulty totals, contest history, historical activity and a searchable, paginated solved-question table. Filters apply to the imported records, not to the platform's larger reported total. GFG School/Basic records appear as Fundamentals in aggregate difficulty summaries.
7. Public shared profiles read saved data without triggering source requests. Their question endpoint rechecks sharing consent on every request and returns 404 after revocation.

Claims serialize through a transaction on the platform row, avoiding duplicate dispatches for overlapping requests. Successful and failed attempts observe the cooldown. Abandoned jobs can be marked failed and retried after their timeout. SQLite concurrent claims are tested; production PostgreSQL/RQ operation still needs verification. The existing separately operated scheduler remains available as a background fallback required by the report.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/syncs` | Refresh a candidate's linked account or return its active/recent run |
| `GET /api/v1/solved-problems` | Candidate-only imported solved-question page |
| `GET /api/v1/public-profiles/{token}/solved-problems` | Consented public question page |

Question pages accept `offset`, `limit` (1–100), `search`, `platform` and `difficulty`. They exclude contests, unsolved records and disconnected accounts. Public responses omit private user details and internal matching fields. `solved_at` exposes an observed zoned acceptance timestamp when available. `source_solved_at` preserves GFG source clock fields whose time zone is unknown, shown with an explicit label. Contest-inferred LeetCode question dates remain unavailable; the activity calendar does not fill them in.

## Local preview with public samples

```sh
apps/api/.venv/bin/python scripts/collect_profile.py leetcode fjzzq2002 --statement-limit 3 --output /tmp/profligator-preview/leetcode.json
apps/api/.venv/bin/python scripts/collect_profile.py geeksforgeeks cerberus97 --statement-limit 3 --output /tmp/profligator-preview/gfg.json
apps/api/.venv/bin/python scripts/preview_profiles.py /tmp/profligator-preview/leetcode.json /tmp/profligator-preview/gfg.json
PROFLIGATOR_DATABASE_URL=sqlite:////tmp/profligator-preview/preview.db PROFLIGATOR_API_PORT=8001 PROFLIGATOR_PUBLIC_WEB_URL=http://localhost:5174 npm run api:dev
# In a second terminal:
PROFLIGATOR_API_PORT=8001 npm run dev --workspace @profligator/web -- --host 127.0.0.1 --port 5174 --strictPort
```

Use the generated public links or demo login emails with password `PreviewOnly2026!`. These are separate sample candidates, not accounts claimed to belong to the same person. Preview data lives in `/tmp`; recreate it with these commands after a system restart.

For broader calendar measurements, use `--calendar-year-limit 10`. The latest four-account report is in the [collector guide](public-collectors.md#latest-measurements-on-2-october). Existing databases must upgrade through Alembic before using the new calendar/profile columns.

# Remaining project work

Reviewed against the source on **15 November 2026**. This checklist distinguishes implemented behavior from acceptance still needed. It replaces older completion estimates; dated collector/model audits retain their original observations.

## Implemented baseline

| Area | What exists | Evidence and limits |
| --- | --- | --- |
| Authentication | Password/Google sign-in, explicit Google linking, candidate/recruiter guards, rotating refresh sessions and logout | API regression; earlier browser restart/refresh acceptance. Real OAuth checks have their own dates. |
| Account profile | Display name, case-insensitive unique username, bio, validated photo upload/removal | Owner-isolation/session/share regression; earlier local/live profile acceptance. |
| Recovery and proof | Independent SMTP sender configuration, one-use reset/inbox tokens, linked-profile public-name challenges | Deterministic tests and earlier loopback SMTP/browser checks. Mail authentication is not proof of inbox receipt. |
| Collection | LeetCode/GFG public collectors, Codeforces public API, normalization, metadata enrichment and partial-history reporting | Fixture regression and dated public-provider samples; source restrictions remain. |
| Sync coordination | Inline/RQ execution, scheduler, sync claims, cooldowns and provider pacing | Database/queue acceptance recorded in October; representative load is separate. |
| Dashboard | Imported/confirmed unique totals, provider topics/difficulty, activity, freshness, solved search/filter and ten-row pagination | API and earlier frontend browser regression. Missing metadata is not invented. |
| Activity | Saved calendars, UTC timestamp fallback and provider-local source series | The heatmap offers All activity, UTC and source views; reported dates do not establish a common timezone. |
| Matching | Source-identity/exact statement matches, candidate retrieval, Groq/Ollama adapters, traceable decisions | Synthetic diagnostics are available; representative accuracy is not established. |
| Sharing | Candidate-enabled random links, read-only public views, revocation and guarded public photos | Consent checked on reads; downloaded copies cannot be recalled. |
| Extension | Chromium/Firefox packages, scoped connection, question detection, authorized imports and opt-in confirmation tracking | Controlled installed-browser tests; real provider sessions remain a separate acceptance step. |
| Hosting | Container stack, HTTPS overlay, persistent volumes, migration task and health checks | Historical deployment/backup/restore checks, not a new November live-health claim. |
| Privacy | Example-only public configuration, issue-based support, anonymized controlled Git history and publication guard | Reachable-history checks do not purge external forks, clones or cached original commits. |

## Current verification

On **15 November**, the full backend suite passed **211 tests**, extension unit tests passed **17 tests**, and `npm audit --json` reported **0 vulnerabilities**. These were local checks for the documentation review. See [testing](testing.md) for commands, data boundaries and checks not rerun.

The October records separately cover frontend registration/linking/sharing, persistent refresh across a browser restart, responsive pages, profile editing, PostgreSQL/RQ, container HTTP requests and live HTTPS profile smoke checks. Those results keep their original dates. No current production uptime, SMTP inbox delivery or semantic-model accuracy is inferred from them.

## Remaining acceptance, in practical order

### 1. Real accounts and browser behavior

- [ ] Complete owner-authorized LeetCode history imports with a consenting real account and compare available names, dates and source totals.
- [ ] Check opt-in acceptance tracking on real LeetCode/GFG/Codeforces pages, including navigation, reconnect, partial imports and unavailable metadata.
- [ ] Repeat the full Firefox platform alert/history flow; prior Firefox checks covered connection/popup/disconnect.
- [ ] Confirm inbox verification, profile proof and password recovery end to end on the target environment using permitted test recipients. Distinguish delivery acceptance from actual receipt and successful confirmation.
- [ ] Recheck provider access/DOM changes before claiming current live compatibility. Access challenges, private/deleted history and premium statements remain unavailable where unsupported.

Use the [extension guide](browser-extension.md), [account workflows](account-security.md) and [collector guide](public-collectors.md). Never put account cookies, proofs, tokens or personal histories in public reports.

### 2. Persistent extension distribution

- [ ] Set up Mozilla signing and validate the signed Firefox package across browser restart.
- [ ] Recheck extension identity, requested data permissions and exact trusted application origin for the signed release.
- [ ] Decide whether to publish through browser stores; generated development ZIPs/unsigned XPI files are not store releases.

A stable Firefox extension ID alone does not make an unsigned add-on install persistently on normal release Firefox. Chrome/Chromium unpacked installation is documented and does not establish store publication.

### 3. Representative matching evaluation

- [ ] Agree on a labeled dataset with difficult non-duplicates, changed wording, multiple sources and larger candidate histories.
- [ ] Measure candidate retrieval separately from final model decisions, including pairs omitted by the shortlist.
- [ ] Compare actual model/provider settings for false positives, recall, latency, availability and cost.
- [ ] Select a model/threshold using those measurements and check interrupted runs, budgets, caching and quota failures.
- [ ] Record uncertainty and source evidence alongside results; keep synthetic diagnostics separate from independent evaluation data.

The default confidence guard is an engineering setting, not a measured accuracy guarantee. Existing classification and duplicate audits are [dated diagnostics](groq-matching.md), not generalization results. Exact matching remains usable without external inference.

### 4. Operational acceptance

- [ ] Test realistic history sizes, concurrent refresh/sync requests and provider retries under representative failures.
- [ ] Add worker/scheduler liveness and alerting beyond API/database health.
- [ ] Repeat restore exercises as stored history and photos grow; protect off-host backup access and retention.
- [ ] Establish durable email retry/delivery monitoring if background mail tasks are insufficient.
- [ ] Keep one scheduler until multi-instance coordination is implemented and accepted.
- [ ] Recheck actual deployment health and external configuration during a separately authorized operational review.

The source contains sync locks, cooldowns and cross-process request pacing. Their existence does not imply successful load testing or a distributed scheduler. Generic prerequisites are in [deployment](deployment.md); private operational notes are excluded from public source.

### 5. Publication and collaboration hygiene

- [ ] Resolve any remaining external fork/cache copies from the earlier privacy cleanup through their owners/platform review; do not claim full erasure from a clean fresh clone alone.
- [ ] Run current-source, staged-content and reachable-history privacy checks before each publication.
- [ ] Keep operator evidence, environment files, browser state, academic documents and private runbooks outside commits.
- [ ] Keep repository Actions disabled during documentation publication; enabling/running automation is a separate decision.

A CI definition exists, but local verification is not a GitHub run. The current docs update neither enables Actions nor claims new hosted acceptance.

## Scope intentionally deferred

CodeChef, HackerRank, AtCoder, Kaggle and GitHub coding-history connectors remain outside the current enabled set. LeetCode contest statistics are disabled by default, even where contest evidence helps recover solved question names. Automatic topic tagging, visible similarity scores, recommendations, skill-gap analysis, progress prediction, recruiter comparison and team invitations are not established release requirements.

There is no new completion percentage here: completion depends on which acceptance goals are included. The application is implemented and has a deployment history; real-provider/browser, model, distribution and operational acceptance still matter.

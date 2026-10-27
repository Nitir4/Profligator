# Duplicate detection audit — 6 October 2026

Live Groq diagnostics passed **18/18 manually labeled pairs** after fixing one local shortlist miss. The backend regression suite passes **175 tests**.

## Results

Model: `openai/gpt-oss-120b`, configured acceptance threshold: **0.95**. Each of nine equivalent pairs and nine similar-looking non-equivalents was evaluated directly, through the authenticated extension check API and through persisted clustering/dashboard counts.

| Path | Duplicates detected | Non-duplicates rejected | False positives | Missed duplicates |
| --- | --- | --- | --- | --- |
| Direct comparison, including one exact-statement match | 9/9 | 9/9 | 0 | 0 |
| Extension check API | 9/9 | 9/9 | 0 | 0 |
| Saved-history clustering | 9/9 | 9/9 | 0 | 0 |

Detected equivalents include renamed Two Sum, LCS, LIS with different algorithm tags, edit distance, nonadjacent reward selection, grid path cost and subset-sum/0/1 feasibility. The exact-statement case bypasses incompatible tags without inference. Every successful extension result includes a previous-attempt object.

Rejected cases include minimum coins versus number of combinations, subsequence versus substring, 0/1 versus unbounded knapsack, strict versus nondecreasing sequences, sum equals versus divisible, indices versus pair counts, directed versus undirected cycles and uppercase versus lowercase characters. A misleading instruction embedded in problem text did not cause a false duplicate.

## Bug found and fixed

The first run's direct model comparisons passed all cases, but the extension and clustering each recovered only **8/9** duplicates. A renamed edit-distance question with no tags was omitted by local retrieval because singular/plural operation words and replacement/substitution did not share tokens.

The local index now normalizes insertion, deletion/removal and replacement/substitution inflections. The full live diagnostic was rerun and recovered the missing pair. A regression test covers that failure. The eight-candidate and two unknown-family fallback limits remain unchanged.

## Scope and limits

- All pairs are synthetic and manually labeled. These results are a diagnostic smoke test, not a representative production accuracy estimate; the confidence threshold remains uncalibrated.
- Each pair uses a separate synthetic user with one saved target in an isolated temporary SQLite database. The original application database is untouched.
- Direct comparisons happen first; extension and clustering reuse validated cached responses. They verify API/retrieval/storage behavior, not independent repeated inference or cold API latency. The API uses an ASGI test client, not an installed-browser extension session.
- The broader [mixed-history local retrieval audit](classification-audit.md) still recovers 16/17 equivalents. Its sparse untagged edit-distance example lacks informative operation words in the query and remains missed. Fixing this live example does not establish full cross-platform recall.
- No real scraped question corpus was available locally. Evaluate diverse real statements and held-out labels before declaring release accuracy.

[Detailed before/after decisions, confidence, reasons and statuses](verification/duplicates-2026-10-06.json).

## Reproduce

This command uses the configured backend Groq key and consumes provider quota:

```sh
apps/api/.venv/bin/python scripts/verify_groq.py \
  --dataset apps/api/tests/fixtures/duplicate_diagnostics.json \
  --output /tmp/profligator-duplicate-audit.json

apps/api/.venv/bin/python -m pytest -q apps/api/tests
```

The evaluator exits with an error for incorrect decisions or unavailable/unattempted comparisons, and still writes its report. Without `--dataset`, the original Groq application smoke check remains available.

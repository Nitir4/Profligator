# Groq comparison integration

Implemented and live-checked on **6 October 2026**. Groq supplies semantic question comparisons through the existing matching service; scrapers and the browser extension still provide solved identities, statements and date evidence.

## Configure

Put these values in the backend's existing `apps/api/.env`:

```dotenv
PROFLIGATOR_MATCHING_BACKEND=groq
PROFLIGATOR_MATCHING_MODEL=openai/gpt-oss-120b
PROFLIGATOR_GROQ_API_KEY=your-groq-api-key
PROFLIGATOR_GROQ_MIN_INTERVAL_SECONDS=2.1
PROFLIGATOR_GROQ_MAX_COMPLETION_TOKENS=2048
PROFLIGATOR_GROQ_MAX_INPUT_CHARS=16000
```

The key is a masked `SecretStr`, used only in server-side authorization headers. The backend loads `.env`, not `.env.local`. Restart the API, scheduler and any worker after changing configuration. The web app and extension use the existing API response format and need no Groq credentials or rebuild. No new package dependency or database migration is needed.

Groq lists this model among its production models and supports strict JSON schema responses for it. The adapter uses `https://api.groq.com/openai/v1/chat/completions`, temperature zero, low reasoning effort for GPT-OSS, bounded output and the existing `duplicate`, `confidence`, `reason` schema. Schema validation does not establish semantic accuracy. [Groq models](https://console.groq.com/docs/models), [structured outputs](https://console.groq.com/docs/structured-outputs).

The repository example still defaults to `disabled`. `ollama` remains available for local models. The configured local development environment now selects `groq` with `openai/gpt-oss-120b`; the model falls back to that ID only when Groq is selected and no model ID is configured.

## Requests, caching and failures

- Exact statement/source checks run without inference. Semantic comparisons use the existing candidate shortlist and comparison/time budgets.
- Requests contain only problem titles, statements and topics. Account identities, submission code, cookies, source dates and attempt links are excluded from the comparison payload.
- Every response is validated. Refusals, incomplete output, malformed JSON, invalid confidence values, extra fields and HTTP errors produce matching-unavailable results rather than confirmed duplicates.
- Serialized question input exceeding 16,000 characters is unavailable by default. It is never truncated into a potentially misleading comparison. This character budget is not an exact token count.
- Valid comparisons have a bounded 1,024-entry, one-hour in-memory cache. Provider instances in the same event loop share pacing, cached responses and cooldown for the same credential/model. Saved-history comparisons also reuse existing persisted decisions for unchanged inputs/model.
- A 429 starts the provider's `Retry-After` cooldown, or 60 seconds when the header is unavailable. Subsequent requests during that cooldown are not sent. Cached/exact checks still work. Other HTTP failures also start a cooldown; raw response bodies and network exceptions are not propagated to users.
- Failed comparisons preserve imported questions and expose unavailable matching. Future refreshes/checks can retry after cooldown. There is no new durable retry queue; multi-process deployments still need shared quota coordination.

The defaults limit request frequency, input size, output tokens and comparisons per run. They do not guarantee staying inside every account's token/day quota. Groq's organization/model limits and 429 responses remain authoritative. [Groq rate limits](https://console.groq.com/docs/rate-limits).

## Candidate retrieval

The matcher does not send all problem pairs to Groq. Retrieval now runs locally through [`problem_retrieval.py`](../apps/api/src/profligator_api/problem_retrieval.py):

1. Normalize provider aliases such as `dp`, `Dynamic Programming` and `DynamicProgramming`. Keep multiple algorithm labels when supplied or supported by recognizable DP pattern names; a question can use DP and binary search, or DP and graphs.
2. Use an inverted topic/keyword index to retrieve related cross-platform history. Known algorithm buckets with no overlap are excluded. Array/string/tree/grid domains help constrain missing classifications.
3. Narrow known DP patterns: LCS and LIS are distinct, as are explicit 0/1 and unbounded knapsack. Broad knapsack hints remain compatible with narrower variants. Coin change, subset sum, edit distance, grid paths, interval, tree, digit, bitmask and linear DP patterns are also recognized.
4. Rank remaining candidates using normalized informative words and document-frequency weights. A generic DP tag alone is not enough; a compatible recognized subtype or sufficient informative word overlap is needed.
5. Compare at most eight shortlisted candidates by default. Unknown classifications get at most two keyword-related fallbacks within that total. Saved-history matching selects distinct clusters and still validates their members directly, within the existing 64-comparison/run cap.

Exact source/statement matches require no Groq call and bypass topic differences. Classification is cached locally by title/text/tags; changes invalidate those local features. It does not create provider topic tags, change dashboard counts or add a separate LLM classification request. It is a retrieval heuristic: incomplete or misleading tags and renamed patterns can still hide real matches. The bounded unknown fallback reduces that risk without comparing the entire history.

Groq still receives the selected pair's titles, public statements and original topic tags, then returns `duplicate`, `confidence` and `reason`. Full statement requirements, constraints and outputs are needed to distinguish questions within the same technique bucket. Sharing DP or even LCS is candidate evidence, not a confirmed duplicate decision.

Retrieval verification passed **165 backend tests**, including zero provider calls for incompatible buckets, exact-match bypass, DP aliases/subtypes, multi-label matching, bounded unknown fallback, distinct-cluster limits and a shortlist of eight from a synthetic history of 1,000 unrelated graph questions plus 20 DP candidates. These checks verify filtering and call boundaries, not real-world retrieval recall.

The subsequent [local classification audit](classification-audit.md) found and fixed contextual false labels, missing subtype aliases and keyword starvation. It added palindrome-subsequence, decoding, minimum-jump and minimum-path-sum hints and permits subset-sum/0/1-feasibility candidates. The suite now passes **174 tests**. On manually authored development diagnostics, 56/60 full label sets match and 16/17 equivalent pairs are retrieved; those results are not representative production accuracy. An untagged edit-distance paraphrase still misses the shortlist.

The later [live duplicate audit](duplicate-audit.md) passed 18/18 synthetic pairs through direct comparison, the extension API and saved-history clustering after normalizing edit-operation vocabulary. It detected all nine equivalents and rejected all nine near misses. The suite now passes **175 tests**; the sparse mixed-history retrieval miss above remains, and real-world accuracy is still unvalidated.

## Reproduce verification

From the repository root:

```sh
apps/api/.venv/bin/python -m pytest -q apps/api/tests

PYTHONPATH=apps/api/src apps/api/.venv/bin/python -m profligator_api.evaluate_matching \
  --provider groq \
  --dataset apps/api/tests/fixtures/matching_pairs.jsonl \
  --models exact openai/gpt-oss-120b \
  --output /tmp/profligator-groq-smoke.json

apps/api/.venv/bin/python scripts/verify_groq.py
```

The two live commands use the configured key. The application check seeds synthetic questions in a temporary SQLite database and leaves personal history untouched. It verifies semantic clustering, dashboard coverage, an extension semantic response with an original-attempt link, and rejection of a similar pair-count question. It does not install a browser or exercise a live source-platform account.

The six smoke comparisons returned **two true positives, four true negatives, zero false positives, zero false negatives and zero provider errors**, with a mean comparison latency of approximately **1.90 seconds** including pacing. The exact-only baseline missed the paraphrased duplicate. The live application check also passed. Backend verification passed **139 tests**, including protocol, secret masking, caches, quota cooldown, error handling, oversized text, clustering and unknown evaluation results.

The recorded results are in [verification/groq-2026-10-06.json](verification/groq-2026-10-06.json). These small synthetic checks establish integration, not launch accuracy or production capacity. A representative labeled dataset, model comparison, calibrated acceptance criteria and deployed load/worker checks remain outstanding. The confidence threshold of 0.95 remains an engineering setting, not a measured 95% accuracy guarantee.

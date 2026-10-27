# Local classification audit — 6 October 2026

The classifier was checked offline and concrete errors were fixed. The backend suite now passes **174 tests**. No Groq requests were made and the application database was read only.

## What was available locally

`profligator.db` contained **zero saved problem rows** and **zero cached problem metadata records**. The bundled LeetCode/GFG fixtures contained five question titles and topic tags, but no independent classification labels. The existing six-pair dataset labels duplicate decisions, not algorithm classes.

Consequently this audit uses **manually labeled diagnostic examples**: those five fixture titles, synthetic tasks, aliases, ambiguous titles, incidental mentions and alternate formulations. Both sets were inspected while fixing bugs. These results measure regression behavior and coverage on these examples; they are **not an independent holdout or a production accuracy estimate**.

## Results

“All labels correct” means both the expected family set and DP subtype set match exactly. Duplicate retrieval counts an exact match or the expected question appearing among at most eight semantic candidates in a shared distractor history.

| Set | All labels correct, before → after | Equivalent pairs retrieved, before → after | Final family label precision / recall |
| --- | --- | --- | --- |
| Main diagnostics: 44 cases, 57-question history | 27/44 → **42/44** | 7/12 → **12/12** | 100% / 95.6% |
| Additional challenges: 16 cases, 23-question history | 11/16 → **14/16** | 3/5 → **4/5** | 100% / 87.5% |

Across these development sets: **56/60 label sets match (93.3%)**, and **16/17 equivalent pairs are recovered (94.1%)**. There are no extra family/subtype labels on the final examples; four family labels and one subtype label remain missing. All four deliberately incompatible pairs are excluded. All four same-family hard negatives are shortlisted, which is expected: topic classification cannot distinguish differences in output, case sensitivity or graph direction. Groq must still reject those pairs. This audit does not evaluate Groq.

The additional-challenge “before” run occurred after the first diagnostic fixes. It is not the original implementation's baseline. Detailed predictions, candidate IDs and failures are in [the JSON report](verification/classification-2026-10-06.json).

## Changes made

- Separate explicit title/tag hints from body mentions; prefer explicit task evidence over compared alternatives.
- Ignore nearby rejection/example markers, while preserving task mentions followed by negative constraints such as “need not be contiguous.” This remains an English context heuristic.
- Recognize compact DP subtype tags and longer aliases such as `TreeDynamicProgramming` and `DisjointSetUnion`.
- Require a DP tag before interpreting ambiguous “Fibonacci” or “Staircase” names as recurrence DP. Staircase printing and Fibonacci membership no longer add DP labels in the tested examples.
- Add recognizable palindrome-subsequence, decoding, minimum-jump and minimum-path-sum subtype hints. Preserve multiple algorithm labels.
- Allow subset-sum and 0/1-knapsack feasibility candidates to share a selection bucket; keep explicit 0/1 and unbounded variants separate. Sharing a bucket is not proof of equivalence.
- Normalize common action inflections. Exclude words absent from the history index when selecting/scoring query keywords, so irrelevant background vocabulary cannot crowd useful words out of the twelve keyword slots.

The eight-candidate limit, two unknown-family fallbacks, same-platform exclusion and exact-match bypass remain in place. No provider tags were rewritten.

## Remaining failures

Four descriptions without source tags or recognized task names remain unknown: message decoding, nonadjacent warehouse selection, graph reachability and an edit-distance paraphrase. Unknown is an abstention, not a correct classification; the metrics count those missing labels.

One equivalent edit-distance pair is missed because the renamed, untagged description shares too few informative words with the query. This shows the limit of keyword fallback. Real source tags or a separately evaluated semantic retrieval stage could improve recall. Long or unusual example/rejection wording, other languages and conflicting provider tags remain unvalidated.

Before release, export public question fields from real collector/extension history, manually label a diverse cross-platform corpus, and evaluate it without tuning the classifier on the evaluation split. Measure missed equivalents as well as extra labels; a confident but incorrect topic gate can hide a true match.

## Reproduce

Run from the repository root; neither evaluation command reads credentials or calls an API:

```sh
PYTHONPATH=apps/api/src apps/api/.venv/bin/python -m profligator_api.evaluate_retrieval \
  --dataset apps/api/tests/fixtures/retrieval_diagnostics.json \
  --output /tmp/classification-diagnostics.json

PYTHONPATH=apps/api/src apps/api/.venv/bin/python -m profligator_api.evaluate_retrieval \
  --dataset apps/api/tests/fixtures/retrieval_challenges.json \
  --output /tmp/classification-challenges.json

apps/api/.venv/bin/python -m pytest -q apps/api/tests
```

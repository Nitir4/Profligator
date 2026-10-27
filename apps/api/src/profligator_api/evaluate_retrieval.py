"""Offline diagnostic audit of topic hints and bounded candidate retrieval.

Labels are manually authored expectations, not model-generated ground truth.
This evaluates retrieval, not semantic duplicate decisions or Groq accuracy.
"""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from profligator_api.problem_retrieval import CandidateIndex, describe


def problem(key, item, platform):
    return SimpleNamespace(id=key, platform=platform, title=item["title"],
                           statement=item.get("statement"), topics=item.get("topics", []))


def label_metrics(results, field):
    tp = fp = fn = 0
    for row in results:
        expected, actual = set(row["expected"][field]), set(row["actual"][field])
        tp += len(expected & actual)
        fp += len(actual - expected)
        fn += len(expected - actual)
    return {"true_positive_labels": tp, "false_positive_labels": fp,
            "missed_labels": fn, "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None}


def evaluate(dataset, limit=8):
    classified = []
    for item in dataset["classification"]:
        labels = describe(problem(item["id"], item, "leetcode"))
        expected = {field: sorted(item[field]) for field in ("families", "dp_patterns")}
        actual = {field: sorted(getattr(labels, field)) for field in expected}
        classified.append({"id": item["id"], "expected": expected, "actual": actual,
                           "correct": actual == expected})
    # Every query competes against the same fixed background; pairs are not tested
    # in isolation. Exclude title-only examples that cannot be compared semantically.
    background = [problem("background-" + item["id"], item, "codeforces")
                  for item in dataset["classification"] if item.get("statement")]
    targets = [problem("target-" + item["id"], item["target"], "geeksforgeeks")
               for item in dataset["retrieval"]]
    index = CandidateIndex(background + targets)
    retrieved = []
    for item in dataset["retrieval"]:
        query = problem("query-" + item["id"], item["query"], "leetcode")
        exact_ids = [p.id for p in index.exact(query)]
        candidate_ids = [p.id for p in index.candidates(query, limit)]
        target = "target-" + item["id"]
        retrieved.append({"id": item["id"], "relation": item["relation"],
                          "exact": target in exact_ids, "shortlisted": target in candidate_ids,
                          "found": target in exact_ids or target in candidate_ids,
                          "candidate_count": len(candidate_ids), "candidate_ids": candidate_ids})
    positives = [row for row in retrieved if row["relation"] == "duplicate"]
    incompatible = [row for row in retrieved if row["relation"] == "incompatible"]
    hard = [row for row in retrieved if row["relation"] == "hard_negative"]
    correct = sum(row["correct"] for row in classified)
    return {"scope": dataset["scope"], "local_only": True, "provider_calls": 0,
            "classification": {"cases": len(classified), "exact_label_sets": correct,
                "exact_label_set_rate": correct / len(classified),
                "families": label_metrics(classified, "families"),
                "dp_patterns": label_metrics(classified, "dp_patterns"),
                "failures": [row for row in classified if not row["correct"]],
                "results": classified},
            "retrieval": {"history_size": len(background + targets), "limit": limit,
                "duplicate_pairs": len(positives), "duplicates_found": sum(r["found"] for r in positives),
                "recall_at_limit_including_exact": sum(r["found"] for r in positives) / len(positives) if positives else None,
                "missed_duplicates": [r["id"] for r in positives if not r["found"]],
                "incompatible_pairs": len(incompatible),
                "incompatible_pairs_admitted": sum(r["found"] for r in incompatible),
                "hard_negative_pairs": len(hard), "hard_negatives_shortlisted": sum(r["found"] for r in hard),
                "note": "Same-bucket hard negatives can be shortlisted; a semantic comparison must reject them.",
                "results": retrieved}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(json.loads(args.dataset.read_text()))
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output)


if __name__ == "__main__":
    main()

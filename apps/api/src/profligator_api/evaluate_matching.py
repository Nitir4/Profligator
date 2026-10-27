"""Evaluate models on labeled problem pairs before selecting a deployment model."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field

from profligator_api.config import get_settings
from profligator_api.matching import MatchingUnavailable, create_match_provider, normalized_statement


class LabeledPair(BaseModel):
    id: str
    left: dict[str, str]
    right: dict[str, str]
    duplicate: bool


async def evaluate(pairs: list[LabeledPair], provider, threshold: float) -> dict:
    tp = fp = tn = fn = errors = 0
    results = []
    for pair in pairs:
        started = perf_counter()
        error = None
        try:
            if provider is None:
                predicted = bool(normalized_statement(pair.left.get("statement"))) and normalized_statement(pair.left.get("statement")) == normalized_statement(pair.right.get("statement"))
            else:
                decision = await provider.compare(pair.left, pair.right)
                predicted = decision.duplicate and decision.confidence >= threshold
        except MatchingUnavailable as exc:
            errors += 1
            error = str(exc)
            predicted = None
        if predicted is not None:
            tp += predicted and pair.duplicate
            fp += predicted and not pair.duplicate
            tn += not predicted and not pair.duplicate
            fn += not predicted and pair.duplicate
        results.append({"id": pair.id, "expected": pair.duplicate, "predicted": predicted,
                        "latency_seconds": round(perf_counter() - started, 4), "error": error})
    return {
        "model": provider.model if provider else "exact",
        "provider": provider.name if provider else "exact",
        "threshold": threshold,
        "evaluated_pairs": len(pairs) - errors,
        "true_positives": tp, "false_positives": fp, "true_negatives": tn, "false_negatives": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "provider_errors": errors,
        "mean_latency_seconds": sum(item["latency_seconds"] for item in results) / len(results),
        "estimated_cost": None,
        "cost_note": "Supply provider billing or local compute cost separately; no pricing is assumed.",
        "results": results,
    }


async def main_async() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--provider", choices=("ollama", "groq"), default="ollama")
    parser.add_argument("--models", nargs="+", required=True, help="Provider model IDs or 'exact' for the baseline")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    pairs = [LabeledPair.model_validate_json(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    if not pairs:
        parser.error("Dataset must contain at least one labeled pair")
    settings = get_settings()
    reports = []
    for model in args.models:
        provider = None if model == "exact" else create_match_provider(settings.model_copy(
            update={"matching_backend": args.provider, "matching_model": model}))
        reports.append(await evaluate(pairs, provider, settings.matching_min_confidence))
    output = json.dumps(reports, indent=2)
    if args.output:
        args.output.write_text(output + "\n")
    else:
        print(output)
    if any(report["provider_errors"] for report in reports):
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main_async())

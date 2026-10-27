"""Live duplicate diagnostics through the provider, extension API and clustering."""

import json
from pathlib import Path
import tempfile
from time import perf_counter

import httpx

from profligator_api.config import get_settings
from profligator_api.connectors.base import payload_checksum
from profligator_api.main import create_app
from profligator_api.matching import MatchingService, MatchingUnavailable, Problem
from profligator_api.problem_retrieval import CandidateIndex
from profligator_api.repository import Repository
from profligator_api.schemas import CanonicalProfile, ConnectorMode, NormalizedRecord


def metrics(rows, field):
    evaluated = [row for row in rows if row.get(field) is not None]
    tp = sum(row["expected"] and row[field] for row in evaluated)
    fp = sum(not row["expected"] and row[field] for row in evaluated)
    fn = sum(row["expected"] and not row[field] for row in evaluated)
    tn = sum(not row["expected"] and not row[field] for row in evaluated)
    return {"evaluated": len(evaluated), "true_positives": tp, "false_positives": fp,
            "false_negatives": fn, "true_negatives": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None}


async def run_duplicate_audit(dataset_path: Path, output: Path):
    dataset = json.loads(dataset_path.read_text())
    rows = []
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="profligator-duplicates-") as temporary:
        config = settings.model_copy(update={
            "database_url": f"sqlite:///{temporary}/audit.db", "auto_create_schema": True,
            "matching_backend": "groq", "matching_model": settings.matching_model or "openai/gpt-oss-120b",
            "leetcode_connector": "fixture", "geeksforgeeks_connector": "fixture",
        })
        app = create_app(config)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                for number, pair in enumerate(dataset["pairs"], 1):
                    started = perf_counter()
                    registration = await client.post("/api/v1/auth/register", json={
                        "email": f"duplicate-{number}@example.com", "handle": f"duplicate_{number}",
                        "password": "SyntheticDiagnostic2026!",
                    })
                    registration.raise_for_status()
                    user_id = (await client.get("/api/v1/auth/me")).json()["id"]

                    def save(repository, platform, content):
                        host = "www.geeksforgeeks.org" if platform == "geeksforgeeks" else "leetcode.com"
                        profile = repository.save_profile(user_id, CanonicalProfile(platform=platform,
                            handle=f"duplicate_{number}", canonical_url=f"https://{host}/u/duplicate_{number}/"),
                            ConnectorMode.FIXTURE, live_data=False)
                        repository.upsert_records(profile.id, [NormalizedRecord(platform=platform,
                            source_id=f"diagnostic-{number}", kind="problem", status="solved",
                            canonical_url=f"https://{host}/problems/diagnostic-{number}/",
                            source_payload_checksum=payload_checksum(content), **content)])

                    with app.state.database.session() as session:
                        save(Repository(session), "geeksforgeeks", pair["right"])
                    matcher = MatchingService(app.state.database, config)
                    saved = matcher.history(user_id)[0]
                    query = Problem("opened", "leetcode", **pair["left"])
                    index = CandidateIndex([saved])
                    eligible = bool(index.exact(query) or index.candidates(query, config.matching_candidate_limit))
                    row = {"id": pair["id"], "expected": pair["duplicate"], "retrieved": eligible}
                    try:
                        # Direct comparison diagnoses model errors independently of retrieval.
                        # Successful responses are reused by the normal provider cache below.
                        decision, provider = await matcher.compare(query, saved, persist=False)
                    except MatchingUnavailable as exc:
                        row.update(error=str(exc), direct=None, extension=None, clustering=None)
                        rows.append(row)
                        print(json.dumps({"id": pair["id"], "error": str(exc)}), flush=True)
                        break  # Do not consume quota or repeatedly hit a provider cooldown.
                    row.update(direct=decision.duplicate and decision.confidence >= config.matching_min_confidence,
                               confidence=decision.confidence, reason=decision.reason, provider=provider)
                    checked = await client.post("/api/v1/extension/check", json={
                        "platform": "leetcode", "source_id": f"diagnostic-{number}",
                        "canonical_url": f"https://leetcode.com/problems/diagnostic-{number}/", **pair["left"],
                    })
                    checked.raise_for_status()
                    check = checked.json()
                    row.update(extension=None if check["status"] == "matching_unavailable" else check["duplicate"],
                               extension_status=check["status"],
                               previous_attempt_present=bool(check.get("previous_attempt")))
                    with app.state.database.session() as session:
                        save(Repository(session), "leetcode", pair["left"])
                    match_status = await MatchingService(app.state.database, config).match_user(user_id)
                    dashboard = (await client.get("/api/v1/dashboard")).json()
                    row.update(clustering=None if match_status == "unavailable" else dashboard["unique_problems_solved"] == 1,
                               clustering_status=match_status, unique_questions=dashboard["unique_problems_solved"],
                               latency_seconds=round(perf_counter() - started, 3))
                    rows.append(row)
                    print(json.dumps({k: row[k] for k in ("id", "expected", "direct", "extension", "clustering")}), flush=True)

    report = {"scope": dataset["scope"], "provider": "groq", "model": config.matching_model,
              "threshold": config.matching_min_confidence, "planned_pairs": len(dataset["pairs"]),
              "attempted_pairs": len(rows), "unattempted_pairs": len(dataset["pairs"]) - len(rows),
              "application_data": "Isolated temporary SQLite; original application data untouched.",
              "test_order": "Direct comparison first; extension and clustering reuse cached pair responses. Their results test application behavior, not independent inference runs.",
              "history_note": "Each pair has its own user and one saved target; mixed-history retrieval was evaluated separately in the local classification audit.",
              "launch_accuracy_validated": False,
              "direct": metrics(rows, "direct"), "extension": metrics(rows, "extension"),
              "clustering": metrics(rows, "clustering"), "results": rows}
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}), flush=True)
    if report["unattempted_pairs"] or any(row.get(field) is None for row in rows for field in ("direct", "extension", "clustering")):
        raise SystemExit(2)
    if any(row[field] != row["expected"] for row in rows for field in ("direct", "extension", "clustering")):
        raise SystemExit(1)

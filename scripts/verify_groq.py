#!/usr/bin/env python3
"""Live Groq application check using synthetic questions and an isolated database."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from profligator_api.config import get_settings
from profligator_api.main import create_app
from profligator_api.matching import MatchingService
from profligator_api.repository import Repository
from profligator_api.schemas import CanonicalProfile, ConnectorMode, NormalizedRecord


async def run(output: Path):
    with tempfile.TemporaryDirectory(prefix="profligator-groq-check-") as temporary:
        config = get_settings().model_copy(update={
            "database_url": f"sqlite:///{temporary}/check.db", "auto_create_schema": True,
            "matching_backend": "groq", "matching_model": get_settings().matching_model or "openai/gpt-oss-120b",
            "leetcode_connector": "fixture", "geeksforgeeks_connector": "fixture",
        })
        app = create_app(config)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                registration = await client.post("/api/v1/auth/register", json={
                    "email": "groq-check@example.com", "handle": "groq_check", "password": "SyntheticCheck2026!",
                })
                assert registration.status_code == 201
                user_id = (await client.get("/api/v1/auth/me")).json()["id"]
                statements = [
                    "Given an integer array and target K, return two distinct indices whose values sum to K. There is exactly one valid pair.",
                    "An integer list contains exactly one pair of different positions adding up to a supplied target. Output those two positions.",
                ]
                with app.state.database.session() as session:
                    repository = Repository(session)
                    for index, platform in enumerate(("leetcode", "geeksforgeeks")):
                        host = "leetcode.com" if index == 0 else "www.geeksforgeeks.org"
                        profile = repository.save_profile(user_id, CanonicalProfile(platform=platform, handle="synthetic_user",
                            canonical_url=f"https://{host}/u/synthetic_user/"), ConnectorMode.FIXTURE, live_data=False)
                        repository.upsert_records(profile.id, [NormalizedRecord(platform=platform, source_id=f"synthetic-{index}",
                            kind="problem", status="solved", title="Pair Search", canonical_url=f"https://{host}/problems/synthetic-{index}/",
                            statement=statements[index], topics=["Array"], source_payload_checksum=f"synthetic-{index}")])
                status = await MatchingService(app.state.database, config).match_user(user_id)
                assert status == "complete", f"Live matching status: {status}"
                dashboard = (await client.get("/api/v1/dashboard")).json()
                assert dashboard["semantic_matching"] == "enabled"
                assert dashboard["total_problems_solved"] == 2 and dashboard["unique_problems_solved"] == 1
                assert dashboard["semantic_matched_records"] == 2
                semantic = await client.post("/api/v1/extension/check", json={
                    "platform": "codeforces", "source_id": "4-A", "title": "Locate Two Positions",
                    "canonical_url": "https://codeforces.com/problemset/problem/4/A",
                    "statement": "For an integer array and a target value, output the indices of two different elements whose sum is the target. Exactly one such pair exists.",
                    "topics": ["Array"],
                })
                assert semantic.status_code == 200 and semantic.json()["status"] == "semantic", semantic.json()["status"]
                assert semantic.json()["previous_attempt"]["record_id"]
                assert "similarity_score" not in semantic.json()
                unrelated = await client.post("/api/v1/extension/check", json={
                    "platform": "codeforces", "source_id": "4-B", "title": "Pair Search",
                    "canonical_url": "https://codeforces.com/problemset/problem/4/B",
                    "statement": "Given an integer array and target K, count all unordered pairs of different indices whose values sum to K, including duplicates.",
                    "topics": ["Array"],
                })
                assert unrelated.status_code == 200 and unrelated.json()["status"] == "no_confirmed_match", unrelated.json()["status"]
                assert unrelated.json()["duplicate"] is False
                result = {"passed": True, "provider": "groq", "model": config.matching_model,
                    "data": "synthetic questions in an isolated temporary SQLite database",
                    "checks": ["semantic clustering", "dashboard matching coverage", "semantic extension response with original-attempt link",
                               "similar topic with different output rejected", "no similarity score exposed"],
                    "launch_accuracy_validated": False}
                output.write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/profligator-groq-application.json"))
    parser.add_argument("--dataset", type=Path, help="Run the broader labeled duplicate audit instead of the original smoke check")
    args = parser.parse_args()
    if args.dataset:
        from profligator_api.evaluate_duplicates import run_duplicate_audit
        asyncio.run(run_duplicate_audit(args.dataset, args.output))
    else:
        asyncio.run(run(args.output))

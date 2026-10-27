from datetime import UTC, datetime
import json

import httpx
import pytest
from sqlalchemy import select

from profligator_api.connectors.geeksforgeeks import GeeksForGeeksConnector
from profligator_api.connectors.leetcode import LeetCodeConnector
from profligator_api.connectors.metadata import DatabaseMetadataStore
from profligator_api.database import Database
from profligator_api.enrichment import enrich_profile
from profligator_api.models import CodingRecord, ProblemMetadata
from profligator_api.repository import Repository
from profligator_api.schemas import CanonicalProfile, ConnectorMode, NormalizedRecord
from test_extension_history import browser_payload, link, token_headers
from test_public_collectors import gfg_problem_html, lc_data


def seed(database, platform):
    with database.session() as session:
        repository = Repository(session)
        user = repository.create_user(email="history@example.com", handle="history", password_hash="test")
        profile = repository.save_profile(user.id, CanonicalProfile(platform=platform, handle="public_user",
            canonical_url="https://leetcode.com/u/public_user/" if platform == "leetcode"
            else "https://www.geeksforgeeks.org/profile/public_user"), ConnectorMode.SCRAPER, live_data=True)
        records = [NormalizedRecord(platform=platform, source_id=f"pair-{i}", kind="problem", status="solved",
            title=f"History {i}", canonical_url=f"https://leetcode.com/problems/pair-{i}/" if platform == "leetcode"
            else f"https://www.geeksforgeeks.org/problems/pair-{i}/1",
            occurred_at=datetime(2025, 1, 1, tzinfo=UTC) if platform == "leetcode" else None,
            source_solved_at="2025-01-01T08:00:00" if platform == "geeksforgeeks" else None,
            submission_url=f"https://leetcode.com/submissions/detail/{i+1}/" if platform == "leetcode" else None,
            source_payload_checksum=f"owner-{i}") for i in range(3)]
        repository.upsert_records(profile.id, records)
        return profile.id


def collector(database, platform, calls, fail=None):
    def handler(request):
        # Enrichment must never request public recent submissions or another account's history.
        if platform == "leetcode":
            body = json.loads(request.content)
            assert set(body["variables"]) == {"titleSlug"}
            key = body["variables"]["titleSlug"]
        else:
            assert request.method == "GET" and "/problems/" in request.url.path
            key = request.url.path.split("/")[2]
        calls.append(key)
        if key == fail:
            return httpx.Response(403)
        if platform == "leetcode":
            return httpx.Response(200, json={"data": {"question": {"titleSlug": key, "title": f"Public {key}",
                "content": "<p>Find a pair.</p>", "difficulty": "Easy", "isPaidOnly": False,
                "topicTags": [{"name": "Array"}]}}})
        return httpx.Response(200, text=gfg_problem_html(key))
    cls = LeetCodeConnector if platform == "leetcode" else GeeksForGeeksConnector
    return cls(0, 0, transport=httpx.MockTransport(handler), metadata_store=DatabaseMetadataStore(database))


@pytest.mark.parametrize("platform", ["leetcode", "geeksforgeeks"])
async def test_saved_history_enrichment_resumes_without_public_solve_list(tmp_path, platform):
    url = f"sqlite:///{tmp_path / 'history.db'}"
    database = Database(url)
    database.initialize()
    profile_id = seed(database, platform)
    database.dispose()
    calls = []
    for expected in (1, 2, 3, 3):
        database = Database(url)
        result = await enrich_profile(database, profile_id, collector(database, platform, calls), 1)
        assert result["enrichment_status"] == "succeeded"
        with database.session() as session:
            rows = list(session.scalars(select(CodingRecord)))
            assert len(rows) == 3 and sum(bool(row.statement) for row in rows) == expected
            assert len(list(session.scalars(select(ProblemMetadata)))) == expected
            if platform == "leetcode":
                assert all(row.occurred_at.year == 2025 and row.submission_url.endswith(f"/{int(row.source_id[-1]) + 1}/") for row in rows)
            else:
                assert all(row.occurred_at is None and row.source_solved_at == "2025-01-01T08:00:00" for row in rows)
        database.dispose()
    assert calls == ["pair-0", "pair-1", "pair-2"]


async def test_metadata_denial_keeps_history_and_successful_checks(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'denied.db'}")
    database.initialize()
    profile_id = seed(database, "leetcode")
    calls = []
    result = await enrich_profile(database, profile_id, collector(database, "leetcode", calls, fail="pair-1"), 3)
    assert result["enrichment_status"] == "partial" and result["enrichment_error"] == "provider_access_denied"
    assert calls == ["pair-0", "pair-1"]  # No further provider requests after denial.
    with database.session() as session:
        rows = list(session.scalars(select(CodingRecord)))
        assert len(rows) == 3 and sum(bool(row.statement) for row in rows) == 1
        assert all(row.occurred_at.year == 2025 for row in rows)
    database.dispose()


async def test_browser_import_enriches_saved_names_with_one_budget(client, monkeypatch):
    from profligator_api.connectors.registry import ConnectorRegistry

    profile = await link(client)
    headers = await token_headers(client)
    database = client._transport.app.state.database
    client._transport.app.state.settings.scraper_statement_limit = 1
    calls = []
    monkeypatch.setattr(ConnectorRegistry, "get", lambda *args: collector(database, "leetcode", calls))
    result = await client.post("/api/v1/extension/history/browser", headers=headers,
                               json=browser_payload(profile, final_batch=True))
    assert result.status_code == 200, result.text
    assert result.json()["questions_with_statements"] == 1
    assert result.json()["timestamped_questions"] == 1
    result = await client.post("/api/v1/extension/history/browser", headers=headers,
                               json=browser_payload(profile, final_batch=True))
    assert result.json()["questions_with_statements"] == 2
    assert set(calls) == {"two-sum", "add-two-numbers"} and len(calls) == 2
    result = await client.post("/api/v1/extension/history/browser", headers=headers,
                               json=browser_payload(profile, questions=[], final_batch=True))
    assert result.json()["metadata_records_written"] == 0 and result.json()["questions"] == 2
    assert len(calls) == 2


async def test_regular_sync_enriches_browser_questions_absent_from_public_history(client, monkeypatch):
    from profligator_api.connectors.registry import ConnectorRegistry

    profile = await link(client)
    headers = await token_headers(client)
    database = client._transport.app.state.database
    client._transport.app.state.settings.scraper_statement_limit = 1
    await client.post("/api/v1/extension/history/browser", headers=headers, json=browser_payload(profile))
    calls = []
    def handler(request):
        body = json.loads(request.content)
        if "titleSlug" not in body["variables"]:
            data = lc_data(total=2)
            data["matchedUser"]["username"] = "sample_user"
            data["recentAcSubmissionList"] = []
            data["userContestRankingHistory"] = []
            return httpx.Response(200, json={"data": data})
        key = body["variables"]["titleSlug"]
        calls.append(key)
        return httpx.Response(200, json={"data": {"question": {"titleSlug": key, "title": key,
            "content": "<p>Public statement.</p>", "difficulty": "Easy", "isPaidOnly": False, "topicTags": []}}})
    monkeypatch.setattr(ConnectorRegistry, "get", lambda *args: LeetCodeConnector(0, 0,
        transport=httpx.MockTransport(handler), metadata_store=DatabaseMetadataStore(database), calendar_year_limit=1))
    for expected in (1, 2, 2):
        response = await client.post("/api/v1/syncs", json={"platform_profile_id": profile["id"]})
        assert response.json()["status"] == "succeeded", response.text
        questions = (await client.get("/api/v1/solved-problems")).json()["items"]
        assert len(questions) == 2
        with database.session() as session:
            assert sum(bool(row.statement) for row in session.scalars(select(CodingRecord))) == expected
    assert len(calls) == 2


async def test_revocation_during_metadata_collection_prevents_record_enrichment(client, monkeypatch):
    from profligator_api.connectors.registry import ConnectorRegistry

    profile = await link(client)
    headers = await token_headers(client)
    database = client._transport.app.state.database
    connector = collector(database, "leetcode", [])
    original = connector.enrich_records
    async def revoke(records, limit):
        updates = await original(records, limit)
        assert (await client.delete("/api/v1/extension/session", headers=headers)).status_code == 204
        return updates
    connector.enrich_records = revoke
    monkeypatch.setattr(ConnectorRegistry, "get", lambda *args: connector)
    response = await client.post("/api/v1/extension/history/browser", headers=headers,
                                 json=browser_payload(profile, final_batch=True))
    assert response.status_code == 401
    questions = (await client.get("/api/v1/solved-problems")).json()["items"]
    assert len(questions) == 2
    with database.session() as session:
        assert all(row.statement is None for row in session.scalars(select(CodingRecord)))


async def test_metadata_cannot_restore_stale_acceptance_evidence(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'concurrent.db'}")
    database.initialize()
    profile_id = seed(database, "leetcode")
    connector = collector(database, "leetcode", [])
    original = connector.enrich_records
    async def earlier_acceptance(records, limit):
        updates = await original(records, limit)
        with database.session() as session:
            row = session.scalar(select(CodingRecord).where(CodingRecord.source_id == "pair-0"))
            row.occurred_at = datetime(2024, 1, 1, tzinfo=UTC)
            row.submission_url = "https://leetcode.com/submissions/detail/999/"
        return updates
    connector.enrich_records = earlier_acceptance
    await enrich_profile(database, profile_id, connector, 1)
    with database.session() as session:
        row = session.scalar(select(CodingRecord).where(CodingRecord.source_id == "pair-0"))
        assert row.statement and row.occurred_at.year == 2024 and row.submission_url.endswith("/999/")
    database.dispose()

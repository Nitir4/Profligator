from datetime import UTC, datetime, timedelta

import httpx
import pytest

from profligator_api.connectors.base import ConnectorError
from profligator_api.connectors.registry import ConnectorRegistry
from profligator_api.models import CodingRecord
from profligator_api.repository import Repository
from profligator_api.schemas import ConnectorPage, NormalizedRecord, ProfileSnapshot
from test_extension_auth import grant


async def link(client, platform="leetcode", handle="sample_user"):
    response = await client.post("/api/v1/platform-profiles", json={"platform": platform, "handle_or_url": handle})
    assert response.status_code == 201, response.text
    return response.json()


async def token_headers(client):
    issued = await grant(client)
    return {"Authorization": f"Bearer {issued['token']}"}


def browser_payload(profile, **values):
    return {"profile_id": profile["id"], "handle": profile["public_handle"], "source_total_solved": 2,
            "questions": [{"source_id": "two-sum", "title": "Two Sum", "solved_at": "2025-01-01T08:00:00Z", "submission_id": "123"},
                          {"source_id": "add-two-numbers", "title": "Add Two Numbers"}], **values}


async def test_browser_history_names_dates_idempotence_and_sharing(client):
    profile = await link(client)
    headers = await token_headers(client)
    result = await client.post("/api/v1/extension/history/browser", headers=headers, json=browser_payload(profile, final_batch=True))
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["questions"] == 2
    assert result.json()["timestamped_questions"] == 1
    assert result.json()["history_complete"] is True
    assert (await client.post("/api/v1/extension/history/browser", headers=headers, json=browser_payload(profile))).json()["records_written"] == 0
    later = browser_payload(profile)
    later["questions"][0]["solved_at"] = "2026-01-01T08:00:00Z"
    later["questions"][0]["submission_id"] = "456"
    await client.post("/api/v1/extension/history/browser", headers=headers, json=later)
    listed = (await client.get("/api/v1/solved-problems")).json()["items"]
    first = next(row for row in listed if row["source_id"] == "two-sum")
    assert first["solved_at"] == "2025-01-01T08:00:00Z"
    assert first["submission_url"] == "https://leetcode.com/submissions/detail/123/"
    assert next(row for row in listed if row["source_id"] == "add-two-numbers")["solved_at"] is None
    sharing = (await client.put("/api/v1/sharing", json={"enabled": True})).json()
    share_token = sharing["shareable_link"].rsplit("/", 1)[-1]
    assert (await client.get(f"/api/v1/public-profiles/{share_token}/solved-problems")).json()["total"] == 2
    assert (await client.get("/api/v1/platform-profiles")).json()[0]["verification_state"] != "verified"


async def test_history_scope_account_identity_disconnection_and_revocation(client):
    profile = await link(client)
    headers = await token_headers(client)
    assert (await client.get("/api/v1/extension/history/profiles")).status_code == 401
    profiles = await client.get("/api/v1/extension/history/profiles", headers=headers)
    assert profiles.json()[0]["import_method"] == "browser_session"
    assert (await client.post("/api/v1/extension/history/browser", headers=headers,
                              json=browser_payload(profile, handle="other"))).status_code == 422
    assert (await client.post("/api/v1/extension/history/provider", headers=headers,
                              json={"profile_id": profile["id"]})).status_code == 422
    await client.post("/api/v1/auth/register", json={"email": "other-history@example.com", "handle": "otherhistory", "password": "OtherHistoryPassword!"})
    other = await link(client, handle="SomeoneElse")
    assert (await client.post("/api/v1/extension/history/browser", headers=headers, json=browser_payload(other))).status_code == 404
    assert (await client.get("/api/v1/extension/history/profiles", headers=headers)).json()[0]["handle"] == "sample_user"
    await client.delete("/api/v1/extension/session", headers=headers)
    assert (await client.post("/api/v1/extension/history/browser", headers=headers, json=browser_payload(profile))).status_code == 401


@pytest.mark.parametrize("extra", [
    {"solved_at": "2025-01-01T08:00:00"},
    {"solved_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    {"source_id": "../two-sum"}, {"submission_id": "https://evil.test"}, {"title": " "},
    {"code": "private code"}, {"cookies": "private session"},
])
async def test_browser_import_rejects_unknown_dates_urls_and_private_payloads(client, extra):
    profile = await link(client)
    headers = await token_headers(client)
    payload = browser_payload(profile)
    payload["questions"][0].update(extra)
    assert (await client.post("/api/v1/extension/history/browser", headers=headers, json=payload)).status_code == 422
    assert (await client.get("/api/v1/solved-problems")).json()["total"] == 0


@pytest.mark.parametrize("platform,source_id,url,local_date", [
    ("geeksforgeeks", "sum-of-two-numbers0000", "https://www.geeksforgeeks.org/problems/sum-of-two-numbers0000/1", "2025-01-01T08:00:00"),
    ("codeforces", "100-A", "https://codeforces.com/problemset/problem/100/A", None),
])
async def test_provider_import_and_acceptance_capture_for_other_sites(client, monkeypatch, platform, source_id, url, local_date):
    profile = await link(client, platform, "extension_test")
    headers = await token_headers(client)
    class Provider:
        async def fetch_profile(self, canonical):
            return ProfileSnapshot(profile=canonical, fetched_at=datetime.now(UTC), source_total_solved=1, history_complete=True)
        async def fetch_solved_records(self, canonical, cursor=None):
            return ConnectorPage(records=[NormalizedRecord(platform=platform, source_id=source_id, kind="problem", status="solved",
                title="Provider Question", canonical_url=url, source_solved_at=local_date,
                occurred_at=None if local_date else datetime(2025, 1, 1, 8, tzinfo=UTC), source_payload_checksum="provider-acceptance")])
        async def fetch_contests(self, *args):
            raise AssertionError("Question imports must not request contests")
    monkeypatch.setattr(ConnectorRegistry, "get", lambda *args: Provider())
    result = await client.post("/api/v1/extension/history/provider", headers=headers, json={"profile_id": profile["id"]})
    assert result.status_code == 200, result.text
    assert result.json()["questions"] == 1
    assert result.json()["history_complete"] is True
    assert result.json()["timestamped_questions"] == (0 if local_date else 1)
    assert result.json()["source_local_question_times"] == (1 if local_date else 0)
    captured = await client.post("/api/v1/extension/history/provider", headers=headers,
                                 json={"profile_id": profile["id"], "source_id": source_id})
    assert captured.json()["status"] == "succeeded"
    assert captured.json()["records_written"] == 0
    absent = await client.post("/api/v1/extension/history/provider", headers=headers,
                               json={"profile_id": profile["id"], "source_id": "999-A" if platform == "codeforces" else "not-solved"})
    assert absent.json()["status"] == "not_found"
    assert absent.json()["questions"] == 1
    class Failed(Provider):
        async def fetch_profile(self, canonical):
            raise ConnectorError("rate_limited", "Provider unavailable")
    monkeypatch.setattr(ConnectorRegistry, "get", lambda *args: Failed())
    assert (await client.post("/api/v1/extension/history/provider", headers=headers,
                              json={"profile_id": profile["id"]})).status_code == 502
    assert (await client.get("/api/v1/solved-problems")).json()["total"] == 1


async def test_import_preserves_richer_metadata_and_disconnected_profile(client):
    profile = await link(client)
    headers = await token_headers(client)
    database = client._transport.app.state.database
    with database.session() as session:
        repository = Repository(session)
        repository.upsert_records(profile["id"], [NormalizedRecord(platform="leetcode", source_id="two-sum", kind="problem",
            status="solved", title="Two Sum", canonical_url="https://leetcode.com/problems/two-sum/", difficulty="Easy",
            topics=["Array"], statement="Find a pair with the target sum.", source_payload_checksum="richer")])
    await client.post("/api/v1/extension/history/browser", headers=headers, json=browser_payload(profile))
    with database.session() as session:
        record = session.query(CodingRecord).filter_by(source_id="two-sum").one()
        assert record.statement == "Find a pair with the target sum."
        assert record.difficulty == "Easy" and record.topics == ["Array"]
    await client.delete(f"/api/v1/platform-profiles/{profile['id']}")
    assert (await client.post("/api/v1/extension/history/browser", headers=headers, json=browser_payload(profile))).status_code == 404

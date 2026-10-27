from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import func, select

from profligator_api.config import Settings
from profligator_api.connectors.base import payload_checksum
from profligator_api.database import Database
from profligator_api.matching import MatchResult, MatchingService, MatchingUnavailable, OllamaMatchProvider
from profligator_api.models import CodingRecord, MatchDecision, PlatformProfile, SyncRun
from profligator_api.repository import Repository
from profligator_api.scheduler import sync_due_profiles
from profligator_api.schemas import CanonicalProfile, ConnectorMode, DuplicateCheckRequest, NormalizedRecord, Platform


def seed(database: Database, *, statements: tuple[str | None, str | None] = ("Find a pair of distinct indices whose values sum to K.", "Find a pair of distinct indices whose values sum to K.")) -> tuple[str, list[str]]:
    with database.session() as session:
        repository = Repository(session)
        user = repository.get_user_by_email("alex@example.com") or repository.create_user(email="alex@example.com", handle="alex_dev96", password_hash="test-only")
        profiles = []
        for index, platform in enumerate((Platform.LEETCODE, Platform.GEEKSFORGEEKS)):
            host = "leetcode.com" if platform == Platform.LEETCODE else "geeksforgeeks.org"
            profile = repository.save_profile(user.id, CanonicalProfile(platform=platform, handle="fixture_user", canonical_url=f"https://{host}/u/fixture_user"), ConnectorMode.FIXTURE, live_data=False)
            profiles.append(profile.id)
            repository.upsert_records(profile.id, [NormalizedRecord(
                platform=platform, source_id=str(index), kind="problem", status="solved",
                title="Pair Sum" if index == 0 else "Find Two Values",
                canonical_url=f"https://{host}/problems/pair-sum/",
                statement=statements[index], topics=["Array"], difficulty="Easy",
                submission_url=f"https://{host}/submissions/{index}",
                occurred_at=datetime(2024, 1, 1 + index, tzinfo=UTC),
                source_payload_checksum=payload_checksum({"statement": statements[index]}),
            )])
        return user.id, profiles


def request(statement: str | None = "Find a pair of distinct indices whose values sum to K.") -> DuplicateCheckRequest:
    return DuplicateCheckRequest(platform="codeforces", source_id="100-A", title="Two numbers", canonical_url="https://codeforces.com/problemset/problem/100/A", statement=statement)


async def test_confirmed_clusters_dashboard_extension_and_disconnect(client: httpx.AsyncClient) -> None:
    app = client._transport.app
    database = app.state.database
    user_id, profiles = seed(database)
    matcher = MatchingService(database, app.state.settings)
    assert await matcher.match_user(user_id) == "exact_only"
    data = (await client.get("/api/v1/dashboard")).json()
    assert data["total_problems_solved"] == 2
    assert data["unique_problems_solved"] == 1
    assert data["matched_records"] == 2
    clusters = (await client.get("/api/v1/unique-clusters")).json()
    assert len(clusters) == 1
    assert len(clusters[0]["records"]) == 2
    checked = (await client.post("/api/v1/extension/check", json=request().model_dump())).json()
    assert checked["duplicate"] is True
    assert checked["previous_attempt"]["submission_url"] == "https://leetcode.com/submissions/0"
    assert "similarity_score" not in checked
    assert await matcher.match_user(user_id) == "exact_only"
    with database.session() as session:
        assert session.scalar(select(func.count(MatchDecision.id))) == 1
    assert (await client.delete(f"/api/v1/platform-profiles/{profiles[0]}")).status_code == 204
    after = (await client.get("/api/v1/unique-clusters")).json()
    assert len(after[0]["records"]) == 1


async def test_shared_profiles_require_consent_and_revocation(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/sharing")).json() == {"enabled": False, "shareable_link": None}
    enabled = (await client.put("/api/v1/sharing", json={"enabled": True})).json()
    token = enabled["shareable_link"].rsplit("/", 1)[1]
    await client.post("/api/v1/auth/logout")
    public = await client.get(f"/api/v1/public-profiles/{token}")
    assert public.status_code == 200
    assert public.headers["cache-control"] == "no-store"
    assert public.json()["handle"] == "alex_dev96"
    assert "email" not in public.json()
    assert (await client.put("/api/v1/sharing", json={"enabled": False})).status_code == 401
    await client.post("/api/v1/auth/login", json={"email": "alex@example.com", "password": "correct-horse-battery-staple"})
    assert (await client.put("/api/v1/sharing", json={"enabled": False})).status_code == 200
    assert (await client.get(f"/api/v1/public-profiles/{token}")).status_code == 404
    new_link = (await client.put("/api/v1/sharing", json={"enabled": True})).json()["shareable_link"]
    assert not new_link.endswith(token)
    assert (await client.get("/api/v1/public-profiles/alex_dev96")).status_code == 404


async def test_roles_and_candidate_history_are_isolated(client: httpx.AsyncClient) -> None:
    database = client._transport.app.state.database
    seed(database)
    await client.post("/api/v1/auth/logout")
    recruiter = await client.post("/api/v1/auth/register", json={"email": "recruiter@example.com", "handle": "recruiter", "password": "correct-horse-battery-staple", "role": "recruiter"})
    assert recruiter.status_code == 201
    for path in ("/api/v1/dashboard", "/api/v1/platform-profiles", "/api/v1/coding-records", "/api/v1/unique-clusters", "/api/v1/sharing"):
        assert (await client.get(path)).status_code == 403
    assert (await client.post("/api/v1/extension/check", json=request().model_dump())).status_code == 403
    await client.post("/api/v1/auth/logout")
    await client.post("/api/v1/auth/register", json={"email": "second@example.com", "handle": "second_user", "password": "correct-horse-battery-staple"})
    assert (await client.get("/api/v1/coding-records")).json() == []
    assert (await client.get("/api/v1/unique-clusters")).json() == []
    assert (await client.post("/api/v1/extension/check", json=request().model_dump())).json()["duplicate"] is False


async def test_titles_alone_do_not_merge_and_unsafe_urls_are_rejected(client: httpx.AsyncClient) -> None:
    app = client._transport.app
    user_id, _ = seed(app.state.database, statements=(None, None))
    with app.state.database.session() as session:
        for record in session.scalars(select(CodingRecord)):
            record.title = "Same title"
    await MatchingService(app.state.database, app.state.settings).match_user(user_id)
    assert (await client.get("/api/v1/dashboard")).json()["unique_problems_solved"] == 2
    result = (await client.post("/api/v1/extension/check", json=request(None).model_dump())).json()
    assert result == {"duplicate": False, "status": "insufficient_data", "previous_attempt": None}
    assert (await client.post("/api/v1/extension/check", json={**request().model_dump(), "canonical_url": "javascript:alert(1)"})).status_code == 422
    assert (await client.post("/api/v1/extension/check", json={**request().model_dump(), "canonical_url": "https://example.com/problem"})).status_code == 422


async def test_semantic_matching_confidence_failure_and_cache(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'matching.db'}")
    database = Database(settings.database_url)
    database.initialize()
    user_id, _ = seed(database, statements=("Find two indices with sum K.", "Return indices of two array elements whose total equals a target."))

    class Provider:
        name = "test"
        model = "test-model"
        calls = 0
        confidence = 0.8
        fail = False

        async def compare(self, left: dict, right: dict) -> MatchResult:
            self.calls += 1
            if self.fail:
                raise MatchingUnavailable("offline")
            return MatchResult(duplicate=True, confidence=self.confidence, reason="Equivalent task")

    provider = Provider()
    matcher = MatchingService(database, settings, provider)
    await matcher.match_user(user_id)
    with database.session() as session:
        assert Repository(session).dashboard(user_id).unique_problems_solved == 2
    provider.model = "high-confidence-model"
    provider.confidence = 0.99
    await matcher.match_user(user_id)
    with database.session() as session:
        assert Repository(session).dashboard(user_id).unique_problems_solved == 1
    calls = provider.calls
    await matcher.match_user(user_id)
    assert provider.calls == calls
    provider.model = "offline-model"
    provider.fail = True
    assert await matcher.match_user(user_id) == "unavailable"
    with database.session() as session:
        data = Repository(session).dashboard(user_id)
        assert data.total_problems_solved == 2
        assert data.unique_problems_solved == 2
    database.dispose()


async def test_ollama_protocol_and_invalid_model_output() -> None:
    settings = Settings(matching_backend="ollama", matching_model="test-model")
    def handler(request: httpx.Request) -> httpx.Response:
        import json
        data = json.loads(request.content)
        assert data["stream"] is False
        assert data["model"] == "test-model"
        assert data["format"]["properties"]["duplicate"]["type"] == "boolean"
        return httpx.Response(200, json={"message": {"content": '{"duplicate":true,"confidence":0.99,"reason":"Equivalent constraints"}'}})
    provider = OllamaMatchProvider(settings, transport=httpx.MockTransport(handler))
    assert (await provider.compare({"statement": "A"}, {"statement": "B"})).duplicate
    provider.transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"message": {"content": '{"duplicate":"yes","confidence":2,"reason":"bad"}'}}))
    import pytest
    with pytest.raises(MatchingUnavailable):
        await provider.compare({}, {})


async def test_scheduler_syncs_due_profiles_once_and_skips_disconnected(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'scheduler.db'}",
                        leetcode_connector="fixture", geeksforgeeks_connector="fixture")
    database = Database(settings.database_url)
    database.initialize()
    _, profiles = seed(database)
    with database.session() as session:
        Repository(session).disconnect_profile(profiles[1], session.get(PlatformProfile, profiles[1]).user_id)
    ids = await sync_due_profiles(settings)
    assert len(ids) == 1
    assert await sync_due_profiles(settings) == []
    with database.session() as session:
        run = session.get(SyncRun, ids[0])
        assert run.platform_profile_id == profiles[0]
        assert run.status == "succeeded"
        assert run.matching_status == "exact_only"
    database.dispose()

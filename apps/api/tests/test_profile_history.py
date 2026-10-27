from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from profligator_api.config import Settings
from profligator_api.database import Database
from profligator_api.models import CodingRecord, SyncRun
from profligator_api.repository import Repository
from profligator_api.schemas import CanonicalProfile, ConnectorMode, NormalizedRecord, Platform
from profligator_api.connectors.base import payload_checksum


async def seed_history(client: httpx.AsyncClient):
    database = client._transport.app.state.database
    with database.session() as session:
        repository = Repository(session)
        user = repository.get_user_by_email("alex@example.com")
        profiles = []
        for platform in (Platform.LEETCODE, Platform.GEEKSFORGEEKS):
            profile = repository.save_profile(user.id, CanonicalProfile(
                platform=platform, handle="public_user", canonical_url="https://leetcode.com/u/public_user/" if platform == Platform.LEETCODE else "https://www.geeksforgeeks.org/profile/public_user/",
            ), ConnectorMode.FIXTURE, live_data=False)
            profiles.append(profile.id)
            records = [NormalizedRecord(
                platform=platform, source_id=f"problem-{index}", kind="problem", status="solved",
                title=f"Pair Sum {index:02}", canonical_url=f"https://leetcode.com/problems/problem-{index}/" if platform == Platform.LEETCODE else f"https://www.geeksforgeeks.org/problems/problem-{index}/1",
                difficulty="Easy" if index % 2 == 0 else "Hard", topics=["Array"],
                occurred_at=datetime(2024, 1, index + 1, tzinfo=UTC) if index < 3 else None,
                source_payload_checksum=payload_checksum({"index": index}),
            ) for index in range(30)]
            records.append(NormalizedRecord(platform=platform, source_id="contest", kind="contest", status="participated", title="A contest", canonical_url="https://leetcode.com/contest/weekly-contest-1/", source_payload_checksum=payload_checksum({"contest": True})))
            repository.upsert_records(profile.id, records)
    return profiles


async def test_problem_search_pagination_and_disconnection(client):
    profiles = await seed_history(client)
    first = await client.get("/api/v1/solved-problems?limit=25")
    assert first.status_code == 200 and first.headers["cache-control"] == "no-store"
    page = first.json()
    assert page["total"] == 60 and len(page["items"]) == 25
    next_page = (await client.get("/api/v1/solved-problems?limit=25&offset=25")).json()
    assert not {item["id"] for item in page["items"]} & {item["id"] for item in next_page["items"]}
    assert page["items"][0]["solved_at"] is not None
    assert "platform_profile_id" not in page["items"][0]
    filtered = (await client.get("/api/v1/solved-problems?platform=geeksforgeeks&difficulty=easy&search=pair%20sum%200")).json()
    assert filtered["total"] == 5 and all(item["platform"] == "geeksforgeeks" and item["difficulty"] == "Easy" for item in filtered["items"])
    # A user's percent/underscore characters are literal search text, not SQL wildcards.
    assert (await client.get("/api/v1/solved-problems?search=%25")).json()["total"] == 0
    assert (await client.get("/api/v1/solved-problems?offset=-1")).status_code == 422
    assert (await client.get("/api/v1/solved-problems?limit=101")).status_code == 422
    await client.delete(f"/api/v1/platform-profiles/{profiles[0]}")
    assert (await client.get("/api/v1/solved-problems")).json()["total"] == 30


async def test_public_question_history_consent_isolation_and_revocation(client):
    await seed_history(client)
    link = (await client.put("/api/v1/sharing", json={"enabled": True})).json()["shareable_link"]
    token = link.rsplit("/", 1)[1]
    public_path = f"/api/v1/public-profiles/{token}/solved-problems"
    await client.post("/api/v1/auth/logout")
    assert (await client.get("/api/v1/solved-problems")).status_code == 401
    public = await client.get(public_path)
    assert public.status_code == 200 and public.headers["cache-control"] == "no-store"
    assert public.json()["total"] == 60
    assert "email" not in public.text and "matching_state" not in public.text
    await client.post("/api/v1/auth/register", json={"email": "other@example.com", "handle": "other", "password": "a-long-test-password"})
    assert (await client.get("/api/v1/solved-problems")).json()["total"] == 0
    await client.post("/api/v1/auth/logout")
    await client.post("/api/v1/auth/login", json={"email": "alex@example.com", "password": "correct-horse-battery-staple"})
    await client.put("/api/v1/sharing", json={"enabled": False})
    revoked = await client.get(public_path)
    assert revoked.status_code == 404 and revoked.headers["cache-control"] == "no-store"


async def test_profile_sync_cooldown_reuses_completed_and_failed_attempts(client):
    client._transport.app.state.settings.profile_sync_cooldown_seconds = 900
    profile = (await client.post("/api/v1/platform-profiles", json={"platform": "leetcode", "handle_or_url": "fixture_user"})).json()
    body = {"platform_profile_id": profile["id"]}
    first = (await client.post("/api/v1/syncs", json=body)).json()
    second = (await client.post("/api/v1/syncs", json=body)).json()
    assert first["id"] == second["id"] and second["status"] == "succeeded"
    database = client._transport.app.state.database
    with database.session() as session:
        run = session.get(SyncRun, first["id"])
        run.finished_at = datetime.now(UTC) - timedelta(minutes=16)
        run.created_at = run.finished_at
    third = (await client.post("/api/v1/syncs", json=body)).json()
    assert third["id"] != first["id"] and third["records_written"] == 0
    with database.session() as session:
        Repository(session).fail_sync(session.get(SyncRun, third["id"]), code="provider_blocked", message="Source unavailable")
    failed = (await client.post("/api/v1/syncs", json=body)).json()
    assert failed["id"] == third["id"] and failed["status"] == "failed"
    assert (await client.get("/api/v1/dashboard")).json()["total_problems_solved"] == 3


def test_overlapping_sync_claims_reuse_one_job_and_recover_abandoned_runs(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'claims.db'}")
    database.initialize()
    with database.session() as session:
        repository = Repository(session)
        user = repository.create_user(email="owner@example.com", handle="owner", password_hash="test-only")
        profile = repository.save_profile(user.id, CanonicalProfile(platform=Platform.LEETCODE, handle="owner", canonical_url="https://leetcode.com/u/owner/"), ConnectorMode.FIXTURE, live_data=False)
        profile_id = profile.id
    def claim():
        with database.session() as session:
            run, claimed = Repository(session).claim_sync(profile_id, 900, 300)
            return run.id, claimed
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: claim(), range(4)))
    assert len({run_id for run_id, _ in claims}) == 1
    assert sum(claimed for _, claimed in claims) == 1
    with database.session() as session:
        run = session.get(SyncRun, claims[0][0])
        run.created_at = datetime.now(UTC) - timedelta(hours=1)
    new_id, claimed = claim()
    assert claimed and new_id != claims[0][0]
    with database.session() as session:
        assert session.get(SyncRun, claims[0][0]).error_code == "worker_timeout"
    database.dispose()

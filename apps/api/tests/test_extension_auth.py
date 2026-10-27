from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from profligator_api.models import ExtensionSession, User
from test_report_backend import seed


QUESTION = {"platform": "leetcode", "source_id": "0", "title": "Pair Sum",
            "canonical_url": "https://leetcode.com/problems/pair-sum/"}


async def grant(client: httpx.AsyncClient) -> dict:
    response = await client.post("/api/v1/extension/sessions", json={"label": "Test browser"},
                                 headers={"Origin": "http://testserver"})
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    return response.json()


async def test_extension_grant_is_scoped_hashed_and_revocable(client: httpx.AsyncClient) -> None:
    database = client._transport.app.state.database
    seed(database)
    issued = await grant(client)
    headers = {"Authorization": f"Bearer {issued['token']}"}
    with database.session() as session:
        saved = session.get(ExtensionSession, issued["session"]["id"])
        assert saved.token_hash != issued["token"]
        assert len(saved.token_hash) == 64
    identity = await client.get("/api/v1/extension/session", headers=headers)
    assert identity.status_code == 200
    assert identity.json()["handle"] == "alex_dev96"
    assert identity.json()["expires_at"].endswith("Z")
    check = await client.post("/api/v1/extension/check", json=QUESTION, headers=headers)
    assert check.status_code == 200
    assert check.json()["duplicate"] is True
    assert check.json()["status"] == "source_identity"
    # A scoped bearer cannot acquire web sessions or access general web APIs,
    # even when an authenticated web cookie is also present.
    for path in ["/api/v1/auth/me", "/api/v1/dashboard", "/api/v1/coding-records", "/api/v1/sharing", "/api/v1/extension/sessions"]:
        assert (await client.get(path, headers=headers)).status_code == 401
    assert (await client.post("/api/v1/extension/sessions", json={}, headers={**headers, "Origin": "http://testserver"})).status_code == 401
    devices = (await client.get("/api/v1/extension/sessions")).json()
    assert len(devices) == 1
    assert "token" not in devices[0] and "token_hash" not in devices[0]
    assert (await client.delete(f"/api/v1/extension/sessions/{issued['session']['id']}")).status_code == 204
    assert (await client.post("/api/v1/extension/check", json=QUESTION, headers=headers)).status_code == 401
    assert (await client.get("/api/v1/extension/session", headers=headers)).status_code == 401
    assert (await client.get("/api/v1/extension/sessions")).json() == []


async def test_extension_grants_require_application_origin_and_candidate(client: httpx.AsyncClient) -> None:
    for headers in [{}, {"Origin": "https://evil.test"}, {"Origin": "null"}]:
        assert (await client.post("/api/v1/extension/sessions", json={}, headers=headers)).status_code == 403
    issued = await grant(client)
    with client._transport.app.state.database.session() as session:
        user = session.scalar(select(User).where(User.email == "alex@example.com"))
        user.role = "recruiter"
    assert (await client.post("/api/v1/extension/sessions", json={}, headers={"Origin": "http://testserver"})).status_code == 403
    assert (await client.post("/api/v1/extension/check", json=QUESTION,
                              headers={"Authorization": f"Bearer {issued['token']}"})).status_code == 403


async def test_expiry_forged_tokens_and_owner_isolation(client: httpx.AsyncClient) -> None:
    issued = await grant(client)
    await client.post("/api/v1/auth/register", json={"email": "other@example.com", "handle": "other",
                                                   "password": "another-long-password"})
    assert (await client.get("/api/v1/extension/sessions")).json() == []
    assert (await client.delete(f"/api/v1/extension/sessions/{issued['session']['id']}")).status_code == 404
    for token in ["pfext_forged", issued["token"][:-1] + ("a" if issued["token"][-1] != "a" else "b")]:
        assert (await client.get("/api/v1/extension/session", headers={"Authorization": f"Bearer {token}"})).status_code == 401
    with client._transport.app.state.database.session() as session:
        session.get(ExtensionSession, issued["session"]["id"]).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert (await client.get("/api/v1/extension/session", headers={"Authorization": f"Bearer {issued['token']}"})).status_code == 401


async def test_extension_can_disconnect_only_its_own_session(client: httpx.AsyncClient) -> None:
    first = await grant(client)
    second = await grant(client)
    headers = {"Authorization": f"Bearer {first['token']}"}
    assert (await client.delete(f"/api/v1/extension/sessions/{second['session']['id']}", headers=headers)).status_code == 401
    assert (await client.delete("/api/v1/extension/session", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/extension/session", headers=headers)).status_code == 401
    assert (await client.get("/api/v1/extension/session", headers={"Authorization": f"Bearer {second['token']}"})).status_code == 200

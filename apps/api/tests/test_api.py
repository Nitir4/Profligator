import httpx


async def test_authentication_lifecycle_and_protected_routes(
    client: httpx.AsyncClient,
) -> None:
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "alex@example.com"

    duplicate = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alex@example.com",
            "handle": "another_handle",
            "password": "another-secure-password",
        },
    )
    assert duplicate.status_code == 409

    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["user"]["handle"] == "alex_dev96"

    logged_out = await client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 204
    assert (await client.get("/api/v1/dashboard")).status_code == 401

    rejected = await client.post(
        "/api/v1/auth/login",
        json={"email": "alex@example.com", "password": "wrong-password"},
    )
    assert rejected.status_code == 401

    logged_in = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "alex@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert logged_in.status_code == 200
    cookies = "\n".join(logged_in.headers.get_list("set-cookie")).lower()
    assert "httponly" in cookies
    assert "samesite=lax" in cookies
    assert (await client.get("/api/v1/dashboard")).status_code == 200


async def test_candidate_data_is_isolated(client: httpx.AsyncClient) -> None:
    first_profile = await client.post(
        "/api/v1/platform-profiles",
        json={"platform": "leetcode", "handle_or_url": "first_candidate"},
    )
    assert first_profile.status_code == 201

    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    second_registration = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "second@example.com",
            "handle": "second_candidate",
            "password": "second-secure-password",
        },
    )
    assert second_registration.status_code == 201
    assert (await client.get("/api/v1/platform-profiles")).json() == []
    inaccessible = await client.post(
        "/api/v1/syncs",
        json={"platform_profile_id": first_profile.json()["id"]},
    )
    assert inaccessible.status_code == 404


async def test_health_and_connector_modes(client: httpx.AsyncClient) -> None:
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["database"] == "ok"

    response = await client.get("/api/v1/connectors")
    assert response.status_code == 200
    modes = {item["platform"]: item for item in response.json()}
    assert modes["leetcode"]["live_data"] is False
    assert modes["geeksforgeeks"]["mode"] == "fixture"
    assert modes["codeforces"]["mode"] == "official_api"


async def test_fixture_profile_sync_is_idempotent(client: httpx.AsyncClient) -> None:
    link = await client.post(
        "/api/v1/platform-profiles",
        json={"platform": "leetcode", "handle_or_url": "fixture_user"},
    )
    assert link.status_code == 201
    profile = link.json()
    assert profile["verification_state"] == "fixture_only"

    first = await client.post(
        "/api/v1/syncs", json={"platform_profile_id": profile["id"]}
    )
    assert first.status_code == 202
    assert first.json()["status"] == "succeeded"
    assert first.json()["records_seen"] == 3
    assert first.json()["records_written"] == 3

    second = await client.post(
        "/api/v1/syncs", json={"platform_profile_id": profile["id"]}
    )
    assert second.status_code == 202
    assert second.json()["records_seen"] == 3
    assert second.json()["records_written"] == 0

    dashboard = await client.get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["total_problems_solved"] == 3
    assert payload["provisional_unique_problems"] == 3
    assert payload["data_state"] == "ready"
    assert payload["activity"]["known_timestamp_records"] == 3
    assert len(payload["activity"]["days"]) == 3
    assert payload["activity"]["longest_streak"] == 1
    topics = {item["name"]: item for item in payload["topics"]["items"]}
    assert topics["Array"] == {"name": "Array", "count": 2, "percent": 25.0}
    difficulties = {
        item["name"]: item for item in payload["difficulties"]["items"]
    }
    assert difficulties["Easy"]["count"] == 1
    assert difficulties["Medium"]["count"] == 2
    assert payload["difficulties"]["unrated_records"] == 0


async def test_geeksforgeeks_fixture_uses_same_normalized_contract(
    client: httpx.AsyncClient,
) -> None:
    link = await client.post(
        "/api/v1/platform-profiles",
        json={"platform": "geeksforgeeks", "handle_or_url": "fixture_user"},
    )
    assert link.status_code == 201
    profile = link.json()
    assert profile["connector_mode"] == "fixture"

    sync = await client.post(
        "/api/v1/syncs", json={"platform_profile_id": profile["id"]}
    )
    assert sync.status_code == 202
    assert sync.json()["status"] == "succeeded"
    assert sync.json()["records_seen"] == 2


async def test_profile_validation_rejects_wrong_host(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/platform-profiles/check",
        json={"platform": "leetcode", "handle_or_url": "https://example.com/u/alex"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_profile_url"


async def test_missing_profile_and_sync_return_404(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/syncs",
        json={"platform_profile_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert response.status_code == 404

    response = await client.get("/api/v1/syncs/00000000-0000-0000-0000-000000000099")
    assert response.status_code == 404


async def test_profile_disconnect_is_soft_and_relink_reactivates(
    client: httpx.AsyncClient,
) -> None:
    linked = await client.post(
        "/api/v1/platform-profiles",
        json={"platform": "leetcode", "handle_or_url": "disconnect_me"},
    )
    assert linked.status_code == 201
    profile_id = linked.json()["id"]

    sync = await client.post(
        "/api/v1/syncs", json={"platform_profile_id": profile_id}
    )
    assert sync.status_code == 202
    assert sync.json()["status"] == "succeeded"

    disconnected = await client.delete(f"/api/v1/platform-profiles/{profile_id}")
    assert disconnected.status_code == 204
    assert (await client.get("/api/v1/platform-profiles")).json() == []
    dashboard = (await client.get("/api/v1/dashboard")).json()
    assert dashboard["connected_profiles"] == 0
    assert dashboard["total_problems_solved"] == 0

    unavailable_sync = await client.post(
        "/api/v1/syncs", json={"platform_profile_id": profile_id}
    )
    assert unavailable_sync.status_code == 404

    relinked = await client.post(
        "/api/v1/platform-profiles",
        json={"platform": "leetcode", "handle_or_url": "disconnect_me"},
    )
    assert relinked.status_code == 201
    assert relinked.json()["id"] == profile_id
    assert len((await client.get("/api/v1/platform-profiles")).json()) == 1

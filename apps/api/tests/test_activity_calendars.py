"""Public calendar contracts and their separation from question acceptance dates."""

from datetime import UTC, date, datetime
import json

import httpx
import pytest

from profligator_api.connectors.base import ConnectorError
from profligator_api.connectors.leetcode import LeetCodeConnector
from profligator_api.repository import Repository
from profligator_api.schemas import (
    ActivityCalendar, ActivityDay, CalendarCollection, CanonicalProfile,
    ConnectorMode, NormalizedRecord, Platform,
)


def calendar_payload(year, days=None, active_years=None, handle="public_user"):
    return {"matchedUser": {"username": handle, "userCalendar": {
        "activeYears": active_years if active_years is not None else [year],
        "submissionCalendar": json.dumps({
            str(int(datetime(year, 1, day, tzinfo=UTC).timestamp())): count
            for day, count in (days or {}).items()
        }),
    }}}


async def test_calendar_budget_advances_through_active_years_and_has_no_problem_dates():
    now = datetime.now(UTC)
    years = [now.year - 4, now.year - 3, now.year - 1, now.year]
    requests = []
    def handler(request):
        body = json.loads(request.content)
        assert "cookie" not in request.headers
        year = body["variables"]["year"]
        requests.append(year)
        return httpx.Response(200, json={"data": calendar_payload(year, {1: 7}, years)})
    connector = LeetCodeConnector(0, 0, transport=httpx.MockTransport(handler), calendar_year_limit=3)
    profile = await connector.validate_handle("public_user")
    first = await connector.fetch_activity(profile)
    assert first.status == "partial" and first.error_code is None
    assert requests == [now.year, now.year - 1, now.year - 3]
    assert sum(day.count for c in first.calendars for day in c.days) == 21
    known = {c.year: c.fetched_at for c in first.calendars}
    # A fresh connector simulates the next job; known years come from persistence.
    next_connector = LeetCodeConnector(0, 0, transport=httpx.MockTransport(handler), calendar_year_limit=3)
    second = await next_connector.fetch_activity(profile, known)
    assert requests[-3:] == [now.year, now.year - 1, now.year - 4]
    assert second.status == "available"
    assert all(set(day.model_dump()) == {"date", "count"} for c in second.calendars for day in c.days)


@pytest.mark.parametrize("fault", ["identity", "bad_json", "negative", "bool", "other_year", "future_year", "duplicate_day"])
def test_invalid_calendar_cannot_become_zero_or_fabricated_activity(fault):
    year = datetime.now(UTC).year - 1
    data = calendar_payload(year, {1: 3})
    user = data["matchedUser"]
    calendar = user["userCalendar"]
    key = str(int(datetime(year, 1, 1, tzinfo=UTC).timestamp()))
    if fault == "identity": user["username"] = "another_user"
    elif fault == "bad_json": calendar["submissionCalendar"] = "{broken"
    elif fault == "negative": calendar["submissionCalendar"] = json.dumps({key: -1})
    elif fault == "bool": calendar["submissionCalendar"] = json.dumps({key: True})
    elif fault == "other_year": calendar["submissionCalendar"] = json.dumps({"1735689600": 1}) if year != 2025 else json.dumps({"1704067200": 1})
    elif fault == "future_year": calendar["activeYears"] = [datetime.now(UTC).year + 1]
    elif fault == "duplicate_day": calendar["submissionCalendar"] = json.dumps({key: 1, str(int(key) + 60): 2})
    with pytest.raises(ConnectorError):
        LeetCodeConnector.parse_calendar(data, "public_user", year)


async def test_calendar_access_denial_retains_partial_results_and_stops_requests():
    year = datetime.now(UTC).year
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requested = body["variables"]["year"]
        requests.append(requested)
        if requested == year:
            return httpx.Response(200, json={"data": calendar_payload(year, {1: 2}, [year - 2, year])})
        return httpx.Response(403)
    connector = LeetCodeConnector(0, transport=httpx.MockTransport(handler), calendar_year_limit=10)
    collection = await connector.fetch_activity(await connector.validate_handle("public_user"))
    assert collection.status == "partial" and collection.error_code == "provider_access_denied"
    assert requests == [year, year - 1] and len(collection.calendars) == 1


def test_empty_calendar_is_valid_and_private_calendar_is_unavailable():
    year = datetime.now(UTC).year
    calendar, _ = LeetCodeConnector.parse_calendar(calendar_payload(year), "public_user", year)
    assert calendar.days == []
    with pytest.raises(ConnectorError) as error:
        LeetCodeConnector.parse_calendar({"matchedUser": {"username": "public_user", "userCalendar": None}}, "public_user", year)
    assert error.value.code == "calendar_unavailable"


async def test_calendar_persistence_no_double_counting_sharing_and_disconnection(client):
    database = client._transport.app.state.database
    fetched = datetime.now(UTC)
    collection = CalendarCollection(status="available", available_years=[2024], calendars=[
        ActivityCalendar(year=2024, days=[ActivityDay(date=date(2024, 1, 1), count=10),
                                         ActivityDay(date=date(2024, 1, 2), count=7)], fetched_at=fetched),
    ])
    with database.session() as session:
        repo = Repository(session)
        user = repo.get_user_by_email("alex@example.com")
        profiles = []
        for platform in (Platform.LEETCODE, Platform.GEEKSFORGEEKS):
            profile = repo.save_profile(user.id, CanonicalProfile(platform=platform, handle="public_user",
                canonical_url="https://leetcode.com/u/public_user/" if platform == Platform.LEETCODE else "https://www.geeksforgeeks.org/profile/public_user/"),
                ConnectorMode.SCRAPER, live_data=True)
            profiles.append(profile.id)
            dates = [datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 3, tzinfo=UTC), None] if platform == Platform.LEETCODE else [datetime(2024, 1, 1, tzinfo=UTC)]
            repo.upsert_records(profile.id, [NormalizedRecord(platform=platform, source_id=str(i),
                kind="problem", status="solved", title=f"Problem {i}", canonical_url="https://leetcode.com/problems/pair/",
                difficulty="Basic" if platform == Platform.GEEKSFORGEEKS else "Easy",
                occurred_at=when, source_payload_checksum=str(i)) for i, when in enumerate(dates)])
        repo.save_activity(profiles[0], collection)
        repo.save_activity(profiles[0], collection)  # snapshot replacement, not addition
        assert list(repo.activity_years(profiles[0])) == [2024]
    response = (await client.get("/api/v1/dashboard")).json()
    activity = response["activity"]
    assert activity["calendar_submissions"] == 17 and activity["calendar_profiles"] == 1
    assert sum(day["count"] for day in activity["days"]) == 18
    assert activity["known_timestamp_records"] == 3 and activity["unknown_timestamp_records"] == 1
    assert activity["count_label"] == "submissions and dated solved records" and activity["timezone"] == "UTC"
    assert response["total_problems_solved"] == 4
    assert response["difficulties"]["items"][0]["name"] == "Fundamentals"
    assert response["difficulties"]["items"][0]["count"] == 1
    assert response["difficulties"]["unrated_records"] == 0
    with database.session() as session:
        repo = Repository(session)
        repo.save_activity(profiles[0], CalendarCollection(status="unavailable", error_code="provider_timeout"))
    assert (await client.get("/api/v1/dashboard")).json()["activity"]["calendar_submissions"] == 17
    token = (await client.put("/api/v1/sharing", json={"enabled": True})).json()["shareable_link"].rsplit("/", 1)[1]
    public = await client.get(f"/api/v1/public-profiles/{token}")
    assert public.json()["dashboard"]["activity"]["calendar_submissions"] == 17
    await client.put("/api/v1/sharing", json={"enabled": False})
    assert (await client.get(f"/api/v1/public-profiles/{token}")).status_code == 404
    await client.delete(f"/api/v1/platform-profiles/{profiles[0]}")
    response = (await client.get("/api/v1/dashboard")).json()
    assert response["activity"]["calendar_profiles"] == 0
    assert sum(day["count"] for day in response["activity"]["days"]) == 1


async def test_optional_calendar_schema_failure_does_not_discard_question_imports(tmp_path, monkeypatch):
    import profligator_api.connectors.registry as registry
    from profligator_api.config import Settings
    from profligator_api.main import create_app
    from test_public_collectors import lc_handler

    requests = []
    def handler(request):
        variables = json.loads(request.content)["variables"]
        if "year" in variables:
            requests.append(variables["year"])
            return httpx.Response(200, json={"errors": [{"message": "Calendar unavailable"}]})
        return lc_handler(request)
    def factory(interval, budget, **kwargs):
        return LeetCodeConnector(0, budget, transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(registry, "LeetCodeConnector", factory)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'optional.db'}", scraper_statement_limit=0)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as test:
            await test.post("/api/v1/auth/register", json={"email":"calendar@example.com","handle":"calendar_user","password":"a-long-test-password"})
            profile = (await test.post("/api/v1/platform-profiles", json={"platform":"leetcode","handle_or_url":"public_user"})).json()
            sync = (await test.post("/api/v1/syncs", json={"platform_profile_id":profile["id"]})).json()
            assert sync["status"] == "succeeded"
            dashboard = (await test.get("/api/v1/dashboard")).json()
            assert dashboard["total_problems_solved"] == 2
            assert dashboard["platforms"][0]["activity_status"] == "unavailable"
            assert len(requests) == 1


async def test_sync_jobs_resume_saved_historical_calendar_years(tmp_path, monkeypatch):
    import profligator_api.connectors.registry as registry
    from profligator_api.config import Settings
    from profligator_api.main import create_app
    from test_public_collectors import lc_handler

    now = datetime.now(UTC)
    active = [now.year, now.year - 1, now.year - 3, now.year - 4]
    requests = []
    def handler(request):
        variables = json.loads(request.content)["variables"]
        if "year" in variables:
            year = variables["year"]
            requests.append(year)
            return httpx.Response(200, json={"data": calendar_payload(year, {1: 7}, active)})
        return lc_handler(request)
    def factory(interval, budget, **kwargs):
        return LeetCodeConnector(0, budget, transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(registry, "LeetCodeConnector", factory)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'progress.db'}",
                        scraper_statement_limit=0, scraper_calendar_year_limit=3, profile_sync_cooldown_seconds=0)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as test:
            await test.post("/api/v1/auth/register", json={"email":"progress@example.com","handle":"progress_user","password":"a-long-test-password"})
            profile = (await test.post("/api/v1/platform-profiles", json={"platform":"leetcode","handle_or_url":"public_user"})).json()
            body = {"platform_profile_id":profile["id"]}
            assert (await test.post("/api/v1/syncs", json=body)).json()["status"] == "succeeded"
            first = (await test.get("/api/v1/dashboard")).json()
            assert first["platforms"][0]["activity_status"] == "partial"
            assert first["activity"]["calendar_submissions"] == 21
            assert (await test.post("/api/v1/syncs", json=body)).json()["status"] == "succeeded"
            second = (await test.get("/api/v1/dashboard")).json()
            assert second["platforms"][0]["activity_status"] == "available"
            assert second["platforms"][0]["activity_years"] == sorted(active)
            assert second["activity"]["calendar_submissions"] == 28
            assert requests == [now.year, now.year - 1, now.year - 3, now.year, now.year - 1, now.year - 4]


async def test_source_local_calendar_is_separate_from_utc_and_revoked_profiles(client):
    database = client._transport.app.state.database
    with database.session() as session:
        repo = Repository(session)
        user = repo.get_user_by_email("alex@example.com")
        profile = repo.save_profile(user.id, CanonicalProfile(platform=Platform.GEEKSFORGEEKS,
            handle="local_clock", canonical_url="https://www.geeksforgeeks.org/profile/local_clock/"),
            ConnectorMode.SCRAPER, live_data=True)
        profile_id = profile.id
        repo.upsert_records(profile_id, [NormalizedRecord(platform=Platform.GEEKSFORGEEKS,
            source_id=str(index), kind="problem", status="solved", title=f"Local date {index}",
            canonical_url=f"https://www.geeksforgeeks.org/problems/local-{index}/1",
            source_solved_at=source_time, occurred_at=utc_time, source_payload_checksum=str(index))
            for index, (source_time, utc_time) in enumerate([
                ("2025-01-01T09:00:00", None), ("2025-01-01T18:30:00", None),
                ("2025-01-02T12:00:00", datetime(2025, 1, 2, tzinfo=UTC)), (None, None),
            ])])
    activity = (await client.get("/api/v1/dashboard")).json()["activity"]
    assert activity["days"] == [{"date": "2025-01-02", "count": 1}]
    assert activity["source_calendars"] == [{"platform": "geeksforgeeks", "profile_handle": "local_clock",
        "days": [{"date": "2025-01-01", "count": 2}]}]
    assert activity["known_timestamp_records"] == 1 and activity["unknown_timestamp_records"] == 3
    token = (await client.put("/api/v1/sharing", json={"enabled": True})).json()["shareable_link"].rsplit("/", 1)[1]
    assert (await client.get(f"/api/v1/public-profiles/{token}")).json()["dashboard"]["activity"]["source_calendars"] == activity["source_calendars"]
    assert (await client.delete(f"/api/v1/platform-profiles/{profile_id}")).status_code == 204
    assert (await client.get("/api/v1/dashboard")).json()["activity"]["source_calendars"] == []
    await client.put("/api/v1/sharing", json={"enabled": False})
    assert (await client.get(f"/api/v1/public-profiles/{token}")).status_code == 404

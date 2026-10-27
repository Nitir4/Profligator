"""Contracts based on public response shapes verified on 1 October 2026.

All identities, statements and timestamps below are synthetic; tests never use the network.
"""

from datetime import UTC, datetime
import gzip
import json

import httpx
import pytest

from profligator_api.config import Settings
from profligator_api.connectors.base import ConnectorError
from profligator_api.connectors.geeksforgeeks import GeeksForGeeksConnector
from profligator_api.connectors.leetcode import LeetCodeConnector
from profligator_api.connectors.public_web import PublicWebClient, embedded_json, public_profile
from profligator_api.connectors.public_web import statement_text
from profligator_api.connectors.registry import ConnectorRegistry
from profligator_api.main import create_app
from profligator_api.schemas import Platform


def lc_data(total=100):
    return {
        "matchedUser": {"username": "public_user", "profile": {"realName": "Public User"},
                        "submitStatsGlobal": {"acSubmissionNum": [{"difficulty": "All", "count": total}]}},
        "recentAcSubmissionList": [
            {"id": "22", "title": "Pair", "titleSlug": "pair", "timestamp": "1730000200"},
            {"id": "11", "title": "Pair", "titleSlug": "pair", "timestamp": "1730000100"},
            {"id": "33", "title": "Locked", "titleSlug": "locked", "timestamp": "1730000300"},
        ],
        "userContestRanking": {"rating": 2100.5, "globalRanking": 123},
        "userContestRankingHistory": [
            {"attended": True, "rating": 2100.5, "ranking": 4,
             "contest": {"title": "Weekly Contest 400", "startTime": 1730000000}},
            {"attended": False, "rating": 2100.5, "ranking": 0,
             "contest": {"title": "Weekly Contest 401", "startTime": 1730500000}},
        ],
    }


def lc_handler(request):
    body = json.loads(request.content)
    assert request.url == "https://leetcode.com/graphql"
    assert "cookie" not in request.headers
    if "username" in body["variables"]:
        if "year" in body["variables"]:
            return httpx.Response(200, json={"data": {"matchedUser": {"username": "public_user", "userCalendar": None}}})
        assert body["variables"]["limit"] == 20
        return httpx.Response(200, json={"data": lc_data()})
    key = body["variables"]["titleSlug"]
    return httpx.Response(200, json={"data": {"question": {
        "title": key.title(), "titleSlug": key, "difficulty": "Easy",
        "content": "<p>Find A &lt; B.</p><p>n &le; 10<sup>5</sup></p>",
        "isPaidOnly": key == "locked", "topicTags": [{"name": "Arrays"}],
    }}})


def gfg_profile_html(total=1, *, handle="public_user"):
    record = ["$", "$L1", None, {"username": handle, "articleCount": {
        "name": "Public User", "total_problems_solved": total, "score": 999,
        "institute_rank": 1,
    }}]
    flight = "6:" + json.dumps(record) + "\n"
    # Flight records can span script tags, and the text itself is JSON encoded.
    middle = len(flight) // 2
    return "".join("<script>self.__next_f.push(" + json.dumps([1, chunk]) + ")</script>"
                   for chunk in (flight[:middle], flight[middle:]))


def gfg_solved(count=1):
    return {"status": "success", "count": count, "result": {"Medium": {
        str(index): {"slug": f"pair-{index}", "pname": f"Pair {index}", "lang": "cpp",
                     "user_subtime": "2025-05-01 12:00:00"} for index in range(count)
    }}}


def gfg_problem_html(key, statement="<p>Find a pair.</p><pre>a &lt; b</pre>"):
    metadata = {"slug": key, "problem_name": "Pair", "difficulty": "Medium",
                "problem_question": statement,
                "tags": {"topic_tags": ["Arrays"], "company_tags": ["Employer"]}}
    payload = {"props": {"pageProps": {"initialState": {
        "problemApi": {"queries": {"getProblemDetails": {"status": "fulfilled", "data": metadata}}}
    }}}}
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"


async def test_leetcode_recent_window_dedup_statements_contests_and_cache():
    requests = []
    def handler(request):
        requests.append(request)
        return lc_handler(request)
    connector = LeetCodeConnector(0, transport=httpx.MockTransport(handler), collect_contests=True)
    profile = await connector.validate_handle("https://leetcode.com/u/public_user/")
    snapshot = await connector.fetch_profile(profile)
    assert snapshot.source_total_solved == 100
    assert snapshot.history_complete is False
    assert snapshot.rank == "123"
    page = await connector.fetch_solved_records(profile)
    assert len(page.records) == 2
    pair, locked = page.records
    assert pair.occurred_at == datetime.fromtimestamp(1730000100, UTC)
    assert pair.submission_url.endswith("/11/")
    assert pair.statement == "Find A < B.\nn ≤ 10^(5)"
    assert pair.topics == ["Arrays"]
    assert locked.statement is None
    assert await connector.fetch_solved_records(profile) == page
    contests = await connector.fetch_contests(profile)
    assert len(contests.records) == 1
    assert contests.records[0].global_rank == 4
    assert contests.records[0].canonical_url.endswith("/weekly-contest-400/")
    assert len(requests) == 3  # one profile response, one request per distinct problem


async def test_leetcode_question_focus_skips_contest_statistics_and_keeps_solved_evidence():
    requests = []
    data = lc_data(total=3)
    data["userContestRankingHistory"][0].update({"problemsSolved": 2, "totalProblems": 2})
    data["userContestRankingHistory"][0]["contest"]["questions"] = [
        {"title": "Pair", "titleSlug": "pair"}, {"title": "Older", "titleSlug": "older"},
    ]
    def handler(request):
        query = json.loads(request.content)["query"]
        assert "userContestRanking(" not in query
        assert "rating" not in query and "ranking" not in query and "startTime" not in query
        requests.append(request)
        return httpx.Response(200, json={"data": data})
    connector = LeetCodeConnector(0, 0, transport=httpx.MockTransport(handler))
    profile = await connector.validate_handle("public_user")
    assert (await connector.fetch_contests(profile)).records == []
    assert requests == []  # Disabled contest import never makes a provider request.
    snapshot = await connector.fetch_profile(profile)
    assert snapshot.rating is None and snapshot.rank is None
    assert snapshot.history_complete is True
    assert {record.source_id for record in (await connector.fetch_solved_records(profile)).records} == {"pair", "locked", "older"}


@pytest.mark.parametrize("unavailable", [False, True])
async def test_missing_optional_contest_evidence_does_not_block_recent_questions(unavailable):
    data = lc_data(total=2)
    data.pop("userContestRanking")
    data["userContestRankingHistory"] = None
    payload = {"data": data}
    if unavailable:
        payload["errors"] = [{"message": "History unavailable", "path": ["userContestRankingHistory"]}]
    connector = LeetCodeConnector(0, 0, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    profile = await connector.validate_handle("public_user")
    assert (await connector.fetch_profile(profile)).history_complete is True
    assert len((await connector.fetch_solved_records(profile)).records) == 2


async def test_leetcode_backfills_fully_solved_contests_without_inventing_acceptance_times():
    data = lc_data(total=3)
    data["userContestRankingHistory"][0].update({"problemsSolved": 2, "totalProblems": 2})
    data["userContestRankingHistory"][0]["contest"]["questions"] = [
        {"title": "Pair", "titleSlug": "pair"},
        {"title": "Older Question", "titleSlug": "older-question"},
    ]
    # Partial contest: neither task can be marked solved from a count of one.
    data["userContestRankingHistory"].append({
        "attended": True, "problemsSolved": 1, "totalProblems": 2,
        "contest": {"title": "Weekly Contest 399", "startTime": 1720000000,
                    "questions": [{"title": "Unknown A", "titleSlug": "unknown-a"},
                                  {"title": "Unknown B", "titleSlug": "unknown-b"}]},
    })
    connector = LeetCodeConnector(0, 0, transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"data": data})))
    profile = await connector.validate_handle("public_user")
    snapshot = await connector.fetch_profile(profile)
    assert snapshot.history_complete is True
    records = (await connector.fetch_solved_records(profile)).records
    assert {record.source_id for record in records} == {"pair", "locked", "older-question"}
    pair = next(record for record in records if record.source_id == "pair")
    older = next(record for record in records if record.source_id == "older-question")
    assert pair.submission_url.endswith("/11/")  # direct evidence wins over backfill
    assert pair.occurred_at == datetime.fromtimestamp(1730000100, UTC)
    assert older.occurred_at is None and older.submission_url is None
    assert older.canonical_url == "https://leetcode.com/problems/older-question/"


@pytest.mark.parametrize("questions", [None, [{"title": "Pair", "titleSlug": "pair"}],
    [{"title": "Pair", "titleSlug": "pair"}, {"title": "Pair", "titleSlug": "pair"}]])
def test_leetcode_never_backfills_from_missing_inconsistent_or_duplicate_question_lists(questions):
    data = lc_data()
    contest = data["userContestRankingHistory"][0]
    contest.update({"problemsSolved": 2, "totalProblems": 2})
    contest["contest"]["questions"] = questions
    assert set(LeetCodeConnector.solved_evidence(data)) == {"pair", "locked"}


async def test_leetcode_backfill_paginates_over_1000_records_with_no_metadata_crawl():
    data = lc_data(total=1003)
    data["userContestRankingHistory"] = [
        {"attended": True, "problemsSolved": 1, "totalProblems": 1,
         "contest": {"title": f"Weekly Contest {index + 1000}", "startTime": 1700000000,
                     "questions": [{"title": f"Old {index}", "titleSlug": f"old-{index}"}]}}
        for index in range(1001)
    ]
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": data})
    connector = LeetCodeConnector(0, 0, transport=httpx.MockTransport(handler))
    profile = await connector.validate_handle("public_user")
    snapshot = await connector.fetch_profile(profile)
    assert snapshot.history_complete is True
    first = await connector.fetch_solved_records(profile)
    second = await connector.fetch_solved_records(profile, first.next_cursor)
    assert len(first.records) == 1000 and len(second.records) == 3
    assert second.next_cursor is None
    assert len(requests) == 1


@pytest.mark.parametrize("payload,code", [
    ({"data": {"matchedUser": None}}, "profile_not_found"),
    ({"errors": [{"message": "Schema changed"}]}, "provider_query_error"),
    ({"data": {**lc_data(), "recentAcSubmissionList": None}}, "invalid_provider_response"),
    ({"data": {**lc_data(), "matchedUser": {"username": "someone_else"}}}, "invalid_provider_response"),
])
async def test_leetcode_missing_private_or_changed_schema_fails_explicitly(payload, code):
    connector = LeetCodeConnector(0, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    profile = await connector.validate_handle("public_user")
    with pytest.raises(ConnectorError) as exc:
        await connector.fetch_profile(profile)
    assert exc.value.code == code


async def test_gfg_flight_profile_solved_coverage_and_missing_statement():
    requests = []
    def handler(request):
        requests.append(request)
        assert "cookie" not in request.headers
        if request.method == "POST":
            assert json.loads(request.content)["handle"] == "public_user"
            return httpx.Response(200, json=gfg_solved(2))
        if "/profile/" in request.url.path:
            return httpx.Response(200, text=gfg_profile_html(3))
        if "pair-1" in request.url.path:
            return httpx.Response(401)
        return httpx.Response(200, text=gfg_problem_html("pair-0"))
    connector = GeeksForGeeksConnector(0, transport=httpx.MockTransport(handler))
    profile = await connector.validate_handle("https://auth.geeksforgeeks.org/user/public_user/")
    assert profile.canonical_url == "https://www.geeksforgeeks.org/profile/public_user/"
    snapshot = await connector.fetch_profile(profile)
    assert snapshot.history_complete is False
    assert snapshot.source_total_solved == 3
    assert snapshot.rank is None and snapshot.rating is None  # not institute rank/coding score
    page = await connector.fetch_solved_records(profile)
    assert len(page.records) == 2
    assert page.records[0].statement == "Find a pair.\na < b"
    assert page.records[0].topics == ["Arrays"]  # company tags are not problem topics
    assert page.records[1].statement is None
    assert all(record.occurred_at is None and record.submission_url is None for record in page.records)
    assert all(record.source_solved_at == "2025-05-01T12:00:00" for record in page.records)
    assert await connector.fetch_solved_records(profile) == page
    assert len(requests) == 4
    assert (await connector.fetch_contests(profile)).records == []


async def test_gfg_pagination_keeps_all_solved_records_without_mass_statement_requests():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=gfg_solved(1001)) if request.method == "POST" else httpx.Response(200, text=gfg_profile_html(1001))
    connector = GeeksForGeeksConnector(0, 0, transport=httpx.MockTransport(handler))
    profile = await connector.validate_handle("public_user")
    snapshot = await connector.fetch_profile(profile)
    assert snapshot.history_complete is True
    first = await connector.fetch_solved_records(profile)
    second = await connector.fetch_solved_records(profile, first.next_cursor)
    assert len(first.records) == 1000 and len(second.records) == 1
    assert second.next_cursor is None
    assert len({record.source_id for record in first.records + second.records}) == 1001
    assert len(requests) == 2
    with pytest.raises(ConnectorError):
        await connector.fetch_solved_records(profile, "-1")


def test_gfg_page_identity_and_problem_identity_are_checked():
    with pytest.raises(ConnectorError, match="different user"):
        GeeksForGeeksConnector.parse_profile(gfg_profile_html(handle="someone_else"), "public_user")
    with pytest.raises(ConnectorError, match="different problem"):
        GeeksForGeeksConnector.parse_problem(gfg_problem_html("other"), "pair")
    assert GeeksForGeeksConnector.parse_problem("<html>Authentication required</html>", "pair") is None
    assert len(embedded_json(gfg_profile_html())) == 1


def test_statement_normalization_preserves_diagrams_table_cells_and_math():
    assert statement_text('<p>A</p><img src="first.svg" alt="graph">') != statement_text('<p>A</p><img src="second.svg" alt="graph">')
    assert statement_text('<tr><td>1</td><td>23</td></tr>') != statement_text('<tr><td>12</td><td>3</td></tr>')
    assert statement_text('<p>x<sub>i</sub> &lt; 10<sup>9</sup></p>') == 'x_(i) < 10^(9)'
    assert statement_text('<p>Long ' + 'a' * 50001 + '</p>') is None


async def test_http_decompresses_once_and_blocks_external_redirects():
    client = PublicWebClient("Test", {"public.test"}, 0, transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=gzip.compress(b'{"value": 1}'), headers={"Content-Encoding": "gzip"})))
    assert client.json(await client.request("GET", "https://public.test/profile")) == {"value": 1}
    requests = []
    def redirect(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
    client.transport = httpx.MockTransport(redirect)
    with pytest.raises(ConnectorError) as exc:
        await client.request("GET", "https://public.test/profile")
    assert exc.value.code == "provider_redirect_blocked" and len(requests) == 1


@pytest.mark.parametrize("status,code", [(403, "provider_access_denied"), (429, "provider_rate_limited")])
async def test_access_denial_and_rate_limits_stop_without_retry(status, code):
    client = PublicWebClient("Test", {"public.test"}, 0, transport=httpx.MockTransport(
        lambda _: httpx.Response(status, headers={"Retry-After": "3600"})))
    with pytest.raises(ConnectorError) as exc:
        await client.request("GET", "https://public.test/profile")
    assert exc.value.code == code and exc.value.retryable is False


@pytest.mark.parametrize("url", ["https://leetcode.com:bad/u/test", "https://evil.test/u/test", "https://user@leetcode.com/u/test", "https://leetcode.com/u/test/private"])
def test_profile_urls_cannot_change_the_request_origin(url):
    with pytest.raises(ConnectorError):
        public_profile(Platform.LEETCODE, url)


async def test_scrapers_run_through_authenticated_sync_and_preserve_old_acceptance(tmp_path, monkeypatch):
    import profligator_api.jobs as jobs
    import profligator_api.main as main

    data = lc_data()
    def handler(request):
        if "username" in json.loads(request.content)["variables"]:
            return httpx.Response(200, json={"data": data})
        return lc_handler(request)
    connector = LeetCodeConnector(0, transport=httpx.MockTransport(handler))
    registry = ConnectorRegistry(Settings())
    async def forbidden_contest_fetch(*_args, **_kwargs):
        raise AssertionError("Question-focused sync must skip contest collection")
    connector.fetch_contests = forbidden_contest_fetch
    registry._connectors[Platform.LEETCODE] = connector
    monkeypatch.setattr(main, "ConnectorRegistry", lambda _, **kwargs: registry)
    monkeypatch.setattr(jobs, "ConnectorRegistry", lambda _, **kwargs: registry)
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'collectors.db'}", profile_sync_cooldown_seconds=0))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            register = await client.post("/api/v1/auth/register", json={"email": "collector@example.com", "handle": "collector_user", "password": "test-password-123"})
            assert register.status_code == 201
            checked = await client.post("/api/v1/platform-profiles/check", json={"platform": "leetcode", "handle_or_url": "public_user"})
            assert checked.json()["mode"] == "scraper" and checked.json()["live_data"] is True
            linked = await client.post("/api/v1/platform-profiles", json={"platform": "leetcode", "handle_or_url": "public_user"})
            assert linked.json()["verification_state"] == "unverified"
            sync_body = {"platform_profile_id": linked.json()["id"]}
            first = (await client.post("/api/v1/syncs", json=sync_body)).json()
            assert first["status"] == "succeeded" and first["records_written"] == 2
            second = (await client.post("/api/v1/syncs", json=sync_body)).json()
            assert second["status"] == "succeeded" and second["records_written"] == 0
            # Historical contest rows stay stored but must not surface in either view.
            from profligator_api.repository import Repository
            from profligator_api.schemas import NormalizedRecord
            with app.state.database.session() as session:
                repository = Repository(session)
                profile = repository.get_profile(linked.json()["id"])
                profile.rating = 2100
                profile.rank = "123"
                repository.upsert_records(profile.id, [NormalizedRecord(
                    platform="leetcode", source_id="weekly-contest-400", kind="contest", status="participated",
                    title="Weekly Contest 400", canonical_url="https://leetcode.com/contest/weekly-contest-400/",
                    source_payload_checksum="historical", contest_rating=2100, global_rank=4,
                )])
            dashboard = (await client.get("/api/v1/dashboard")).json()
            assert dashboard["total_problems_solved"] == 2
            assert dashboard["platforms"][0]["source_total_solved"] == 100
            assert dashboard["platforms"][0]["history_complete"] is False
            assert dashboard["contests"] == []
            assert dashboard["platforms"][0]["contests_enabled"] is False
            assert dashboard["platforms"][0]["rating"] is None
            share = (await client.put("/api/v1/sharing", json={"enabled": True})).json()
            token = share["shareable_link"].rsplit("/", 1)[1]
            public = (await client.get(f"/api/v1/public-profiles/{token}")).json()["dashboard"]
            assert public["contests"] == []
            assert public["platforms"][0]["rank"] is None
            # A later recent acceptance and reduced metadata must preserve imported evidence.
            data["recentAcSubmissionList"] = [{"id": "99", "title": "Pair", "titleSlug": "pair", "timestamp": "1730000500"}]
            connector._statement_limit = 0
            for _ in range(2):
                assert (await client.post("/api/v1/syncs", json=sync_body)).json()["status"] == "succeeded"
            rows = (await client.get("/api/v1/coding-records")).json()
            pair = next(row for row in rows if row["source_id"] == "pair")
            assert pair["submission_url"].endswith("/11/")
            from sqlalchemy import select
            from profligator_api.models import CodingRecord
            with app.state.database.session() as session:
                stored = session.scalar(select(CodingRecord).where(CodingRecord.source_id == "pair"))
                assert stored.statement == "Find A < B.\nn ≤ 10^(5)"
            assert datetime.fromisoformat(pair["occurred_at"]).replace(tzinfo=UTC) == datetime.fromtimestamp(1730000100, UTC)
            # Both collectors enter the same pipeline, including missing GFG timestamps.
            gfg_time = "2025-05-01 12:00:00"
            def gfg_handler(request):
                if request.method == "POST":
                    payload = gfg_solved(2)
                    for item in payload["result"]["Medium"].values():
                        item["user_subtime"] = gfg_time
                    return httpx.Response(200, json=payload)
                if "/profile/" in request.url.path:
                    return httpx.Response(200, text=gfg_profile_html(2))
                key = request.url.path.split("/")[2]
                if key == "pair-0":
                    return httpx.Response(200, text=gfg_problem_html(key, "<p>Find A &lt; B.</p><p>n &le; 10<sup>5</sup></p>"))
                return httpx.Response(200, text=gfg_problem_html(key))
            registry._connectors[Platform.GEEKSFORGEEKS] = GeeksForGeeksConnector(0, transport=httpx.MockTransport(gfg_handler))
            linked_gfg = await client.post("/api/v1/platform-profiles", json={"platform": "geeksforgeeks", "handle_or_url": "public_user"})
            gfg_body = {"platform_profile_id": linked_gfg.json()["id"]}
            assert (await client.post("/api/v1/syncs", json=gfg_body)).json()["records_written"] == 2
            assert (await client.post("/api/v1/syncs", json=gfg_body)).json()["records_written"] == 0
            dashboard = (await client.get("/api/v1/dashboard")).json()
            assert dashboard["total_problems_solved"] == 4
            assert dashboard["unique_problems_solved"] == 3  # identical LC/GFG statements group
            assert dashboard["activity"]["unknown_timestamp_records"] == 2
            questions = (await client.get("/api/v1/solved-problems?platform=geeksforgeeks")).json()["items"]
            assert all(item["source_solved_at"] == "2025-05-01T12:00:00" and item["solved_at"] is None for item in questions)
            gfg_time = "2025-06-01 15:00:00"
            assert (await client.post("/api/v1/syncs", json=gfg_body)).json()["status"] == "succeeded"
            questions = (await client.get("/api/v1/solved-problems?platform=geeksforgeeks")).json()["items"]
            assert all(item["source_solved_at"] == "2025-05-01T12:00:00" for item in questions)
            # Losing provider access retains imported data and reports a failed run.
            connector._http.transport = httpx.MockTransport(lambda _: httpx.Response(403))
            failed = (await client.post("/api/v1/syncs", json=sync_body)).json()
            assert failed["status"] == "failed" and failed["error_code"] == "provider_access_denied"
            assert (await client.get("/api/v1/dashboard")).json()["total_problems_solved"] == 4


@pytest.mark.parametrize("platform", [Platform.LEETCODE, Platform.GEEKSFORGEEKS])
async def test_metadata_budget_advances_across_connector_and_database_restarts(tmp_path, platform):
    from profligator_api.connectors.metadata import DatabaseMetadataStore
    from profligator_api.database import Database

    url = f"sqlite:///{tmp_path / 'metadata.db'}"
    requests = []
    data = lc_data(total=4)
    data["recentAcSubmissionList"] = [
        {"id": str(i + 1), "title": f"Pair {i}", "titleSlug": f"pair-{i}", "timestamp": "1730000100"}
        for i in range(4)
    ]
    def handler(request):
        if platform == Platform.LEETCODE:
            body = json.loads(request.content)
            if "username" in body["variables"]:
                return httpx.Response(200, json={"data": data})
            key = body["variables"]["titleSlug"]
            requests.append(key)
            # A unavailable/premium problem must not monopolize future budgets.
            return httpx.Response(200, json={"data": {"question": {
                "titleSlug": key, "title": key, "difficulty": "Easy",
                "content": "<p>Public statement</p>", "isPaidOnly": key == "pair-0", "topicTags": [],
            }}})
        if request.method == "POST":
            return httpx.Response(200, json=gfg_solved(4))
        if "/profile/" in request.url.path:
            return httpx.Response(200, text=gfg_profile_html(4))
        key = request.url.path.split("/")[2]
        requests.append(key)
        return httpx.Response(401) if key == "pair-0" else httpx.Response(200, text=gfg_problem_html(key))

    counts = []
    for budget in (2, 2, 0):
        database = Database(url)
        database.initialize()
        cls = LeetCodeConnector if platform == Platform.LEETCODE else GeeksForGeeksConnector
        connector = cls(0, budget, transport=httpx.MockTransport(handler),
                        metadata_store=DatabaseMetadataStore(database))
        canonical = await connector.validate_handle("public_user")
        await connector.fetch_profile(canonical)
        rows = (await connector.fetch_solved_records(canonical)).records
        assert len(rows) == 4 and rows[0].statement is None
        counts.append(sum(row.statement is not None for row in rows))
        database.dispose()
    assert counts == [1, 3, 3]
    assert requests == ["pair-0", "pair-1", "pair-2", "pair-3"]


async def test_metadata_prioritizes_unchecked_then_oldest_and_preserves_cache_on_failure(tmp_path):
    from profligator_api.connectors.metadata import DatabaseMetadataStore, MetadataEntry
    from profligator_api.database import Database
    import time

    database = Database(f"sqlite:///{tmp_path / 'progress.db'}")
    database.initialize()
    store = DatabaseMetadataStore(database)
    now = time.time()
    store.save("Test", "old", MetadataEntry(now - 200000, {"title": "Old"}))
    store.save("Test", "older", MetadataEntry(now - 300000, None))
    store.save("Other", "new", MetadataEntry(now, {"title": "Other provider"}))
    web = PublicWebClient("Test", {"public.test"}, 0, metadata_store=store)
    seen = []
    async def loader(key):
        seen.append(key)
        return {"title": key}
    keys = ["old", "older", "new"]
    first = await web.problem_metadata(keys, loader, 1)
    assert seen == ["new"] and first["old"] == {"title": "Old"}
    await web.problem_metadata(keys, loader, 1)
    assert seen == ["new", "older"]
    before = store.load("Test", keys)
    async def failed(key):
        raise ConnectorError("provider_rate_limited", "Try later")
    with pytest.raises(ConnectorError):
        await web.problem_metadata(keys, failed, 1)
    assert store.load("Test", keys) == before
    # A delayed worker cannot regress a fresher cached result.
    store.save("Test", "new", MetadataEntry(now - 400000, None))
    assert store.load("Test", ["new"])["new"] == before["new"]
    database.dispose()


async def test_sync_jobs_persist_and_resume_problem_enrichment(tmp_path, monkeypatch):
    import profligator_api.connectors.registry as registry_module
    from sqlalchemy import select
    from profligator_api.models import CodingRecord, ProblemMetadata

    requests = []
    data = lc_data(total=2)
    def handler(request):
        body = json.loads(request.content)
        if "titleSlug" in body["variables"]:
            requests.append(body["variables"]["titleSlug"])
        else:
            return httpx.Response(200, json={"data": data})
        return lc_handler(request)
    def factory(interval, budget, **kwargs):
        return LeetCodeConnector(0, budget, transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(registry_module, "LeetCodeConnector", factory)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'sync-cache.db'}",
                        scraper_statement_limit=1, profile_sync_cooldown_seconds=0)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post("/api/v1/auth/register", json={
                "email": "progress@example.com", "handle": "progress_user", "password": "test-password-123",
            })
            assert response.status_code == 201
            linked = await client.post("/api/v1/platform-profiles", json={
                "platform": "leetcode", "handle_or_url": "public_user",
            })
            body = {"platform_profile_id": linked.json()["id"]}
            for expected_checks in (1, 2, 2):
                sync = (await client.post("/api/v1/syncs", json=body)).json()
                assert sync["status"] == "succeeded"
                with app.state.database.session() as session:
                    assert len(list(session.scalars(select(ProblemMetadata)))) == expected_checks
                    pair = session.scalar(select(CodingRecord).where(CodingRecord.source_id == "pair"))
                    assert pair.statement == "Find A < B.\nn ≤ 10^(5)"
            assert requests == ["pair", "locked"]
            # A smaller recent window must still reconcile against saved history.
            data["recentAcSubmissionList"] = data["recentAcSubmissionList"][:1]
            sync = (await client.post("/api/v1/syncs", json=body)).json()
            assert sync["status"] == "succeeded"
            dashboard = (await client.get("/api/v1/dashboard")).json()
            assert dashboard["platforms"][0]["solved"] == 2
            assert dashboard["platforms"][0]["history_complete"] is True
            # A changed source total is reported as a mismatch, retaining records.
            data["matchedUser"]["submitStatsGlobal"]["acSubmissionNum"][0]["count"] = 1
            assert (await client.post("/api/v1/syncs", json=body)).json()["status"] == "succeeded"
            dashboard = (await client.get("/api/v1/dashboard")).json()
            assert dashboard["platforms"][0]["solved"] == 2
            assert dashboard["platforms"][0]["history_complete"] is False

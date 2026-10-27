from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from profligator_api.connectors.codeforces import CodeforcesConnector
from profligator_api.connectors.base import ConnectorError
from profligator_api.connectors.geeksforgeeks import GeeksForGeeksConnector
from profligator_api.connectors.metadata import DatabaseMetadataStore
from profligator_api.connectors.problem_html import problem_html
from profligator_api.connectors.public_web import statement_text
from profligator_api.database import Database
from profligator_api.models import CodingRecord, ProblemMetadata
from profligator_api.repository import Repository
from profligator_api.schemas import NormalizedRecord
from profligator_api.schemas import Platform
from test_extension_history import link, token_headers


def test_statement_containers_preserve_examples_constraints_and_images():
    html = '<nav>Not a statement</nav><div class="problem-statement"><div class="header"><div class="title">A. Title</div><div class="time-limit">time limit per test: 2 seconds</div><div class="memory-limit">memory limit per test: 256 megabytes</div></div><p>Find x &lt; n.</p><div class="input-specification">Input: n &le; 10<sup>5</sup></div><div class="output-specification">Output: x</div><pre>1 2<br>3 4</pre><img src="/diagram.png" alt="Graph"></div><textarea>private code</textarea>'
    text = statement_text(problem_html(html, "codeforces"))
    assert "Find x < n." in text and "10^(5)" in text and "Output: x" in text
    assert "1 2\n3 4" in text and "[image: /diagram.png Graph]" in text
    assert "Title" not in text and "Not a statement" not in text and "private code" not in text
    assert "time limit per test: 2 seconds" in text and "memory limit per test: 256 megabytes" in text
    for html in ['<h1>Sign in</h1>', '<div class="problem-statement">incomplete',
                 '<div class="problem-statement">One</div><div class="problem-statement">Two</div>']:
        assert problem_html(html, "codeforces") is None
    assert statement_text(problem_html('<div class="problem-statement"><svg><path></path></svg></div>', "codeforces")) is None
    assert statement_text('<p>Authentication required</p>') is None
    assert "https://codeforces.com/image.png" in statement_text('<p>Diagram</p><img src="/image.png">', base_url="https://codeforces.com/problemset/problem/4/A")


async def test_codeforces_statement_budget_cache_and_gym_identity(tmp_path):
    url = f"sqlite:///{tmp_path / 'cf-metadata.db'}"
    requests = []
    def handler(request):
        requests.append(request.url.path)
        if request.url.path.endswith("/B"):
            return httpx.Response(404)
        return httpx.Response(200, text='<div class="problem-statement"><p>Find n.</p><div class="input-specification">Input n.</div><div class="output-specification">Output n.</div></div>')
    rows = [NormalizedRecord(platform="codeforces", source_id=key, kind="problem", status="solved", title=key,
        canonical_url=CodeforcesConnector.problem_url(key), occurred_at=datetime(2024, 1, 1, tzinfo=UTC),
        source_payload_checksum=key) for key in ["4-A", "4-B", "100001-A"]]
    for index in range(3):
        database = Database(url)
        database.initialize()
        connector = CodeforcesConnector(min_interval_seconds=0, transport=httpx.MockTransport(handler),
                                         metadata_store=DatabaseMetadataStore(database))
        updates = await connector.enrich_records(rows, 1)
        rows = [next((new for new in updates if new.source_id == row.source_id), row) for row in rows]
        assert all(row.occurred_at.year == 2024 for row in rows)
        database.dispose()
    assert requests == ["/problemset/problem/4/A", "/problemset/problem/4/B", "/gym/100001/problem/A"]
    assert sum(bool(row.statement) for row in rows) == 2
    gym = CodeforcesConnector.parse_submissions([
        {"id": 456, "verdict": "OK", "creationTimeSeconds": 1704153600,
         "problem": {"contestId": 100001, "index": "A", "name": "Gym question"}},
        {"id": 123, "verdict": "OK", "creationTimeSeconds": 1704067200,
         "problem": {"contestId": 100001, "index": "A", "name": "Gym question"}},
    ]).records[0]
    assert gym.submission_url == "https://codeforces.com/gym/100001/submission/123"
    assert gym.occurred_at == datetime(2024, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("status,code", [(400, "profile_not_found"), (403, "provider_access_denied"), (429, "provider_rate_limited")])
async def test_codeforces_profile_checks_handle_missing_or_blocked_accounts(client, status, code):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(status, json={"status": "FAILED", "comment": "User not found"})
    client._transport.app.state.connectors._connectors[Platform.CODEFORCES] = CodeforcesConnector(
        min_interval_seconds=0, transport=httpx.MockTransport(handler))
    response = await client.post("/api/v1/platform-profiles/check", json={"platform": "codeforces", "handle_or_url": "missing_user"})
    assert response.status_code == 422 and response.json()["error"]["code"] == code
    assert calls == ["/api/user.info"]


async def test_problem_redirect_cannot_attach_another_questions_text():
    def handler(request):
        if request.url.path.endswith("/4/A"):
            return httpx.Response(302, headers={"location": "https://codeforces.com/problemset/problem/71/A"})
        return httpx.Response(200, text='<div class="problem-statement"><p>Different problem</p></div>')
    connector = CodeforcesConnector(min_interval_seconds=0, transport=httpx.MockTransport(handler))
    with pytest.raises(ConnectorError, match="different problem page"):
        await connector._problem("4-A")


async def test_gfg_falls_back_to_visible_statement_without_next_data():
    connector = GeeksForGeeksConnector(0, transport=httpx.MockTransport(lambda request: httpx.Response(200,
        text='<div class="problems_problem_content__123"><p>Find the pair.</p><pre>Input: [1,2], target=3</pre><p>Output: true</p></div><textarea>Private solution</textarea>')))
    metadata = await connector._problem("key-pair5616")
    text = statement_text(metadata["problem_question"])
    assert "Input: [1,2], target=3" in text and "Output: true" in text and "Private solution" not in text


@pytest.mark.parametrize("platform,key,url", [
    ("leetcode", "two-sum", "https://leetcode.com/problems/two-sum/"),
    ("geeksforgeeks", "key-pair5616", "https://www.geeksforgeeks.org/problems/key-pair5616/1"),
    ("codeforces", "4-A", "https://codeforces.com/problemset/problem/4/A"),
])
async def test_visible_text_only_enriches_owned_existing_solves(client, platform, key, url):
    profile = await link(client, platform, "extension_test")
    headers = await token_headers(client)
    payload = {"platform": platform, "source_id": key, "statement": "Public text. Input: n. Output: n.", "topics": ["Array"], "public_statement": True}
    path = "/api/v1/extension/history/metadata"
    assert (await client.post(path, json=payload)).status_code == 401
    assert (await client.post(path, headers=headers, json=payload)).json()["status"] == "not_in_history"
    assert (await client.get("/api/v1/solved-problems")).json()["total"] == 0
    database = client._transport.app.state.database
    with database.session() as session:
        Repository(session).upsert_records(profile["id"], [NormalizedRecord(platform=platform, source_id=key,
            kind="problem", status="solved", title="A solved question", canonical_url=url,
            occurred_at=None, source_payload_checksum="owner-history")])
    response = await client.post(path, headers=headers, json=payload)
    assert response.status_code == 200 and response.json()["metadata_records_written"] == 1
    assert (await client.post(path, headers=headers, json=payload)).json()["metadata_records_written"] == 0
    with database.session() as session:
        row = session.scalar(select(CodingRecord))
        assert row.statement == payload["statement"] and row.topics == ["Array"] and row.occurred_at is None
        assert list(session.scalars(select(ProblemMetadata))) == []  # Owner text is not shared cached metadata.
    dashboard = (await client.get("/api/v1/dashboard")).json()
    assert dashboard["records_with_statements"] == 1 and dashboard["semantic_matching"] == "disabled"
    assert dashboard["platforms"][0]["questions_with_utc_dates"] == 0
    shared = (await client.put("/api/v1/sharing", json={"enabled": True})).json()["shareable_link"].rsplit("/", 1)[-1]
    public = (await client.get(f"/api/v1/public-profiles/{shared}/solved-problems")).json()["items"][0]
    assert public["has_statement"] is True and "statement" not in public and "matching_state" not in public
    for extra in [{"solved_at": "2025-01-01T08:00:00Z"}, {"code": "private code"}, {"cookies": "private"}, {"public_statement": False}, {"source_id": "../question"}]:
        assert (await client.post(path, headers=headers, json={**payload, **extra})).status_code == 422
    await client.delete(f"/api/v1/platform-profiles/{profile['id']}")
    assert (await client.post(path, headers=headers, json=payload)).json()["status"] == "not_in_history"

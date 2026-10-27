from datetime import UTC, datetime

import httpx
import pytest

from profligator_api.connectors.aggregation_service import AggregationServiceConnector
from profligator_api.connectors.base import ConnectorError
from profligator_api.connectors.codeforces import CodeforcesConnector
from profligator_api.schemas import Platform


async def test_codeforces_imports_rated_contests_and_original_submission_urls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/user.rating")
        assert request.url.params["handle"] == "tourist"
        return httpx.Response(200, json={"status": "OK", "result": [{"contestId": 123, "contestName": "A round", "rank": 3, "newRating": 2900, "ratingUpdateTimeSeconds": 1728000000}]})
    connector = CodeforcesConnector(min_interval_seconds=0, transport=httpx.MockTransport(handler))
    profile = await connector.validate_handle("tourist")
    page = await connector.fetch_contests(profile)
    record = page.records[0]
    assert record.kind == "contest"
    assert record.contest_rating == 2900
    assert record.global_rank == 3
    assert record.canonical_url == "https://codeforces.com/contest/123"


async def test_aggregation_service_reports_partial_history_and_validates_identity() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/records"):
            assert request.url.params["kind"] == "problem"
            return httpx.Response(200, json={"records": [{"platform": "leetcode", "source_id": "1", "kind": "problem", "status": "solved", "title": "Pair", "canonical_url": "https://leetcode.com/problems/pair/", "source_payload_checksum": "checksum"}], "next_cursor": "page2"})
        return httpx.Response(200, json={"profile": {"platform": "leetcode", "handle": "public_user", "canonical_url": "https://leetcode.com/u/public_user/"}, "fetched_at": datetime.now(UTC).isoformat(), "source_total_solved": 500, "history_complete": False})
    connector = AggregationServiceConnector(Platform.LEETCODE, "http://service.test", transport=httpx.MockTransport(handler))
    profile = await connector.validate_handle("public_user")
    snapshot = await connector.fetch_profile(profile)
    assert snapshot.source_total_solved == 500
    assert snapshot.history_complete is False
    page = await connector.fetch_solved_records(profile)
    assert len(page.records) == 1
    assert page.next_cursor == "page2"
    connector.transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"profile": {"platform": "leetcode", "handle": "different_user", "canonical_url": "https://leetcode.com/u/different_user/"}, "fetched_at": datetime.now(UTC).isoformat()}))
    with pytest.raises(ConnectorError, match="different coding profile"):
        await connector.fetch_profile(profile)


async def test_matching_evaluation_reports_errors_and_false_positives() -> None:
    from profligator_api.evaluate_matching import LabeledPair, evaluate
    from profligator_api.matching import MatchResult, MatchingUnavailable

    class Provider:
        name = "test"
        model = "test-model"
        async def compare(self, left, right):
            if left["title"] == "offline":
                raise MatchingUnavailable("offline")
            return MatchResult(duplicate=True, confidence=0.99, reason="test")
    pairs = [
        LabeledPair(id="false-positive", left={"title": "A"}, right={"title": "B"}, duplicate=False),
        LabeledPair(id="provider-error", left={"title": "offline"}, right={"title": "B"}, duplicate=True),
    ]
    report = await evaluate(pairs, Provider(), 0.95)
    assert report["false_positives"] == 1
    assert report["false_negatives"] == 0
    assert report["false_positive_rate"] == 1
    assert report["provider_errors"] == 1
    assert report["evaluated_pairs"] == 1
    assert report["results"][1]["predicted"] is None

import pytest

from profligator_api.connectors.codeforces import CodeforcesConnector, RequestIntervalLimiter


async def test_codeforces_profile_url_is_canonicalized() -> None:
    connector = CodeforcesConnector(min_interval_seconds=0)
    profile = await connector.validate_handle("https://codeforces.com/profile/tourist")
    assert profile.handle == "tourist"
    assert profile.canonical_url == "https://codeforces.com/profile/tourist"


def test_codeforces_submission_parser_deduplicates_solved_problems() -> None:
    submissions = [
        {
            "id": 2,
            "creationTimeSeconds": 1728000000,
            "verdict": "OK",
            "problem": {
                "contestId": 4,
                "index": "A",
                "name": "Watermelon",
                "rating": 800,
                "tags": ["brute force", "math"],
            },
        },
        {
            "id": 1,
            "creationTimeSeconds": 1727000000,
            "verdict": "OK",
            "problem": {
                "contestId": 4,
                "index": "A",
                "name": "Watermelon",
                "tags": ["brute force", "math"],
            },
        },
        {
            "id": 3,
            "creationTimeSeconds": 1729000000,
            "verdict": "WRONG_ANSWER",
            "problem": {"contestId": 71, "index": "A", "name": "Way Too Long Words"},
        },
    ]

    page = CodeforcesConnector.parse_submissions(submissions)
    assert len(page.records) == 1
    record = page.records[0]
    assert record.source_id == "4-A"
    assert record.title == "Watermelon"
    assert record.difficulty == "Easy"
    assert record.topics == ["brute force", "math"]


async def test_codeforces_rate_limiter_waits_for_remaining_interval() -> None:
    now = [0.0]
    waits: list[float] = []

    def clock() -> float:
        return now[0]

    async def sleep(delay: float) -> None:
        waits.append(delay)
        now[0] += delay

    limiter = RequestIntervalLimiter(2.05, clock=clock, sleep=sleep)
    await limiter.wait()
    now[0] += 0.5
    await limiter.wait()

    assert waits == pytest.approx([1.55])

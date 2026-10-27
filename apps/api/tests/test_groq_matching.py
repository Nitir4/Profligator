import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select

from profligator_api.config import Settings
from profligator_api.database import Database
from profligator_api.evaluate_matching import LabeledPair, evaluate
from profligator_api.groq_matching import GroqMatchProvider, _retry_seconds
from profligator_api.matching import MatchingService, MatchingUnavailable, create_match_provider
from profligator_api.models import MatchDecision
from profligator_api.repository import Repository
from test_report_backend import seed, request


def settings(**values):
    return Settings(_env_file=None, matching_backend="groq", groq_api_key=SecretStr("test-only-key"),
                    groq_min_interval_seconds=0, **values)


def decision(duplicate=True, confidence=0.99):
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps({"duplicate": duplicate, "confidence": confidence, "reason": "Equivalent task"}),
    }}]})


def test_configuration_requires_key_and_keeps_it_secret():
    with pytest.raises(ValidationError, match="PROFLIGATOR_GROQ_API_KEY"):
        Settings(_env_file=None, matching_backend="groq")
    config = settings()
    assert config.matching_model == "openai/gpt-oss-120b"
    assert "test-only-key" not in repr(config)
    assert "test-only-key" not in config.model_dump_json()
    assert isinstance(create_match_provider(config), GroqMatchProvider)


async def test_groq_protocol_and_concurrent_cache_across_instances():
    calls = []
    def handler(req):
        calls.append(req)
        assert str(req.url) == GroqMatchProvider.endpoint
        assert req.headers["authorization"] == "Bearer test-only-key"
        body = json.loads(req.content)
        assert body["model"] == "openai/gpt-oss-120b" and body["stream"] is False
        assert body["reasoning_effort"] == "low" and body["max_completion_tokens"] == 2048
        schema = body["response_format"]["json_schema"]
        assert schema["strict"] is True and schema["schema"]["additionalProperties"] is False
        assert set(schema["schema"]["required"]) == {"duplicate", "confidence", "reason"}
        assert "untrusted" in body["messages"][0]["content"]
        sent = json.loads(body["messages"][1]["content"])
        assert set(sent["left"]) == {"title", "statement", "topics"}
        assert "private@" not in req.content.decode()
        return decision()
    config = settings()
    left = {"title": "Pair", "statement": "Return two indices.", "topics": ["Array"], "email": "private@example.com", "cookies": "private"}
    right = {"statement": "Find a pair of indices."}
    providers = [GroqMatchProvider(config, transport=httpx.MockTransport(handler)) for _ in range(2)]
    results = await asyncio.gather(*(p.compare(left, right) for p in providers))
    assert len(calls) == 1 and all(r.duplicate for r in results)
    results[0].duplicate = False
    assert (await providers[0].compare(left, right)).duplicate


@pytest.mark.parametrize("response", [
    httpx.Response(401, text="secret provider body"), httpx.Response(403), httpx.Response(503),
    httpx.Response(302, headers={"location": "https://untrusted.example/"}),
    httpx.Response(200, text="not json"), httpx.Response(200, json={"choices": []}),
    httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}),
    httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"refusal": "Declined", "content": None}}]}),
    httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"duplicate":"yes","confidence":2,"reason":"bad"}'}}]}),
    httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"duplicate":true,"confidence":1,"reason":"x","extra":1}'}}]}),
])
async def test_errors_invalid_refused_or_incomplete_output_are_unavailable(response):
    provider = GroqMatchProvider(settings(), transport=httpx.MockTransport(lambda _: response))
    with pytest.raises(MatchingUnavailable) as failure:
        await provider.compare({"statement": "Different text"}, {"statement": "Other text"})
    assert "test-only-key" not in str(failure.value) and "secret provider body" not in str(failure.value)


async def test_quota_cooldown_shared_across_new_providers_and_cached_results_survive():
    calls = []
    def handler(req):
        calls.append(req)
        return decision() if len(calls) == 1 else httpx.Response(429, headers={"retry-after": "120"})
    first = GroqMatchProvider(settings(), transport=httpx.MockTransport(handler))
    assert (await first.compare({"statement": "A"}, {"statement": "B"})).duplicate
    with pytest.raises(MatchingUnavailable, match="quota"):
        await first.compare({"statement": "C"}, {"statement": "D"})
    second = GroqMatchProvider(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(MatchingUnavailable, match="rate limited"):
        await second.compare({"statement": "E"}, {"statement": "F"})
    assert (await second.compare({"statement": "A"}, {"statement": "B"})).duplicate
    assert len(calls) == 2
    assert _retry_seconds("120") == 120
    assert _retry_seconds("nan") == 60 and _retry_seconds("invalid") == 60


async def test_oversized_input_is_not_truncated_or_sent():
    provider = GroqMatchProvider(settings(groq_max_input_chars=1000), transport=httpx.MockTransport(
        lambda _: pytest.fail("Oversized text must not be uploaded")))
    with pytest.raises(MatchingUnavailable, match="input budget"):
        await provider.compare({"statement": "x" * 1001}, {"statement": "small"})


async def test_semantic_clusters_persist_reuse_and_failure_preserves_history(tmp_path):
    config = settings(database_url=f"sqlite:///{tmp_path / 'groq.db'}")
    database = Database(config.database_url)
    database.initialize()
    user_id, _ = seed(database, statements=("Return indices for a target sum.", "Find two array positions totaling K."))
    calls = []
    def handler(req):
        calls.append(req)
        return decision()
    provider = GroqMatchProvider(config, transport=httpx.MockTransport(handler))
    matcher = MatchingService(database, config, provider)
    assert await matcher.match_user(user_id) == "complete"
    with database.session() as session:
        data = Repository(session).dashboard(user_id, semantic_matching=True)
        assert data.unique_problems_solved == 1 and data.semantic_matched_records == 2
        assert session.scalar(select(func.count(MatchDecision.id))) == 1
    assert await matcher.match_user(user_id) == "complete" and len(calls) == 1
    unavailable = GroqMatchProvider(config.model_copy(update={"matching_model": "unavailable-model"}),
                                   transport=httpx.MockTransport(lambda _: httpx.Response(429)))
    assert await MatchingService(database, config, unavailable).match_user(user_id) == "unavailable"
    with database.session() as session:
        assert Repository(session).dashboard(user_id).total_problems_solved == 2
    exact = GroqMatchProvider(config, transport=httpx.MockTransport(lambda _: pytest.fail("Exact checks need no API")))
    assert (await MatchingService(database, config, exact).check(user_id, request("Return indices for a target sum."))).status == "exact"
    database.dispose()


async def test_evaluation_reports_provider_errors_as_unknown():
    class Offline:
        name, model = "groq", "test-model"
        async def compare(self, left, right):
            raise MatchingUnavailable("Quota reached")
    pair = LabeledPair(id="unavailable", left={"statement": "A"}, right={"statement": "B"}, duplicate=False)
    report = await evaluate([pair], Offline(), 0.95)
    assert report["provider_errors"] == 1 and report["evaluated_pairs"] == 0
    assert report["true_negatives"] == 0 and report["results"][0]["predicted"] is None

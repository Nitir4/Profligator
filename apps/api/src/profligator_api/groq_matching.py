"""Bounded hosted comparisons with shared pacing, cooldown and response caching."""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import time
from weakref import WeakKeyDictionary

import httpx
from pydantic import ValidationError

from profligator_api.config import Settings
from profligator_api.matching import MatchResult, MatchingUnavailable, comparison_messages


@dataclass
class _State:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_request_at: float = 0
    blocked_until: float = 0
    cache: OrderedDict = field(default_factory=OrderedDict)


_STATES: WeakKeyDictionary = WeakKeyDictionary()


def _retry_seconds(value: str | None) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            instant = parsedate_to_datetime(value)
            seconds = (instant - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return 60
    return max(1, seconds) if math.isfinite(seconds) else 60


class GroqMatchProvider:
    name = "groq"
    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        if not settings.groq_api_key or not settings.groq_api_key.get_secret_value().strip():
            raise ValueError("PROFLIGATOR_GROQ_API_KEY is required for Groq matching")
        self._api_key = settings.groq_api_key
        self.model = settings.matching_model or "openai/gpt-oss-120b"
        self.timeout = settings.matching_timeout_seconds
        self.interval = settings.groq_min_interval_seconds
        self.max_completion_tokens = settings.groq_max_completion_tokens
        self.max_input_chars = settings.groq_max_input_chars
        self.transport = transport
        self.database_url = settings.database_url
        self.pacing_key = "groq:" + hashlib.sha256(self._api_key.get_secret_value().encode()).hexdigest()

    def _state(self) -> _State:
        loop = asyncio.get_running_loop()
        # Neither the credential nor the input text is used as a visible cache key.
        identity = (hashlib.sha256(self._api_key.get_secret_value().encode()).hexdigest(), self.model)
        states = _STATES.setdefault(loop, {})
        return states.setdefault(identity, _State())

    async def compare(self, left: dict, right: dict) -> MatchResult:
        messages = comparison_messages(left, right)
        if len(messages[1]["content"]) > self.max_input_chars:
            raise MatchingUnavailable("Problem text exceeds the Groq comparison input budget")
        payload = {
            "model": self.model, "messages": messages, "stream": False, "temperature": 0,
            "max_completion_tokens": self.max_completion_tokens,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "problem_comparison", "strict": True, "schema": MatchResult.model_json_schema(),
            }},
        }
        if self.model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
            payload["reasoning_effort"] = "low"
        checksum = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        state = self._state()
        async with state.lock:
            now = time.monotonic()
            cached = state.cache.get(checksum)
            if cached and now - cached[0] < 3600:
                state.cache.move_to_end(checksum)
                return cached[1].model_copy()
            if now < state.blocked_until:
                raise MatchingUnavailable("Groq is temporarily unavailable or rate limited; retry later")
            if now < state.next_request_at:
                await asyncio.sleep(state.next_request_at - now)
            state.next_request_at = time.monotonic() + self.interval
            database = None
            try:
                if self.transport is None:
                    from profligator_api.database import Database
                    from profligator_api.coordination import pace_request
                    database = Database(self.database_url)
                    await pace_request(database, self.pacing_key, self.interval)
                async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport, follow_redirects=False) as client:
                    response = await client.post(self.endpoint, json=payload, headers={
                        "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                    })
                if response.status_code == 429:
                    cooldown = _retry_seconds(response.headers.get("retry-after"))
                    state.blocked_until = time.monotonic() + cooldown
                    if database is not None:
                        from profligator_api.coordination import defer_requests
                        defer_requests(database, self.pacing_key, cooldown)
                    raise MatchingUnavailable("Groq quota reached; retry after the provider cooldown")
                if response.status_code != 200:
                    state.blocked_until = time.monotonic() + 60
                    raise MatchingUnavailable(f"Groq request failed (HTTP {response.status_code})")
                body = response.json()
                choice = body["choices"][0]
                if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
                    raise MatchingUnavailable("Groq declined the comparison or returned incomplete output")
                result = MatchResult.model_validate_json(choice["message"]["content"])
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError, ValidationError):
                state.blocked_until = time.monotonic() + 10
                # Raw errors/bodies may echo credentials or prompts; never propagate them.
                raise MatchingUnavailable("Groq could not complete a valid comparison") from None
            finally:
                if database is not None:
                    database.dispose()
            state.cache[checksum] = (time.monotonic(), result)
            state.cache.move_to_end(checksum)
            while len(state.cache) > 1024:
                state.cache.popitem(last=False)
            return result.model_copy()

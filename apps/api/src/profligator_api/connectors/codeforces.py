import asyncio
from datetime import UTC, datetime
import re
import time
from typing import Awaitable, Callable
from urllib.parse import quote, urlparse

import httpx

from profligator_api.connectors.base import Connector, ConnectorError, payload_checksum
from profligator_api.schemas import (
    CanonicalProfile,
    ConnectorDescriptor,
    ConnectorMode,
    ConnectorPage,
    NormalizedRecord,
    Platform,
    ProfileSnapshot,
    RecordKind,
    RecordStatus,
)


_HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,24}$")


class RequestIntervalLimiter:
    def __init__(
        self,
        interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.interval_seconds = interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last_request_at: float | None = None

    async def wait(self) -> None:
        async with self._lock:
            now = self._clock()
            if self._last_request_at is not None:
                remaining = self.interval_seconds - (now - self._last_request_at)
                if remaining > 0:
                    await self._sleep(remaining)
            self._last_request_at = self._clock()


class CodeforcesConnector(Connector):
    descriptor = ConnectorDescriptor(
        platform=Platform.CODEFORCES,
        mode=ConnectorMode.OFFICIAL_API,
        live_data=True,
        notice="Uses the official public Codeforces API with a conservative request interval.",
    )

    def __init__(
        self,
        base_url: str = "https://codeforces.com/api",
        min_interval_seconds: float = 2.05,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._limiter = RequestIntervalLimiter(min_interval_seconds)
        self._transport = transport

    async def validate_handle(self, handle_or_url: str) -> CanonicalProfile:
        value = handle_or_url.strip().rstrip("/")
        if "://" in value:
            parsed = urlparse(value)
            host = parsed.netloc.lower().removeprefix("www.")
            if host not in {"codeforces.com", "mirror.codeforces.com"}:
                raise ConnectorError("invalid_profile_url", "Expected a codeforces.com profile URL")
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) < 2 or parts[0] != "profile":
                raise ConnectorError("invalid_profile_url", "Expected a /profile/{handle} URL")
            handle = parts[1]
        else:
            handle = value

        if not _HANDLE_PATTERN.fullmatch(handle):
            raise ConnectorError("invalid_handle", "The Codeforces handle format is invalid")

        return CanonicalProfile(
            platform=Platform.CODEFORCES,
            handle=handle,
            canonical_url=f"https://codeforces.com/profile/{quote(handle)}",
            display_name=handle,
        )

    async def _get(self, method: str, params: dict[str, object]) -> object:
        await self._limiter.wait()
        timeout = httpx.Timeout(10.0, connect=5.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            transport=self._transport,
            headers={"User-Agent": "Profligator/0.1 (+profile aggregation student project)"},
        ) as client:
            try:
                response = await client.get(f"{self.base_url}/{method}", params=params)
                response.raise_for_status()
            except httpx.TimeoutException as exc:
                raise ConnectorError("provider_timeout", "Codeforces timed out", retryable=True) from exc
            except httpx.HTTPError as exc:
                raise ConnectorError(
                    "provider_http_error", "Codeforces could not be reached", retryable=True
                ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError(
                "invalid_provider_response", "Codeforces returned invalid JSON", retryable=True
            ) from exc
        if not isinstance(payload, dict):
            raise ConnectorError(
                "invalid_provider_response", "Codeforces returned an unexpected response"
            )
        if payload.get("status") != "OK":
            comment = payload.get("comment", "Codeforces returned an error")
            code = "profile_not_found" if "not found" in comment.lower() else "provider_error"
            raise ConnectorError(code, comment, retryable=code == "provider_error")
        return payload["result"]

    async def fetch_profile(self, profile: CanonicalProfile) -> ProfileSnapshot:
        result = await self._get("user.info", {"handles": profile.handle})
        if not isinstance(result, list) or not result:
            raise ConnectorError("profile_not_found", "Codeforces profile was not found")
        user = result[0]
        display_name = " ".join(
            value for value in (user.get("firstName"), user.get("lastName")) if value
        ) or user["handle"]
        canonical = profile.model_copy(
            update={"handle": user["handle"], "display_name": display_name}
        )
        return ProfileSnapshot(
            profile=canonical,
            fetched_at=datetime.now(UTC),
            rating=user.get("rating"),
            rank=user.get("rank"),
        )

    async def fetch_solved_records(
        self, profile: CanonicalProfile, cursor: str | None = None
    ) -> ConnectorPage:
        start = int(cursor or "1")
        result = await self._get(
            "user.status", {"handle": profile.handle, "from": start, "count": 1000}
        )
        if not isinstance(result, list):
            raise ConnectorError("invalid_provider_response", "Unexpected Codeforces response")
        return self.parse_submissions(result, start=start)

    @staticmethod
    def parse_submissions(submissions: list[dict[str, object]], *, start: int = 1) -> ConnectorPage:
        solved: dict[str, NormalizedRecord] = {}
        for submission in submissions:
            if submission.get("verdict") != "OK":
                continue
            problem = submission.get("problem")
            if not isinstance(problem, dict):
                continue
            contest_id = problem.get("contestId")
            index = problem.get("index")
            name = problem.get("name")
            if contest_id is None or not index or not name:
                continue
            source_id = f"{contest_id}-{index}"
            if source_id in solved:
                continue
            url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
            occurred_at = None
            if isinstance(submission.get("creationTimeSeconds"), int):
                occurred_at = datetime.fromtimestamp(submission["creationTimeSeconds"], UTC)
            tags = problem.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            rating = problem.get("rating")
            difficulty = None
            if isinstance(rating, int):
                difficulty = "Easy" if rating <= 1200 else "Medium" if rating <= 1900 else "Hard"
            normalized_payload = {
                "id": submission.get("id"),
                "contestId": contest_id,
                "index": index,
                "name": name,
                "tags": tags,
                "rating": rating,
                "creationTimeSeconds": submission.get("creationTimeSeconds"),
            }
            solved[source_id] = NormalizedRecord(
                platform=Platform.CODEFORCES,
                source_id=source_id,
                kind=RecordKind.PROBLEM,
                status=RecordStatus.SOLVED,
                title=str(name),
                canonical_url=url,
                difficulty=difficulty,
                topics=[str(tag) for tag in tags],
                occurred_at=occurred_at,
                source_payload_checksum=payload_checksum(normalized_payload),
            )
        next_cursor = str(start + len(submissions)) if len(submissions) == 1000 else None
        return ConnectorPage(records=list(solved.values()), next_cursor=next_cursor)

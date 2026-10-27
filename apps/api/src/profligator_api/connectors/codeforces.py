import asyncio
from datetime import UTC, datetime
import re
import time
from typing import Awaitable, Callable
from urllib.parse import quote, urlparse

import httpx

from profligator_api.connectors.base import Connector, ConnectorError, payload_checksum
from profligator_api.connectors.metadata import MetadataStore
from profligator_api.connectors.problem_html import problem_html
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
    supports_problem_metadata = True
    descriptor = ConnectorDescriptor(
        platform=Platform.CODEFORCES,
        mode=ConnectorMode.OFFICIAL_API,
        live_data=True,
        notice="Uses the official public Codeforces API for solved questions and observed acceptance dates, plus bounded public problem-page enrichment. Unavailable pages retain saved history.",
    )

    def __init__(
        self,
        base_url: str = "https://codeforces.com/api",
        min_interval_seconds: float = 2.05,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        metadata_store: MetadataStore | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._limiter = RequestIntervalLimiter(min_interval_seconds)
        self._transport = transport
        # Imported here because PublicWebClient shares this module's request limiter.
        from profligator_api.connectors.public_web import PublicWebClient
        self._http = PublicWebClient("Codeforces", {"codeforces.com"}, min_interval_seconds,
                                     transport=transport, metadata_store=metadata_store)

    @staticmethod
    def problem_url(source_id: str) -> str:
        match = re.fullmatch(r"([1-9][0-9]*)-([A-Z][0-9]?)", source_id)
        if not match:
            raise ConnectorError("invalid_problem_identity", "Invalid Codeforces problem identity")
        contest, index = match.groups()
        return (f"https://codeforces.com/gym/{contest}/problem/{index}" if int(contest) >= 100000
                else f"https://codeforces.com/problemset/problem/{contest}/{index}")

    async def _problem(self, source_id: str) -> dict | None:
        from profligator_api.connectors.public_web import statement_text
        await self._limiter.wait()
        response = await self._http.request("GET", self.problem_url(source_id), optional=True)
        if response:
            path = response.url.path
            match = re.fullmatch(r"/problemset/problem/([0-9]+)/([A-Z][0-9]?)/?", path) or re.fullmatch(
                r"/(?:contest|gym)/([0-9]+)/problem/([A-Z][0-9]?)/?", path)
            if not match or "-".join(match.groups()) != source_id:
                raise ConnectorError("invalid_provider_response", "Codeforces returned a different problem page")
        statement = statement_text(problem_html(response.text, "codeforces"), base_url=str(response.url)) if response else None
        return {"statement": statement} if statement else None

    async def enrich_records(self, records: list[NormalizedRecord], limit: int) -> list[NormalizedRecord]:
        eligible = [row for row in records if row.platform == Platform.CODEFORCES
                    and row.kind == RecordKind.PROBLEM and row.status == RecordStatus.SOLVED]
        metadata = await self._http.problem_metadata([row.source_id for row in eligible], self._problem, limit)
        updated = []
        for row in eligible:
            statement = (metadata.get(row.source_id) or {}).get("statement")
            if statement and statement != row.statement:
                result = row.model_copy(update={"statement": statement})
                result.source_payload_checksum = payload_checksum(result.model_dump(mode="json", exclude={"source_payload_checksum"}))
                updated.append(result)
        return updated

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
        await self._http.pace()
        await self._limiter.wait()
        timeout = httpx.Timeout(10.0, connect=5.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            transport=self._transport,
            headers={"User-Agent": "Profligator/0.1 (+profile aggregation student project)"},
        ) as client:
            try:
                response = await client.get(f"{self.base_url}/{method}", params=params)
                if response.status_code in {401, 403, 429}:
                    raise ConnectorError("provider_rate_limited" if response.status_code == 429 else "provider_access_denied",
                                         "Codeforces declined collection; try a later sync")
                # Invalid handles produce a structured FAILED result (HTTP 400).
                if response.status_code != 400:
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
            if not isinstance(comment, str):
                raise ConnectorError("invalid_provider_response", "Codeforces returned an invalid error")
            code = "profile_not_found" if "not found" in comment.lower() else "provider_error"
            raise ConnectorError(code, comment, retryable=code == "provider_error")
        if "result" not in payload:
            raise ConnectorError("invalid_provider_response", "Codeforces returned no result")
        return payload["result"]

    async def fetch_profile(self, profile: CanonicalProfile) -> ProfileSnapshot:
        result = await self._get("user.info", {"handles": profile.handle})
        if not isinstance(result, list) or not result:
            raise ConnectorError("profile_not_found", "Codeforces profile was not found")
        user = result[0]
        if not isinstance(user, dict) or not isinstance(user.get("handle"), str) or user["handle"].casefold() != profile.handle.casefold():
            raise ConnectorError("invalid_provider_response", "Codeforces returned a different account")
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

    async def fetch_contests(
        self, profile: CanonicalProfile, cursor: str | None = None
    ) -> ConnectorPage:
        result = await self._get("user.rating", {"handle": profile.handle})
        if not isinstance(result, list):
            raise ConnectorError("invalid_provider_response", "Unexpected Codeforces contest history")
        records = []
        for item in result:
            if not isinstance(item, dict) or "contestId" not in item:
                raise ConnectorError("invalid_provider_response", "Invalid Codeforces contest record")
            records.append(NormalizedRecord(
                platform=Platform.CODEFORCES, source_id=str(item["contestId"]),
                kind=RecordKind.CONTEST, status=RecordStatus.PARTICIPATED,
                title=item.get("contestName", f"Contest {item['contestId']}"),
                canonical_url=f"https://codeforces.com/contest/{item['contestId']}",
                occurred_at=datetime.fromtimestamp(item["ratingUpdateTimeSeconds"], UTC)
                if isinstance(item.get("ratingUpdateTimeSeconds"), int) else None,
                contest_rating=item.get("newRating"), global_rank=item.get("rank"),
                source_payload_checksum=payload_checksum(item),
            ))
        # user.rating is one complete result; callers still use a uniform paginated contract.
        start = int(cursor or "0")
        return ConnectorPage(
            records=records[start:start + 1000],
            next_cursor=str(start + 1000) if start + 1000 < len(records) else None,
        )

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
            try:
                url = CodeforcesConnector.problem_url(source_id)
            except ConnectorError:
                continue
            submission_url = (
                f"https://codeforces.com/{'gym' if int(contest_id) >= 100000 else 'contest'}/{contest_id}/submission/{submission['id']}"
                if isinstance(submission.get("id"), int) else None
            )
            occurred_at = None
            if isinstance(submission.get("creationTimeSeconds"), int):
                occurred_at = datetime.fromtimestamp(submission["creationTimeSeconds"], UTC)
            if source_id in solved:
                previous = solved[source_id]
                if occurred_at is not None and (previous.occurred_at is None or occurred_at < previous.occurred_at):
                    previous.occurred_at = occurred_at
                    previous.submission_url = submission_url
                    previous.source_payload_checksum = payload_checksum(
                        previous.model_dump(mode="json", exclude={"source_payload_checksum"})
                    )
                continue
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
                submission_url=submission_url,
            )
        next_cursor = str(start + len(submissions)) if len(submissions) == 1000 else None
        return ConnectorPage(records=list(solved.values()), next_cursor=next_cursor)

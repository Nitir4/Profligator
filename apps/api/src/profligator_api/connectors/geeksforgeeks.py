"""Collect GFG's public profile and its public solved-problem response."""

from datetime import UTC, datetime
import re

import httpx

from profligator_api.connectors.base import Connector, ConnectorError, payload_checksum
from profligator_api.connectors.metadata import MetadataStore
from profligator_api.connectors.problem_html import problem_html
from profligator_api.connectors.public_web import (
    PublicWebClient, embedded_json, integer, invalid_response, objects, page_start,
    public_profile, slug, statement_text, timestamp,
    source_local_time,
)
from profligator_api.schemas import (
    CanonicalProfile, ConnectorDescriptor, ConnectorMode, ConnectorPage,
    NormalizedRecord, Platform, ProfileSnapshot, RecordKind, RecordStatus,
)


class GeeksForGeeksConnector(Connector):
    supports_problem_metadata = True
    descriptor = ConnectorDescriptor(
        platform=Platform.GEEKSFORGEEKS, mode=ConnectorMode.SCRAPER, live_data=True,
        notice="Public profile and solved-problem collector. Coverage is checked against the source total. Some statements and submission dates are unavailable; contest history is unavailable.",
    )

    def __init__(self, min_interval_seconds: float = 2.05, statement_limit: int = 20, *,
                 transport: httpx.AsyncBaseTransport | None = None,
                 metadata_store: MetadataStore | None = None) -> None:
        self._http = PublicWebClient("GeeksforGeeks", {
            "www.geeksforgeeks.org", "geeksforgeeks.org", "practiceapi.geeksforgeeks.org",
        }, min_interval_seconds, transport=transport, metadata_store=metadata_store)
        self._statement_limit = statement_limit
        self._profiles: dict[str, tuple[dict, dict]] = {}
        self._records: dict[str, list[NormalizedRecord]] = {}

    async def validate_handle(self, handle_or_url: str) -> CanonicalProfile:
        return public_profile(Platform.GEEKSFORGEEKS, handle_or_url)

    @staticmethod
    def parse_profile(html: str, handle: str) -> dict:
        for document in embedded_json(html):
            for item in objects(document):
                # The public /profile/ page carries this data in its Flight stream.
                if "username" in item and "articleCount" in item:
                    if not isinstance(item["username"], str) or item["username"].casefold() != handle.casefold():
                        raise invalid_response("GFG returned a different user's profile")
                    data = item["articleCount"]
                    if not isinstance(data, dict) or integer(data.get("total_problems_solved")) is None:
                        raise invalid_response("GFG solved totals are unavailable")
                    if data.get("practice_course_visibility") is False:
                        raise ConnectorError("profile_private", "GFG coding history is private")
                    return data
        raise invalid_response("GFG public profile format changed or coding statistics are private")

    @staticmethod
    def parse_solved(payload: dict) -> list[tuple[str, dict]]:
        if payload.get("status") != "success":
            raise ConnectorError("provider_error", "GFG public solved history is unavailable")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise invalid_response("GFG returned an invalid solved-problem list")
        values: dict[str, tuple[str, dict]] = {}
        for difficulty, problems in result.items():
            if difficulty not in {"School", "Basic", "Easy", "Medium", "Hard"} or not isinstance(problems, dict):
                raise invalid_response("GFG returned an unexpected difficulty bucket")
            for item in problems.values():
                if not isinstance(item, dict) or not isinstance(item.get("pname"), str) or not item["pname"]:
                    raise invalid_response("GFG returned an invalid solved problem")
                key = slug(item.get("slug"))
                previous = values.get(key)
                current_time = timestamp(item.get("user_subtime"))
                previous_time = timestamp(previous[1].get("user_subtime")) if previous else None
                current_local = source_local_time(item.get("user_subtime"))
                previous_local = source_local_time(previous[1].get("user_subtime")) if previous else None
                if (previous is None or (current_time and (previous_time is None or current_time < previous_time))
                        or (current_time is None and previous_time is None and current_local and previous_local
                            and current_local < previous_local)):
                    values[key] = (difficulty, item)
        return list(values.values())

    async def _load(self, profile: CanonicalProfile, *, refresh: bool = False) -> tuple[dict, dict]:
        if refresh or profile.handle not in self._profiles:
            response = await self._http.request("GET", f"https://www.geeksforgeeks.org/profile/{profile.handle}")
            info = self.parse_profile(response.text, profile.handle)
            response = await self._http.request(
                "POST", "https://practiceapi.geeksforgeeks.org/api/v1/user/problems/submissions/",
                json_body={"handle": profile.handle, "requestType": "", "year": "", "month": ""},
            )
            solved = self._http.json(response)
            self.parse_solved(solved)
            if len(self._profiles) >= 16:
                self._profiles.clear()
                self._records.clear()
            self._profiles[profile.handle] = (info, solved)
            self._records.pop(profile.handle, None)
        return self._profiles[profile.handle]

    async def fetch_profile(self, profile: CanonicalProfile) -> ProfileSnapshot:
        info, solved = await self._load(profile, refresh=True)
        total = integer(info.get("total_problems_solved"))
        if total is None or total < 0:
            raise invalid_response("GFG returned an invalid solved total")
        count = len(self.parse_solved(solved))
        canonical = profile.model_copy(update={"display_name": info.get("name") or profile.handle})
        # Institute rank and coding score are not global rank or contest rating.
        return ProfileSnapshot(
            profile=canonical, fetched_at=datetime.now(UTC), source_total_solved=total,
            rating=None, rank=None, history_complete=count == total,
        )

    @staticmethod
    def parse_problem(html: str, problem_slug: str) -> dict | None:
        for document in embedded_json(html):
            for item in objects(document):
                if "problem_question" in item and "slug" in item:
                    if item["slug"] != problem_slug:
                        raise invalid_response("GFG returned metadata for a different problem")
                    return item
        # Older contest problems may render a page with Authentication required.
        # Never treat the surrounding page/navigation as a problem statement.
        content = problem_html(html, "geeksforgeeks")
        return {"slug": problem_slug, "problem_question": content} if content else None

    async def _problem(self, problem_slug: str) -> dict | None:
        response = await self._http.request(
            "GET", f"https://www.geeksforgeeks.org/problems/{problem_slug}/1", optional=True,
        )
        if response:
            path = re.fullmatch(r"/problems/([a-zA-Z0-9_-]+)(?:/[0-9]+)?/?", response.url.path)
            if not path or path[1] != problem_slug:
                raise invalid_response("GFG returned a different problem page")
        metadata = self.parse_problem(response.text, problem_slug) if response else None
        # Keep only the fields needed for matching, not the problem's code/editorials.
        if metadata is not None:
            metadata = {key: metadata.get(key) for key in (
                "slug", "problem_name", "difficulty", "problem_question", "tags",
            )}
        return metadata

    async def fetch_solved_records(self, profile: CanonicalProfile, cursor: str | None = None) -> ConnectorPage:
        start = page_start(cursor)
        _, solved = await self._load(profile)
        if profile.handle not in self._records:
            solved_items = self.parse_solved(solved)
            enriched = await self._http.problem_metadata(
                [item["slug"] for _, item in solved_items], self._problem, self._statement_limit,
            )
            records = []
            for difficulty, item in solved_items:
                key = item["slug"]
                metadata = enriched.get(key) or {}
                tags = metadata.get("tags") or {}
                if not isinstance(tags, dict) or not isinstance(tags.get("topic_tags", []), list):
                    raise invalid_response("GFG returned invalid problem topics")
                record = NormalizedRecord(
                    platform=Platform.GEEKSFORGEEKS, source_id=key,
                    kind=RecordKind.PROBLEM, status=RecordStatus.SOLVED,
                    title=metadata.get("problem_name") or item["pname"],
                    canonical_url=f"https://www.geeksforgeeks.org/problems/{key}/1",
                    difficulty=metadata.get("difficulty") or difficulty,
                    topics=[tag for tag in tags.get("topic_tags", []) if isinstance(tag, str)],
                    occurred_at=timestamp(item.get("user_subtime")),
                    source_solved_at=source_local_time(item.get("user_subtime")),
                    statement=statement_text(metadata.get("problem_question"), base_url=f"https://www.geeksforgeeks.org/problems/{key}/1"),
                    # GFG returns neither a public submission ID nor a submission URL.
                    submission_url=None, source_payload_checksum="pending",
                )
                record.source_payload_checksum = payload_checksum({
                    "record": record.model_dump(mode="json", exclude={"source_payload_checksum"}),
                    "source_submission_time": item.get("user_subtime"),
                })
                records.append(record)
            self._records[profile.handle] = records
        records = self._records[profile.handle]
        return ConnectorPage(records=records[start:start + 1000],
                             next_cursor=str(start + 1000) if start + 1000 < len(records) else None)

    async def enrich_records(self, records: list[NormalizedRecord], limit: int) -> list[NormalizedRecord]:
        eligible = [row for row in records if row.platform == Platform.GEEKSFORGEEKS
                    and row.kind == RecordKind.PROBLEM and row.status == RecordStatus.SOLVED]
        metadata = await self._http.problem_metadata([slug(row.source_id) for row in eligible], self._problem, limit)
        updated = []
        for row in eligible:
            data = metadata.get(row.source_id)
            if not data:
                continue
            tags = data.get("tags") or {}
            if not isinstance(tags, dict) or not isinstance(tags.get("topic_tags", []), list):
                raise invalid_response("GFG returned invalid problem topics")
            values = {"title": data.get("problem_name"), "difficulty": data.get("difficulty"),
                      "topics": [tag for tag in tags.get("topic_tags", []) if isinstance(tag, str)],
                      "statement": statement_text(data.get("problem_question"), base_url=row.canonical_url)}
            changed = {key: value for key, value in values.items() if value and value != getattr(row, key)}
            if changed:
                result = NormalizedRecord.model_validate({**row.model_dump(), **changed})
                result.source_payload_checksum = payload_checksum(result.model_dump(mode="json", exclude={"source_payload_checksum"}))
                updated.append(result)
        return updated

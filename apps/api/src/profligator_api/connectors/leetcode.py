"""Collect solved-question evidence; contest statistics are optional and deferred."""

from datetime import UTC, datetime
import json
import re

import httpx

from profligator_api.connectors.base import Connector, ConnectorError, payload_checksum
from profligator_api.connectors.metadata import MetadataStore
from profligator_api.connectors.public_web import (
    PublicWebClient, integer, invalid_response, page_start, public_profile, slug,
    statement_text, timestamp,
)
from profligator_api.schemas import (
    CanonicalProfile, ConnectorDescriptor, ConnectorMode, ConnectorPage,
    ActivityCalendar, ActivityDay, CalendarCollection,
    NormalizedRecord, Platform, ProfileSnapshot, RecordKind, RecordStatus,
)


_CONTEST_PROFILE_QUERY = """
query PublicProfile($username: String!, $limit: Int!) {
  matchedUser(username: $username) {
    username
    profile { realName ranking }
    submitStatsGlobal { acSubmissionNum { difficulty count } }
  }
  recentAcSubmissionList(username: $username, limit: $limit) { id title titleSlug timestamp }
  userContestRanking(username: $username) { rating globalRanking }
  userContestRankingHistory(username: $username) {
    attended rating ranking problemsSolved totalProblems
    contest { title startTime questions { title titleSlug } }
  }
}
"""
_PROFILE_QUERY = """
query PublicProfile($username: String!, $limit: Int!) {
  matchedUser(username: $username) {
    username
    profile { realName }
    submitStatsGlobal { acSubmissionNum { difficulty count } }
  }
  recentAcSubmissionList(username: $username, limit: $limit) { id title titleSlug timestamp }
  userContestRankingHistory(username: $username) {
    attended problemsSolved totalProblems
    contest { title questions { title titleSlug } }
  }
}
"""
_QUESTION_QUERY = """
query PublicProblem($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    title titleSlug content difficulty isPaidOnly topicTags { name }
  }
}
"""
_CALENDAR_QUERY = """
query PublicCalendar($username: String!, $year: Int!) {
  matchedUser(username: $username) {
    username
    userCalendar(year: $year) { activeYears submissionCalendar }
  }
}
"""


class LeetCodeConnector(Connector):
    supports_problem_metadata = True
    descriptor = ConnectorDescriptor(
        platform=Platform.LEETCODE, mode=ConnectorMode.SCRAPER, live_data=True,
        notice="Public solved-question collector. Imports recent acceptances and question names supported by fully solved contest evidence. Contest statistics are deferred. Source totals and recovered coverage remain separate; lifetime history may be partial.",
    )

    def __init__(self, min_interval_seconds: float = 2.05, statement_limit: int = 20, *,
                 transport: httpx.AsyncBaseTransport | None = None,
                 metadata_store: MetadataStore | None = None,
                 calendar_year_limit: int = 3, collect_contests: bool = False) -> None:
        self._http = PublicWebClient("LeetCode", {"leetcode.com", "www.leetcode.com"},
                                     min_interval_seconds, transport=transport, metadata_store=metadata_store)
        self._statement_limit = statement_limit
        self._calendar_year_limit = max(1, min(calendar_year_limit, 10))
        self._collect_contests = collect_contests
        if collect_contests:
            self.descriptor = self.descriptor.model_copy(update={"notice": self.descriptor.notice.replace(
                "Contest statistics are deferred.", "Contest statistics are enabled.")})
        self._profiles: dict[str, dict] = {}
        self._records: dict[str, list[NormalizedRecord]] = {}

    async def validate_handle(self, handle_or_url: str) -> CanonicalProfile:
        return public_profile(Platform.LEETCODE, handle_or_url)

    async def _query(self, query: str, variables: dict, *, optional_fields: tuple[str, ...] = ()) -> dict:
        response = await self._http.request("POST", "https://leetcode.com/graphql",
                                           json_body={"query": query, "variables": variables})
        payload = self._http.json(response)
        errors = payload.get("errors")
        if errors and (not isinstance(errors, list) or any(
            not isinstance(error, dict) or not isinstance(error.get("path"), list)
            or not error["path"] or error["path"][0] not in optional_fields for error in errors
        )):
            raise ConnectorError("provider_query_error", "LeetCode could not return the requested public data")
        if not isinstance(payload.get("data"), dict):
            raise invalid_response("LeetCode returned no public data")
        return payload["data"]

    async def _load(self, profile: CanonicalProfile, *, refresh: bool = False) -> dict:
        if refresh or profile.handle not in self._profiles:
            data = await self._query(
                _CONTEST_PROFILE_QUERY if self._collect_contests else _PROFILE_QUERY,
                {"username": profile.handle, "limit": 20},
                optional_fields=() if self._collect_contests else ("userContestRankingHistory",),
            )
            user = data.get("matchedUser")
            if user is None:
                raise ConnectorError("profile_not_found", "LeetCode profile was not found or is private")
            if not isinstance(user, dict) or not isinstance(user.get("username"), str):
                raise invalid_response("LeetCode returned an invalid profile")
            if user["username"].casefold() != profile.handle.casefold():
                raise invalid_response("LeetCode returned a different user's profile")
            for key in (("recentAcSubmissionList", "userContestRankingHistory") if self._collect_contests else ("recentAcSubmissionList",)):
                if not isinstance(data.get(key), list):
                    raise invalid_response("LeetCode public history is unavailable")
            if len(self._profiles) >= 16:
                self._profiles.clear()
                self._records.clear()
            self._profiles[profile.handle] = data
            self._records.pop(profile.handle, None)
        return self._profiles[profile.handle]

    async def fetch_profile(self, profile: CanonicalProfile) -> ProfileSnapshot:
        data = await self._load(profile, refresh=True)
        user = data["matchedUser"]
        details = user.get("profile") or {}
        stats = user.get("submitStatsGlobal") or {}
        if not isinstance(details, dict) or not isinstance(stats, dict):
            raise invalid_response("LeetCode returned invalid profile statistics")
        counts = stats.get("acSubmissionNum")
        if not isinstance(counts, list):
            raise invalid_response("LeetCode solved counts are unavailable")
        total = next((integer(item.get("count")) for item in counts
                      if isinstance(item, dict) and item.get("difficulty") == "All"), None)
        if total is None or total < 0:
            raise invalid_response("LeetCode returned an invalid solved total")
        ranking = (data.get("userContestRanking") or {}) if self._collect_contests else {}
        if not isinstance(ranking, dict):
            raise invalid_response("LeetCode returned invalid contest statistics")
        rating = ranking.get("rating")
        canonical = profile.model_copy(update={"display_name": details.get("realName") or user["username"]})
        return ProfileSnapshot(
            profile=canonical, fetched_at=datetime.now(UTC), source_total_solved=total,
            rating=round(rating) if isinstance(rating, (int, float)) else None,
            rank=str(ranking["globalRanking"]) if ranking.get("globalRanking") else None,
            # Count reconciliation is required; a public total alone is insufficient.
            history_complete=len(self.solved_evidence(data)) == total,
            source_difficulty_counts={item["difficulty"]: integer(item["count"]) for item in counts
                                      if isinstance(item, dict) and item.get("difficulty") in {"Easy", "Medium", "Hard"}
                                      and integer(item.get("count")) is not None and integer(item["count"]) >= 0} or None,
        )

    @staticmethod
    def parse_calendar(data: dict, handle: str, year: int) -> tuple[ActivityCalendar, list[int]]:
        user = data.get("matchedUser")
        if not isinstance(user, dict) or not isinstance(user.get("username"), str) or user["username"].casefold() != handle.casefold():
            raise invalid_response("LeetCode returned an invalid calendar identity")
        calendar = user.get("userCalendar")
        if not isinstance(calendar, dict) or calendar.get("submissionCalendar") is None:
            raise ConnectorError("calendar_unavailable", "LeetCode public activity calendar is unavailable")
        years = calendar.get("activeYears")
        now = datetime.now(UTC)
        if (not isinstance(years, list) or len(years) > 100
                or any(integer(value) is None or not 2010 <= integer(value) <= now.year for value in years)):
            raise invalid_response("LeetCode returned invalid activity years")
        raw = calendar["submissionCalendar"]
        try:
            values = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError as exc:
            raise invalid_response("LeetCode returned invalid calendar data") from exc
        if not isinstance(values, dict) or len(values) > 366:
            raise invalid_response("LeetCode returned an invalid daily calendar")
        days = {}
        for key, value in values.items():
            when = timestamp(key)
            count = integer(value)
            if (when is None or when.year != year or when.date() > now.date()
                    or count is None or count < 0 or count > 10_000_000):
                raise invalid_response("LeetCode returned invalid daily submission counts")
            if when.date() in days:
                raise invalid_response("LeetCode returned duplicate calendar days")
            if count:
                days[when.date()] = count
        return ActivityCalendar(year=year, days=[ActivityDay(date=day, count=count)
                                for day, count in sorted(days.items())], fetched_at=now), sorted(set(map(int, years)))

    async def fetch_activity(self, profile: CanonicalProfile,
                             known_years: dict[int, datetime] | None = None) -> CalendarCollection:
        known = known_years or {}
        calendars = []
        active_years = []
        now = datetime.now(UTC)
        try:
            current, active_years = self.parse_calendar(await self._query(
                _CALENDAR_QUERY, {"username": profile.handle, "year": now.year},
            ), profile.handle, now.year)
            calendars.append(current)
            # Refresh the latest two years for the rolling 12-month view. Remaining
            # budget advances into previously unchecked historical active years.
            pending = [year for year in active_years if year < now.year - 1 and (
                year not in known or (now - (known[year].replace(tzinfo=UTC)
                                            if known[year].tzinfo is None else known[year])).total_seconds() >= 86400
            )]
            pending.sort(key=lambda year: (year in known, known.get(year, datetime.min.replace(tzinfo=UTC)).replace(tzinfo=UTC), -year))
            selected = [now.year - 1, *pending]
            for year in selected[:self._calendar_year_limit - 1]:
                calendar, _ = self.parse_calendar(await self._query(
                    _CALENDAR_QUERY, {"username": profile.handle, "year": year},
                ), profile.handle, year)
                calendars.append(calendar)
            checked = set(known) | {calendar.year for calendar in calendars}
            required = set(active_years) | {now.year, now.year - 1}
            return CalendarCollection(status="available" if required <= checked else "partial",
                                      calendars=calendars, available_years=active_years)
        except ConnectorError as exc:
            # Calendar access is optional. Keep valid question imports and old
            # calendars; never turn an inaccessible response into zero activity.
            return CalendarCollection(status="partial" if calendars else "unavailable", calendars=calendars,
                                      available_years=active_years, error_code=exc.code)

    @staticmethod
    def solved_evidence(data: dict) -> dict[str, dict]:
        """Prefer direct acceptances, then infer names only from fully solved contests.

        A contest score/rank or a partial solved count never identifies which tasks
        were solved. Require the reported solved count, total and distinct question
        list length to agree before adding any questions from that contest.
        """
        solved: dict[str, dict] = {}
        for item in data["recentAcSubmissionList"][:20]:
            if not isinstance(item, dict) or not isinstance(item.get("title"), str) or not item["title"]:
                raise invalid_response("LeetCode returned an invalid accepted submission")
            key = slug(item.get("titleSlug"))
            previous = solved.get(key)
            current_time = timestamp(item.get("timestamp"))
            previous_time = timestamp(previous.get("timestamp")) if previous else None
            if previous is None or (current_time and (previous_time is None or current_time < previous_time)):
                solved[key] = item
        history = data.get("userContestRankingHistory")
        for item in history if isinstance(history, list) else []:
            if not isinstance(item, dict):
                raise invalid_response("LeetCode returned invalid contest history")
            total = integer(item.get("totalProblems"))
            count = integer(item.get("problemsSolved"))
            if item.get("attended") is not True or total is None or total <= 0 or count != total:
                continue
            contest = item.get("contest")
            if not isinstance(contest, dict) or not isinstance(contest.get("title"), str):
                raise invalid_response("LeetCode returned invalid contest details")
            questions = contest.get("questions")
            if not isinstance(questions, list) or len(questions) != total:
                continue
            candidates = {}
            for question in questions:
                if not isinstance(question, dict) or not isinstance(question.get("title"), str) or not question["title"]:
                    raise invalid_response("LeetCode returned an invalid contest question")
                key = slug(question.get("titleSlug"))
                candidates[key] = {
                    "titleSlug": key, "title": question["title"],
                    "_contest_evidence": {
                        "contest": contest["title"], "startTime": contest.get("startTime"),
                        "problemsSolved": count, "totalProblems": total,
                    },
                }
            if len(candidates) == total:
                for key, question in candidates.items():
                    solved.setdefault(key, question)
        return solved

    async def _problem(self, title_slug: str) -> dict | None:
        data = await self._query(_QUESTION_QUERY, {"titleSlug": title_slug})
        question = data.get("question")
        if question is not None and (not isinstance(question, dict) or question.get("titleSlug") != title_slug):
            raise invalid_response("LeetCode returned metadata for a different problem")
        if question is not None and question.get("isPaidOnly") is not False:
            question = {**question, "content": None}
        return question

    async def enrich_records(self, records: list[NormalizedRecord], limit: int) -> list[NormalizedRecord]:
        eligible = [row for row in records if row.platform == Platform.LEETCODE
                    and row.kind == RecordKind.PROBLEM and row.status == RecordStatus.SOLVED]
        metadata = await self._http.problem_metadata([slug(row.source_id) for row in eligible], self._problem, limit)
        updated = []
        for row in eligible:
            data = metadata.get(row.source_id)
            if not data:
                continue
            tags = data.get("topicTags") or []
            if not isinstance(tags, list):
                raise invalid_response("LeetCode returned invalid problem topics")
            values = {"title": data.get("title"), "difficulty": data.get("difficulty"),
                      "topics": [tag["name"] for tag in tags if isinstance(tag, dict) and isinstance(tag.get("name"), str)],
                      "statement": statement_text(data.get("content"), base_url=row.canonical_url) if data.get("isPaidOnly") is False else None}
            changed = {key: value for key, value in values.items() if value and value != getattr(row, key)}
            if changed:
                result = NormalizedRecord.model_validate({**row.model_dump(), **changed})
                result.source_payload_checksum = payload_checksum(result.model_dump(mode="json", exclude={"source_payload_checksum"}))
                updated.append(result)
        return updated

    async def fetch_solved_records(self, profile: CanonicalProfile, cursor: str | None = None) -> ConnectorPage:
        start = page_start(cursor)
        data = await self._load(profile)
        if profile.handle not in self._records:
            submissions = self.solved_evidence(data)
            enriched = await self._http.problem_metadata(list(submissions), self._problem, self._statement_limit)
            records = []
            for key, item in submissions.items():
                metadata = enriched.get(key) or {}
                tags = metadata.get("topicTags") or []
                if not isinstance(tags, list):
                    raise invalid_response("LeetCode returned invalid problem topics")
                submission_id = integer(item.get("id"))
                record = NormalizedRecord(
                    platform=Platform.LEETCODE, source_id=key,
                    kind=RecordKind.PROBLEM, status=RecordStatus.SOLVED,
                    title=metadata.get("title") or item["title"],
                    canonical_url=f"https://leetcode.com/problems/{key}/",
                    difficulty=metadata.get("difficulty"),
                    topics=[tag["name"] for tag in tags if isinstance(tag, dict) and isinstance(tag.get("name"), str)],
                    occurred_at=timestamp(item.get("timestamp")),
                    statement=statement_text(metadata.get("content"), base_url=f"https://leetcode.com/problems/{key}/") if metadata.get("isPaidOnly") is False else None,
                    submission_url=f"https://leetcode.com/submissions/detail/{submission_id}/"
                    if submission_id is not None and submission_id > 0 else None,
                    source_payload_checksum="pending",
                )
                payload = record.model_dump(mode="json", exclude={"source_payload_checksum"})
                if item.get("_contest_evidence"):
                    payload["contest_evidence"] = item["_contest_evidence"]
                record.source_payload_checksum = payload_checksum(payload)
                records.append(record)
            self._records[profile.handle] = records
        records = self._records[profile.handle]
        return ConnectorPage(records=records[start:start + 1000],
                             next_cursor=str(start + 1000) if start + 1000 < len(records) else None)

    async def fetch_contests(self, profile: CanonicalProfile, cursor: str | None = None) -> ConnectorPage:
        if not self._collect_contests:
            return ConnectorPage(records=[])
        data = await self._load(profile)
        records = {}
        for item in data["userContestRankingHistory"]:
            if not isinstance(item, dict):
                raise invalid_response("LeetCode returned invalid contest history")
            if item.get("attended") is not True:
                continue
            contest = item.get("contest")
            if not isinstance(contest, dict):
                raise invalid_response("LeetCode returned an invalid contest")
            title = contest.get("title")
            start_time = timestamp(contest.get("startTime"))
            if not isinstance(title, str) or start_time is None:
                raise invalid_response("LeetCode returned invalid contest details")
            # Only the two public series have a URL derivable from this response.
            match = re.fullmatch(r"(Weekly|Biweekly) Contest (\d+)", title)
            if match is None:
                continue
            contest_slug = f"{match[1].lower()}-contest-{match[2]}"
            rating = item.get("rating")
            rank = integer(item.get("ranking"))
            records[contest_slug] = NormalizedRecord(
                platform=Platform.LEETCODE, source_id=contest_slug,
                kind=RecordKind.CONTEST, status=RecordStatus.PARTICIPATED,
                title=title, canonical_url=f"https://leetcode.com/contest/{contest_slug}/",
                occurred_at=start_time,
                contest_rating=round(rating) if isinstance(rating, (int, float)) else None,
                global_rank=rank if rank and rank > 0 else None,
                source_payload_checksum=payload_checksum(item),
            )
        start = page_start(cursor)
        values = list(records.values())
        return ConnectorPage(records=values[start:start + 1000],
                             next_cursor=str(start + 1000) if start + 1000 < len(values) else None)

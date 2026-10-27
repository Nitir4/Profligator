"""Owner-scoped question imports and provider-confirmed acceptance refreshes."""

import asyncio
from datetime import UTC, datetime, timedelta
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from profligator_api.coordination import serialize_history
from profligator_api.config import Settings
from profligator_api.connectors.base import ConnectorError, payload_checksum
from profligator_api.connectors.registry import ConnectorRegistry
from profligator_api.connectors.metadata import DatabaseMetadataStore
from profligator_api.database import Database
from profligator_api.enrichment import enrich_profile
from profligator_api.extension_auth import read_extension_session
from profligator_api.matching import MatchingService
from profligator_api.models import CodingRecord, PlatformProfile, User
from profligator_api.repository import Repository
from profligator_api.schemas import CanonicalProfile, NormalizedRecord, Platform, Topic
from profligator_api.enrichment import normalized
from profligator_api.security import optional_bearer


class BrowserQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(pattern=r"^[a-z0-9-]{1,160}$")
    title: str = Field(min_length=1, max_length=512)
    solved_at: datetime | None = None
    submission_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,24}$")
    difficulty: Literal["Easy", "Medium", "Hard"] | None = None
    topics: list[Topic] = Field(default_factory=list, max_length=50)
    statement: str | None = Field(default=None, min_length=1, max_length=50000)
    public_statement: Literal[True] | None = None

    @model_validator(mode="after")
    def public_text(self):
        if self.statement is not None and (self.public_statement is not True or not self.statement.strip()):
            raise ValueError("Only explicitly public question text can be imported")
        return self

    @field_validator("title")
    @classmethod
    def nonempty_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question title must not be empty")
        return value.strip()

    @field_validator("solved_at")
    @classmethod
    def known_instant(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value < datetime(2010, 1, 1, tzinfo=UTC)
                                  or value > datetime.now(UTC) + timedelta(minutes=5)):
            raise ValueError("Acceptance dates must be provider timestamps with a known time zone")
        return value.astimezone(UTC) if value is not None else None


class BrowserImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(min_length=1, max_length=64)
    handle: str = Field(min_length=2, max_length=64)
    questions: list[BrowserQuestion] = Field(max_length=100)
    source_total_solved: int | None = Field(default=None, ge=0, le=1_000_000, strict=True)
    final_batch: bool = False


class ProviderImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(min_length=1, max_length=64)
    source_id: str | None = Field(default=None, min_length=1, max_length=160)


class VisibleProblem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Platform
    source_id: str = Field(min_length=1, max_length=160)
    statement: str = Field(min_length=1, max_length=50000)
    topics: list[Topic] = Field(default_factory=list, max_length=50)
    public_statement: Literal[True]

    @model_validator(mode="after")
    def valid_question(self):
        pattern = r"[1-9][0-9]*-[A-Z][0-9]?" if self.platform == Platform.CODEFORCES else r"[a-z0-9-]{1,160}"
        if not re.fullmatch(pattern, self.source_id) or not self.statement.strip():
            raise ValueError("Expected a public problem identity and nonempty text")
        return self


async def extension_owner(request: Request,
                          bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(optional_bearer)]) -> User:
    return read_extension_session(request, bearer)[0]


def create_history_router(database: Database, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/extension/history", tags=["extension"])
    owner = Annotated[User, Depends(extension_owner)]
    registry = ConnectorRegistry(settings.model_copy(update={"scraper_statement_limit": 0}),
                                 metadata_store=DatabaseMetadataStore(database))
    locks: dict[str, asyncio.Lock] = {}

    def owned_profile(repository: Repository, profile_id: str, user_id: str):
        profile = repository.get_profile(profile_id, user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Linked platform account not found")
        return profile

    def counts(repository: Repository, profile, *, status: str = "succeeded", written: int = 0) -> dict:
        records = list(repository.session.scalars(select(CodingRecord).where(
            CodingRecord.platform_profile_id == profile.id, CodingRecord.kind == "problem",
            CodingRecord.status == "solved",
        )))
        return {"profile_id": profile.id, "platform": profile.platform, "handle": profile.public_handle,
                "status": status, "questions": len(records), "records_written": written,
                "timestamped_questions": sum(row.occurred_at is not None for row in records),
                "source_local_question_times": sum(row.source_solved_at is not None for row in records),
                "questions_with_statements": sum(bool(row.statement) for row in records),
                "questions_with_difficulty": sum(bool(row.difficulty) for row in records),
                "questions_with_topics": sum(bool(row.topics) for row in records),
                "source_total_solved": profile.source_total_solved, "history_complete": profile.history_complete}

    async def match(user_id: str) -> None:
        try:
            await asyncio.wait_for(MatchingService(database, settings).match_user(user_id),
                                   timeout=settings.matching_run_timeout_seconds)
        except Exception:
            # An unavailable model must not discard imported questions.
            pass

    @router.get("/profiles")
    async def profiles(current_user: owner, response: Response) -> list[dict]:
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            repository = Repository(session)
            return [{**counts(repository, profile),
                     "import_method": "browser_session" if profile.platform == "leetcode" else "public_provider",
                     "date_support": "accepted_submission" if profile.platform != "geeksforgeeks" else "source_time",
                     "connector_mode": profile.connector_mode}
                    for profile in repository.list_profiles(current_user.id)]

    @router.post("/browser")
    @serialize_history(database)
    async def browser_import(payload: BrowserImport, current_user: owner, response: Response, request: Request,
                             bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(optional_bearer)]) -> dict:
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            repository = Repository(session)
            profile = owned_profile(repository, payload.profile_id, current_user.id)
            if profile.platform != "leetcode" or profile.public_handle.casefold() != payload.handle.casefold():
                raise HTTPException(status_code=422, detail="Signed-in LeetCode account must match the linked account")
            if len({item.source_id for item in payload.questions}) != len(payload.questions):
                raise HTTPException(status_code=422, detail="Question identities must be distinct within a batch")
            records = []
            for item in payload.questions:
                evidence = item.model_dump(mode="json")
                records.append(NormalizedRecord(
                    platform=Platform.LEETCODE, source_id=item.source_id, kind="problem", status="solved",
                    title=item.title, canonical_url=f"https://leetcode.com/problems/{item.source_id}/",
                    occurred_at=item.solved_at,
                    statement=item.statement, difficulty=item.difficulty, topics=item.topics,
                    submission_url=f"https://leetcode.com/submissions/detail/{item.submission_id}/"
                    if item.submission_id else None,
                    source_payload_checksum=payload_checksum({"source": "owner_browser", "handle": payload.handle,
                                                              "question": evidence}),
                ))
            written = repository.upsert_records(profile.id, records)
            if payload.source_total_solved is not None:
                profile.source_total_solved = payload.source_total_solved
            if profile.source_total_solved is not None:
                profile.history_complete = counts(repository, profile)["questions"] == profile.source_total_solved
            # Browser evidence is an owner import, not proof of provider account ownership.
            result = counts(repository, profile, written=written)
        if payload.final_batch:
            async with locks.setdefault("leetcode", asyncio.Lock()):
                enrichment = await enrich_profile(database, payload.profile_id, registry.get(Platform.LEETCODE),
                                                  settings.scraper_statement_limit,
                                                  authorize=lambda: read_extension_session(request, bearer))
            with database.session() as session:
                repository = Repository(session)
                result = {**counts(repository, owned_profile(repository, payload.profile_id, current_user.id), written=written),
                          **enrichment}
            await match(current_user.id)
        return result

    @router.post("/metadata")
    @serialize_history(database)
    async def visible_metadata(payload: VisibleProblem, current_user: owner, response: Response) -> dict:
        """Owner-authorized page text enriches existing solves, never creates one.

        Browser imports remain scoped to this candidate rather than entering the
        shared public metadata cache. No acceptance date is accepted here.
        """
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            repository = Repository(session)
            rows = list(session.scalars(select(CodingRecord).join(PlatformProfile).where(
                PlatformProfile.user_id == current_user.id, PlatformProfile.disconnected_at.is_(None),
                PlatformProfile.platform == payload.platform.value, CodingRecord.source_id == payload.source_id,
                CodingRecord.kind == "problem", CodingRecord.status == "solved",
            )))
            written = 0
            for row in rows:
                # Keep the first usable text; later public refreshes may supply an update.
                # Mere visits must not continually invalidate matching/clustering.
                if row.statement and (row.topics or not payload.topics):
                    continue
                record = normalized(row, payload.platform.value)
                record.statement = row.statement or payload.statement
                record.topics = row.topics or payload.topics
                record.source_payload_checksum = payload_checksum(record.model_dump(mode="json", exclude={"source_payload_checksum"}))
                written += repository.upsert_records(row.platform_profile_id, [record])
        if written:
            await match(current_user.id)
        return {"status": "saved" if rows else "not_in_history", "metadata_records_written": written}

    @router.post("/provider")
    @serialize_history(database)
    async def provider_import(payload: ProviderImport, current_user: owner, response: Response, request: Request,
                              bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(optional_bearer)]) -> dict:
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            repository = Repository(session)
            profile = owned_profile(repository, payload.profile_id, current_user.id)
            if profile.platform == "leetcode":
                raise HTTPException(status_code=422, detail="Use a signed-in LeetCode tab to import its history")
            if payload.source_id is not None and not re.fullmatch(
                r"[a-z0-9-]{1,160}" if profile.platform == "geeksforgeeks" else r"[0-9]+-[A-Z][0-9]?", payload.source_id,
            ):
                raise HTTPException(status_code=422, detail="Invalid question identity")
            # Share the existing sync claim so a provider refresh cannot overlap a regular sync.
            run, claimed = repository.claim_sync(profile.id, settings.extension_history_cooldown_seconds,
                                                  settings.sync_job_timeout_seconds)
            if not claimed:
                return counts(repository, profile, status="cooldown")
            run_id = run.id
            repository.mark_sync_running(run)
            canonical = CanonicalProfile(platform=profile.platform, handle=profile.public_handle,
                                         canonical_url=profile.canonical_url)
        lock = locks.setdefault(canonical.platform.value, asyncio.Lock())

        async def collect():
            async with lock:
                connector = registry.get(canonical.platform)
                snapshot = await connector.fetch_profile(canonical)
                if snapshot.profile.handle.casefold() != canonical.handle.casefold():
                    raise ConnectorError("invalid_provider_response", "Provider returned a different account")
                records, cursor, seen, observed_solved = {}, None, set(), set()
                exhausted = False
                for _ in range(20):
                    page = await connector.fetch_solved_records(canonical, cursor)
                    for record in page.records:
                        if record.platform != canonical.platform or record.kind != "problem" or record.status != "solved":
                            continue
                        observed_solved.add(record.source_id)
                        if payload.source_id is not None and record.source_id != payload.source_id:
                            continue
                        previous = records.get(record.source_id)
                        if previous is None or (record.occurred_at is not None and (
                            previous.occurred_at is None or record.occurred_at < previous.occurred_at
                        )):
                            records[record.source_id] = record
                    if page.next_cursor is None:
                        exhausted = True
                        break
                    # Capturing a new acceptance needs only the provider's recent page.
                    if payload.source_id is not None:
                        break
                    if page.next_cursor in seen:
                        raise ConnectorError("invalid_pagination", "Provider repeated a cursor")
                    seen.add(page.next_cursor)
                    cursor = page.next_cursor
                return snapshot, list(records.values()), exhausted, len(observed_solved)

        try:
            snapshot, records, exhausted, source_count = await asyncio.wait_for(collect(), timeout=120)
            read_extension_session(request, bearer)
            with database.session() as session:
                repository = Repository(session)
                profile = owned_profile(repository, payload.profile_id, current_user.id)
                written = repository.upsert_records(profile.id, records)
                if canonical.platform == Platform.CODEFORCES:
                    snapshot.source_total_solved = source_count if exhausted else None
                    snapshot.history_complete = counts(repository, profile)["questions"] == source_count if exhausted else False
                repository.save_snapshot(profile.id, snapshot)
                result = counts(repository, profile, written=written,
                                status="not_found" if payload.source_id and not records else "succeeded")
            async with lock:
                enrichment = await enrich_profile(database, payload.profile_id, registry.get(canonical.platform),
                                                  settings.scraper_statement_limit,
                                                  authorize=lambda: read_extension_session(request, bearer))
            with database.session() as session:
                repository = Repository(session)
                profile = owned_profile(repository, payload.profile_id, current_user.id)
                repository.finish_sync(repository.get_sync(run_id), seen=len(records), written=written)
                result = {**counts(repository, profile, written=written, status=result["status"]), **enrichment}
            if records or enrichment["metadata_records_written"]:
                await match(current_user.id)
            return result
        except (ConnectorError, TimeoutError) as exc:
            with database.session() as session:
                repository = Repository(session)
                repository.fail_sync(repository.get_sync(run_id),
                                     code=exc.code if isinstance(exc, ConnectorError) else "provider_timeout",
                                     message=exc.message if isinstance(exc, ConnectorError) else "History import timed out")
            raise HTTPException(status_code=502, detail="Provider history could not be refreshed; saved questions are retained") from exc
        except Exception:
            with database.session() as session:
                repository = Repository(session)
                repository.fail_sync(repository.get_sync(run_id), code="history_import_failed",
                                     message="History import failed; saved questions are retained")
            raise

    return router

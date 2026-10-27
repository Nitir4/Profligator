import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue
from sqlalchemy import select

from profligator_api.coordination import operation_lock
from profligator_api.config import Settings, get_settings
from profligator_api.connectors import ConnectorError, ConnectorRegistry
from profligator_api.connectors.base import payload_checksum
from profligator_api.connectors.metadata import DatabaseMetadataStore
from profligator_api.database import Database
from profligator_api.enrichment import enrich_profile
from profligator_api.matching import MatchingService
from profligator_api.models import CodingRecord, PlatformProfile
from profligator_api.repository import Repository
from profligator_api.schemas import CanonicalProfile, Platform, SyncRunResponse


logger = logging.getLogger(__name__)


class SyncDispatchError(RuntimeError):
    pass


async def execute_sync(sync_id: str, settings: Settings, *, sleep=asyncio.sleep) -> SyncRunResponse:
    database = Database(settings.database_url)
    try:
        with database.session() as session:
            run = Repository(session).get_sync(sync_id)
            if run is None:
                raise RuntimeError(f"Sync run {sync_id} does not exist")
            profile = session.get(PlatformProfile, run.platform_profile_id)
            user_id = profile.user_id
        async with operation_lock(database, "history:" + user_id):
            with database.session() as session:
                run = Repository(session).get_sync(sync_id)
                if run.status != "pending":
                    return SyncRunResponse.model_validate(run)
            return await _execute_sync(sync_id, settings, sleep=sleep)
    finally:
        database.dispose()


async def _execute_sync(
    sync_id: str,
    settings: Settings,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> SyncRunResponse:
    database = Database(settings.database_url)
    # Spend the metadata budget once, after all fresh and saved solves are available.
    registry = ConnectorRegistry(settings.model_copy(update={"scraper_statement_limit": 0}),
                                 metadata_store=DatabaseMetadataStore(database))
    try:
        with database.session() as session:
            repository = Repository(session)
            run = repository.get_sync(sync_id)
            if run is None:
                raise RuntimeError(f"Sync run {sync_id} does not exist")
            profile = repository.get_profile(run.platform_profile_id)
            if profile is None:
                repository.fail_sync(
                    run,
                    code="profile_not_found",
                    message="The linked profile no longer exists",
                )
                return SyncRunResponse.model_validate(run)
            repository.mark_sync_running(run)
            platform = Platform(profile.platform)
            canonical = CanonicalProfile(
                platform=platform,
                handle=profile.public_handle,
                canonical_url=profile.canonical_url,
            )
            profile_id = profile.id
            user_id = profile.user_id

        connector = registry.get(platform)
        max_attempts = max(1, settings.sync_max_attempts)
        for attempt in range(1, max_attempts + 1):
            try:
                snapshot = await connector.fetch_profile(canonical)
                records = []
                cursor: str | None = None
                seen_cursors: set[str] = set()
                while True:
                    page = await connector.fetch_solved_records(snapshot.profile, cursor)
                    records.extend(page.records)
                    if page.next_cursor is None:
                        break
                    if page.next_cursor in seen_cursors:
                        raise ConnectorError("invalid_pagination", "Provider repeated a pagination cursor")
                    seen_cursors.add(page.next_cursor)
                    cursor = page.next_cursor

                # Third-party connectors may provide contest history independently of solved lists.
                collect_contests = platform != Platform.LEETCODE or settings.leetcode_collect_contests
                if collect_contests and hasattr(connector, "fetch_contests"):
                    cursor = None
                    seen_cursors = set()
                    while True:
                        page = await connector.fetch_contests(snapshot.profile, cursor)
                        records.extend(page.records)
                        if page.next_cursor is None:
                            break
                        if page.next_cursor in seen_cursors:
                            raise ConnectorError("invalid_pagination", "Provider repeated a contest pagination cursor")
                        seen_cursors.add(page.next_cursor)
                        cursor = page.next_cursor

                with database.session() as session:
                    known_years = Repository(session).activity_years(profile_id)
                activity = await connector.fetch_activity(canonical, known_years) if hasattr(connector, "fetch_activity") else None

                with database.session() as session:
                    repository = Repository(session)
                    run = repository.get_sync(sync_id)
                    if run is None:
                        raise RuntimeError(f"Sync run {sync_id} disappeared")
                    if run.status != "running":
                        return SyncRunResponse.model_validate(run)
                    if repository.get_profile(profile_id) is None:
                        repository.fail_sync(run, code="profile_disconnected", message="Profile was disconnected during sync")
                        return SyncRunResponse.model_validate(run)
                    normalized = {}
                    for record in records:
                        if not collect_contests and record.kind.value == "contest":
                            continue
                        key = (record.kind, record.source_id)
                        previous = normalized.get(key)
                        if previous is None:
                            normalized[key] = record
                        elif record.occurred_at is not None and (
                            previous.occurred_at is None or record.occurred_at < previous.occurred_at
                        ):
                            previous.occurred_at = record.occurred_at
                            previous.submission_url = record.submission_url
                            previous.source_payload_checksum = payload_checksum(
                                previous.model_dump(mode="json", exclude={"source_payload_checksum"})
                            )
                    before = {(row.source_id, row.kind): row.source_payload_checksum for row in session.scalars(
                        select(CodingRecord).where(CodingRecord.platform_profile_id == profile_id)
                    )}
                    repository.upsert_records(profile_id, list(normalized.values()))
                    if platform == Platform.CODEFORCES:
                        count = sum(row.kind.value == "problem" and row.status.value == "solved" for row in normalized.values())
                        snapshot.source_total_solved = count
                        snapshot.history_complete = count == sum(row.kind == "problem" and row.status == "solved"
                            for row in session.scalars(select(CodingRecord).where(CodingRecord.platform_profile_id == profile_id)))
                    repository.save_snapshot(profile_id, snapshot if collect_contests else snapshot.model_copy(update={"rating": None, "rank": None}))
                    if activity is not None:
                        repository.save_activity(profile_id, activity)

                # Provider failures must not discard successfully ingested coding history.
                await enrich_profile(database, profile_id, connector, settings.scraper_statement_limit)
                with database.session() as session:
                    # Count each changed record once even if both ingestion and enrichment wrote it.
                    written = sum(before.get((row.source_id, row.kind)) != row.source_payload_checksum
                                  for row in session.scalars(select(CodingRecord).where(
                                      CodingRecord.platform_profile_id == profile_id)))
                try:
                    matching_status = await asyncio.wait_for(
                        MatchingService(database, settings).match_user(user_id),
                        timeout=settings.matching_run_timeout_seconds,
                    )
                except Exception:
                    logger.exception("Matching failed after successful sync %s", sync_id)
                    matching_status = "unavailable"
                with database.session() as session:
                    repository = Repository(session)
                    run = repository.get_sync(sync_id)
                    if run.status != "running":
                        return SyncRunResponse.model_validate(run)
                    repository.finish_sync(run, seen=len(records), written=written)
                    run.matching_status = matching_status
                    return SyncRunResponse.model_validate(run)
            except ConnectorError as exc:
                if not exc.retryable or attempt == max_attempts:
                    with database.session() as session:
                        repository = Repository(session)
                        run = repository.get_sync(sync_id)
                        if run is None:
                            raise RuntimeError(f"Sync run {sync_id} disappeared") from exc
                        repository.fail_sync(run, code=exc.code, message=exc.message)
                        return SyncRunResponse.model_validate(run)
                delay = settings.sync_retry_base_seconds * (2 ** (attempt - 1))
                await sleep(delay + random.uniform(0, delay * 0.2))
            except Exception as exc:
                logger.exception("Unexpected failure in sync %s (attempt %s)", sync_id, attempt)
                if attempt < max_attempts:
                    delay = settings.sync_retry_base_seconds * (2 ** (attempt - 1))
                    await sleep(delay + random.uniform(0, delay * 0.2))
                    continue
                with database.session() as session:
                    repository = Repository(session)
                    run = repository.get_sync(sync_id)
                    if run is None:
                        raise RuntimeError(f"Sync run {sync_id} disappeared") from exc
                    repository.fail_sync(
                        run,
                        code="internal_sync_error",
                        message="The sync failed after bounded retries",
                    )
                    return SyncRunResponse.model_validate(run)
        raise RuntimeError("Sync retry loop ended unexpectedly")
    finally:
        database.dispose()


def run_sync_job(sync_id: str) -> dict[str, object]:
    result = asyncio.run(execute_sync(sync_id, get_settings()))
    return result.model_dump(mode="json")


class SyncDispatcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def dispatch(self, sync_id: str) -> SyncRunResponse | None:
        if self.settings.sync_backend == "inline":
            return await execute_sync(sync_id, self.settings)

        try:
            connection = Redis.from_url(self.settings.redis_url)
            queue = Queue(self.settings.sync_queue_name, connection=connection)
            queue.enqueue(
                run_sync_job,
                sync_id,
                job_id=sync_id,
                job_timeout=self.settings.sync_job_timeout_seconds,
                result_ttl=3600,
                failure_ttl=86400,
            )
        except (RedisError, OSError) as exc:
            raise SyncDispatchError("The profile sync queue is unavailable") from exc
        return None

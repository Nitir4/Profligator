import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue

from profligator_api.config import Settings, get_settings
from profligator_api.connectors import ConnectorError, ConnectorRegistry
from profligator_api.database import Database
from profligator_api.repository import Repository
from profligator_api.schemas import CanonicalProfile, Platform, SyncRunResponse


logger = logging.getLogger(__name__)


class SyncDispatchError(RuntimeError):
    pass


async def execute_sync(
    sync_id: str,
    settings: Settings,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> SyncRunResponse:
    database = Database(settings.database_url)
    registry = ConnectorRegistry(settings)
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

        connector = registry.get(platform)
        max_attempts = max(1, settings.sync_max_attempts)
        for attempt in range(1, max_attempts + 1):
            try:
                snapshot = await connector.fetch_profile(canonical)
                records = []
                cursor: str | None = None
                while True:
                    page = await connector.fetch_solved_records(snapshot.profile, cursor)
                    records.extend(page.records)
                    if page.next_cursor is None:
                        break
                    cursor = page.next_cursor

                with database.session() as session:
                    repository = Repository(session)
                    run = repository.get_sync(sync_id)
                    if run is None:
                        raise RuntimeError(f"Sync run {sync_id} disappeared")
                    written = repository.upsert_records(profile_id, records)
                    repository.finish_sync(run, seen=len(records), written=written)
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

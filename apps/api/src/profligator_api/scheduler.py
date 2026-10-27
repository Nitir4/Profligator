"""Run one scheduler process alongside the API and worker."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import logging

from sqlalchemy import exists, select

from profligator_api.config import Settings, get_settings
from profligator_api.database import Database
from profligator_api.jobs import SyncDispatchError, SyncDispatcher
from profligator_api.models import PlatformProfile, SyncRun
from profligator_api.repository import Repository

logger = logging.getLogger(__name__)


async def sync_due_profiles(settings: Settings) -> list[str]:
    database = Database(settings.database_url)
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.sync_interval_seconds)
    dispatcher = SyncDispatcher(settings)
    try:
        with database.session() as session:
            # Treat an abandoned worker run as failed so it cannot permanently block refreshes.
            stale = session.scalars(select(SyncRun).where(
                SyncRun.status.in_(["pending", "running"]),
                SyncRun.created_at < now - timedelta(seconds=settings.sync_job_timeout_seconds * 2),
            ))
            for run in stale:
                Repository(session).fail_sync(run, code="worker_timeout", message="Sync worker did not finish in time")
            recent_run = exists(select(SyncRun.id).where(
                SyncRun.platform_profile_id == PlatformProfile.id,
                ((SyncRun.status.in_(["pending", "running"])) | (SyncRun.created_at > cutoff)),
            ))
            profiles = list(session.scalars(select(PlatformProfile).where(
                PlatformProfile.disconnected_at.is_(None),
                ((PlatformProfile.last_successful_sync.is_(None)) | (PlatformProfile.last_successful_sync < cutoff)),
                ~recent_run,
            ).order_by(PlatformProfile.created_at)))
            ids = []
            for profile in profiles:
                run, claimed = Repository(session).claim_sync(
                    profile.id, settings.profile_sync_cooldown_seconds,
                    settings.sync_job_timeout_seconds,
                )
                if claimed:
                    ids.append(run.id)
        for sync_id in ids:
            try:
                await dispatcher.dispatch(sync_id)
            except SyncDispatchError:
                with database.session() as session:
                    repository = Repository(session)
                    repository.fail_sync(repository.get_sync(sync_id), code="queue_unavailable", message="Profile sync queue unavailable")
        return ids
    finally:
        database.dispose()


async def run_scheduler(settings: Settings, once: bool) -> None:
    while True:
        try:
            await sync_due_profiles(settings)
        except Exception:
            logger.exception("Periodic sync failed")
            if once:
                raise
        if once:
            return
        await asyncio.sleep(settings.scheduler_poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scheduler(get_settings(), args.once))


if __name__ == "__main__":
    main()

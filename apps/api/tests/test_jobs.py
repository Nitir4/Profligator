from datetime import UTC, datetime
from pathlib import Path

from profligator_api import jobs
from profligator_api.config import Settings
from profligator_api.connectors import ConnectorError
from profligator_api.database import Database
from profligator_api.jobs import SyncDispatcher, execute_sync
from profligator_api.repository import Repository
from profligator_api.schemas import (
    CanonicalProfile,
    ConnectorMode,
    ConnectorPage,
    Platform,
    ProfileSnapshot,
)


async def test_rq_dispatcher_enqueues_worker_job(monkeypatch) -> None:
    enqueued: dict[str, object] = {}

    class FakeRedis:
        @staticmethod
        def from_url(url: str) -> object:
            enqueued["redis_url"] = url
            return object()

    class FakeQueue:
        def __init__(self, name: str, *, connection: object) -> None:
            enqueued["queue_name"] = name
            enqueued["connection"] = connection

        def enqueue(self, function, sync_id: str, **options: object) -> None:
            enqueued["function"] = function
            enqueued["sync_id"] = sync_id
            enqueued["options"] = options

    monkeypatch.setattr(jobs, "Redis", FakeRedis)
    monkeypatch.setattr(jobs, "Queue", FakeQueue)
    settings = Settings(
        sync_backend="rq",
        redis_url="redis://queue.test:6379/4",
        sync_queue_name="profile-syncs",
        sync_job_timeout_seconds=123,
    )

    result = await SyncDispatcher(settings).dispatch("sync-123")

    assert result is None
    assert enqueued["redis_url"] == "redis://queue.test:6379/4"
    assert enqueued["queue_name"] == "profile-syncs"
    assert enqueued["function"] is jobs.run_sync_job
    assert enqueued["sync_id"] == "sync-123"
    assert enqueued["options"] == {
        "job_id": "sync-123",
        "job_timeout": 123,
        "result_ttl": 3600,
        "failure_ttl": 86400,
    }


async def test_sync_retries_transient_connector_failures(
    tmp_path: Path, monkeypatch
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'jobs.db'}",
        sync_max_attempts=3,
        sync_retry_base_seconds=1,
    )
    database = Database(settings.database_url)
    database.initialize()
    profile = CanonicalProfile(
        platform=Platform.CODEFORCES,
        handle="tourist",
        canonical_url="https://codeforces.com/profile/tourist",
    )
    with database.session() as session:
        repository = Repository(session)
        user = repository.create_user(
            email="worker@example.com",
            handle="worker",
            password_hash="test-only-hash",
        )
        saved = repository.save_profile(
            user.id, profile, ConnectorMode.OFFICIAL_API, live_data=True
        )
        run = repository.start_sync(saved.id)
        sync_id = run.id
    database.dispose()

    class RetryingConnector:
        attempts = 0

        async def fetch_profile(self, canonical: CanonicalProfile) -> ProfileSnapshot:
            self.attempts += 1
            if self.attempts < 3:
                raise ConnectorError("provider_timeout", "try again", retryable=True)
            return ProfileSnapshot(profile=canonical, fetched_at=datetime.now(UTC))

        async def fetch_solved_records(
            self, canonical: CanonicalProfile, cursor: str | None = None
        ) -> ConnectorPage:
            return ConnectorPage(records=[])

    connector = RetryingConnector()

    class FakeRegistry:
        def __init__(self, _: Settings) -> None:
            pass

        def get(self, _: Platform) -> RetryingConnector:
            return connector

    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(jobs, "ConnectorRegistry", FakeRegistry)
    result = await execute_sync(sync_id, settings, sleep=fake_sleep)

    assert result.status == "succeeded"
    assert connector.attempts == 3
    assert len(delays) == 2
    assert 1 <= delays[0] <= 1.2
    assert 2 <= delays[1] <= 2.4

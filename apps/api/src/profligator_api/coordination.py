"""Crash-released process coordination for SQLite and PostgreSQL deployments."""
import asyncio
from contextlib import asynccontextmanager
import fcntl
from functools import wraps
from hashlib import sha256
import os
from pathlib import Path
import time

from sqlalchemy import text


@asynccontextmanager
async def operation_lock(database, resource, timeout=300):
    """Keep a dedicated session advisory lock, or a lock beside the SQLite DB.

    No database write transaction stays open during collection or inference.
    OS/session teardown releases locks after worker crashes; no expiring lease
    can let two still-running writers enter the same critical section.
    """
    key = sha256(resource.encode()).digest()
    connection = None
    lock_engine = None
    descriptor = None
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        if database.engine.dialect.name == "postgresql":
            from sqlalchemy import create_engine
            from sqlalchemy.pool import NullPool
            # Long-lived advisory sessions must not exhaust the API query pool.
            lock_engine = create_engine(database.engine.url, poolclass=NullPool)
            connection = lock_engine.connect()
            lock_id = int.from_bytes(key[:8], "big", signed=True)
            def attempt():
                result = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id})
                connection.commit()
                return result
        else:
            filename = database.engine.url.database
            directory = (Path(filename).resolve().parent / (Path(filename).name + ".locks")) if filename and filename != ":memory:" else Path('/tmp/profligator-memory-locks')
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(directory / (key.hex() + '.lock'), os.O_CREAT | os.O_RDWR, 0o600)
            def attempt():
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return True
                except BlockingIOError:
                    return False
        while not attempt():
            if time.monotonic() >= deadline:
                raise TimeoutError("Another profile operation is still in progress. Try again shortly.")
            await asyncio.sleep(0.05)
        acquired = True
        yield
    finally:
        if connection is not None:
            try:
                if acquired:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})
                    connection.commit()
            finally:
                connection.close()
        if lock_engine is not None:
            lock_engine.dispose()
        if descriptor is not None:
            os.close(descriptor)


def serialize_history(database):
    """Coordinate source writes across sync workers and extension imports."""
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            from fastapi import HTTPException
            try:
                async with operation_lock(database, "history:" + kwargs["current_user"].id):
                    from profligator_api.models import User
                    with database.session() as session:
                        user = session.get(User, kwargs["current_user"].id)
                        if user is None or user.auth_version != kwargs["current_user"].auth_version:
                            raise HTTPException(401, "Your account session changed. Sign in again.")
                    if "request" in kwargs and "bearer" in kwargs:
                        from profligator_api.extension_auth import read_extension_session
                        read_extension_session(kwargs["request"], kwargs["bearer"])
                    return await function(*args, **kwargs)
            except TimeoutError:
                raise HTTPException(409, "Another history operation is in progress. Try again shortly.") from None
        return wrapped
    return decorate


async def pace_request(database, key, interval):
    """Atomically reserve the next request slot across processes.

    Cancelled requests may leave an unused slot, which only slows collection.
    The transaction finishes before waiting or making a network request.
    """
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import case
    from sqlalchemy.dialects.postgresql import insert as postgres_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from profligator_api.models import ProviderRequestWindow
    now = datetime.now(UTC)
    model = ProviderRequestWindow
    insert = sqlite_insert if database.engine.dialect.name == "sqlite" else postgres_insert
    statement = insert(model).values(key=key, next_request_at=now + timedelta(seconds=interval))
    statement = statement.on_conflict_do_update(index_elements=[model.key], set_={
        "next_request_at": case((model.next_request_at > now, model.next_request_at + timedelta(seconds=interval)),
                                 else_=now + timedelta(seconds=interval)),
    }).returning(model.next_request_at)
    # SQLite datetime arithmetic uses Julian numbers rather than SQL intervals.
    # Use its write lock and a Python datetime when reserving a slot there.
    with database.session() as session:
        if database.engine.dialect.name == "sqlite":
            seed = insert(model).values(key=key, next_request_at=now).on_conflict_do_nothing(index_elements=[model.key])
            session.execute(seed)
            window = session.get(model, key)
            previous = window.next_request_at.replace(tzinfo=UTC) if window.next_request_at.tzinfo is None else window.next_request_at
            start = max(previous, now)
            window.next_request_at = start + timedelta(seconds=interval)
        else:
            reserved = session.scalar(statement)
            start = reserved - timedelta(seconds=interval)
    delay = (start - datetime.now(UTC)).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)


def defer_requests(database, key, seconds):
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import case
    from sqlalchemy.dialects.postgresql import insert as postgres_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from profligator_api.models import ProviderRequestWindow
    until = datetime.now(UTC) + timedelta(seconds=min(seconds, 3600))
    model = ProviderRequestWindow
    insert = sqlite_insert if database.engine.dialect.name == "sqlite" else postgres_insert
    statement = insert(model).values(key=key, next_request_at=until)
    statement = statement.on_conflict_do_update(index_elements=[model.key], set_={
        "next_request_at": case((model.next_request_at < until, until), else_=model.next_request_at),
    })
    with database.session() as session:
        session.execute(statement)

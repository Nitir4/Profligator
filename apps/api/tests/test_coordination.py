import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import multiprocessing
from pathlib import Path

import pytest
from sqlalchemy import select

from profligator_api.coordination import operation_lock, pace_request
from profligator_api.database import Database
from profligator_api.jobs import execute_sync
from profligator_api.models import ProviderRequestWindow
from profligator_api.repository import Repository
from profligator_api.schemas import ConnectorMode, CanonicalProfile
from profligator_api.config import Settings


def hold_lock(url, ready, release):
    async def run():
        db=Database(url)
        async with operation_lock(db,'history:owner'):
            ready.set()
            while not release.is_set():
                await asyncio.sleep(.01)
        db.dispose()
    asyncio.run(run())


async def test_cross_process_exclusion_and_crash_release(tmp_path):
    url=f"sqlite:///{tmp_path / 'locks.db'}"
    db=Database(url)
    context=multiprocessing.get_context('spawn')
    ready,release=context.Event(),context.Event()
    process=context.Process(target=hold_lock,args=(url,ready,release))
    process.start()
    try:
        assert await asyncio.to_thread(ready.wait,10)
        with pytest.raises(TimeoutError):
            async with operation_lock(db,'history:owner',timeout=.1):
                pytest.fail('Other process owns the lock')
        process.terminate()
        await asyncio.to_thread(process.join,10)
        async with operation_lock(db,'history:owner',timeout=1):
            pass
    finally:
        release.set()
        if process.is_alive(): process.terminate()
        process.join(10)
        db.dispose()


async def test_duplicate_job_deliveries_execute_collection_once(tmp_path,monkeypatch):
    config=Settings(_env_file=None,database_url=f"sqlite:///{tmp_path / 'jobs.db'}",leetcode_connector='fixture',geeksforgeeks_connector='fixture',scraper_statement_limit=0)
    db=Database(config.database_url);db.initialize()
    with db.session() as session:
        repo=Repository(session)
        user=repo.create_user(email='owner@example.com',handle='owner',password_hash=None)
        profile=repo.save_profile(user.id,CanonicalProfile(platform='leetcode',handle='owner',canonical_url='https://leetcode.com/u/owner/'),ConnectorMode.FIXTURE,live_data=False)
        run_id=repo.start_sync(profile.id).id
    from profligator_api.connectors.fixtures import FixtureConnector
    original=FixtureConnector.fetch_profile
    calls=[]
    async def delayed(self,profile):
        calls.append(profile.handle)
        await asyncio.sleep(.1)
        return await original(self,profile)
    monkeypatch.setattr(FixtureConnector,'fetch_profile',delayed)
    results=await asyncio.gather(execute_sync(run_id,config),execute_sync(run_id,config))
    assert len(calls)==1
    assert all(result.status=='succeeded' for result in results)
    db.dispose()


def test_refresh_token_revocation_has_one_winner(tmp_path):
    db=Database(f"sqlite:///{tmp_path / 'refresh.db'}");db.initialize()
    with db.session() as session:
        repo=Repository(session)
        user=repo.create_user(email='owner@example.com',handle='owner',password_hash=None)
        from datetime import timedelta
        repo.create_refresh_session(user_id=user.id,token_hash='hash',expires_at=datetime.now(UTC)+timedelta(days=1))
    def rotate():
        with db.session() as session:
            return Repository(session).revoke_refresh_session('hash')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:rotate(),range(2)))
    assert sorted(results)==[False,True]
    db.dispose()


async def test_provider_reservations_shared_across_database_instances(tmp_path,monkeypatch):
    url=f"sqlite:///{tmp_path / 'pacing.db'}"
    first,second=Database(url),Database(url);first.initialize()
    delays=[]
    async def record(delay): delays.append(delay)
    monkeypatch.setattr('profligator_api.coordination.asyncio.sleep',record)
    await pace_request(first,'source:leetcode',2)
    await pace_request(second,'source:leetcode',2)
    with first.session() as session:
        stamp=session.get(ProviderRequestWindow,'source:leetcode').next_request_at.replace(tzinfo=UTC)
        assert (stamp-datetime.now(UTC)).total_seconds()>3
    assert len(delays)==1 and 1<delays[0]<=2
    first.dispose();second.dispose()

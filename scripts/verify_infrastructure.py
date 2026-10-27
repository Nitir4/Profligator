#!/usr/bin/env python3
"""PostgreSQL migrations and real Redis/RQ acceptance using isolated test data."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(os.environ.get("PROFLIGATOR_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "apps/api/src"))


async def run(output, create_database):
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url
    from alembic import command
    from alembic.config import Config
    from redis import Redis
    from rq import Queue
    from rq.job import Job
    import httpx

    output.mkdir(parents=True, exist_ok=True)
    base = os.environ.get("PROFLIGATOR_TEST_DATABASE_URL")
    if create_database:
        base = base or os.environ.get("PROFLIGATOR_DATABASE_URL")
    if not base:
        raise ValueError("Set PROFLIGATOR_TEST_DATABASE_URL to a dedicated PostgreSQL test database")
    url = make_url(base)
    if url.get_backend_name() != "postgresql":
        raise ValueError("This acceptance check requires PostgreSQL")
    admin = None
    if create_database:
        name = "profligator_acceptance_" + uuid4().hex
        admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        url = url.set(database=name)
    elif not (url.database or "").startswith("profligator_acceptance"):
        raise ValueError("Refusing to migrate a database without the profligator_acceptance prefix")
    engine = create_engine(url)
    redis_url = os.environ.get("PROFLIGATOR_TEST_REDIS_URL")
    if not redis_url:
        parts = urlsplit(os.environ.get("PROFLIGATOR_REDIS_URL", "redis://localhost:6379/0"))
        redis_url = urlunsplit(parts._replace(path="/15"))
    redis = Redis.from_url(redis_url)
    queue_name = "profligator-acceptance-" + uuid4().hex
    queue = Queue(queue_name, connection=redis)
    # Jobs read these settings in a separate process. No live collector/model is used.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PROFLIGATOR_")}
    environment.update({"PROFLIGATOR_DATABASE_URL": url.render_as_string(hide_password=False),
        "PROFLIGATOR_REDIS_URL": redis_url, "PROFLIGATOR_SYNC_BACKEND": "rq",
        "PROFLIGATOR_SYNC_QUEUE_NAME": queue_name, "PROFLIGATOR_AUTO_CREATE_SCHEMA": "false",
        "PROFLIGATOR_MATCHING_BACKEND": "disabled", "PROFLIGATOR_LEETCODE_CONNECTOR": "fixture",
        "PROFLIGATOR_GEEKSFORGEEKS_CONNECTOR": "fixture", "PROFLIGATOR_SCRAPER_STATEMENT_LIMIT": "0",
        "PROFLIGATOR_AUTH_SECRET_KEY": "infrastructure-test-secret-with-at-least-32-characters",
        "PROFLIGATOR_AUTH_COOKIE_SECURE": "false", "PROFLIGATOR_ENVIRONMENT": "development",
        "PROFLIGATOR_PROFILE_SYNC_COOLDOWN_SECONDS": "0", "PYTHONPATH": str(ROOT / "apps/api/src")})
    os.environ.update({key: value for key, value in environment.items() if key.startswith("PROFLIGATOR_")})
    from profligator_api.config import get_settings
    from profligator_api.models import Base
    get_settings.cache_clear()
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    checks = []
    try:
        assert not inspect(engine).get_table_names(), "Test database must be empty"
        assert redis.ping()
        command.upgrade(config, "20260925_0003")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id,email,handle,created_at,updated_at) VALUES ('legacy','legacy@example.com','legacy_user',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO platform_profiles (id,user_id,platform,public_handle,canonical_url,verification_state,connector_mode,created_at,updated_at) VALUES ('legacy-profile','legacy','leetcode','legacy','https://leetcode.com/u/legacy','fixture_only','fixture',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO coding_records (id,platform_profile_id,source_id,kind,status,title,canonical_url,topics,source_payload_checksum,created_at,updated_at) VALUES ('legacy-record','legacy-profile','1','problem','solved','Legacy question','https://leetcode.com/problems/legacy','[]','legacy',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT role FROM users WHERE id='legacy'")) == "candidate"
            assert connection.scalar(text("SELECT cluster_id FROM coding_records WHERE id='legacy-record'"))
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
        for table in Base.metadata.sorted_tables:
            assert {c["name"] for c in inspector.get_columns(table.name)} == {c.name for c in table.columns}
        checks.append("PostgreSQL legacy-to-head migration preserves user/history and matches model columns")

        def worker():
            with (output / "worker.log").open("a") as log:
                subprocess.run([str(Path(sys.executable).with_name("rq")), "worker", "--burst", "--url", redis_url,
                    "--name", "acceptance-" + uuid4().hex, "--path", str(ROOT / "apps/api/src"), queue_name],
                    cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=60, check=True)

        from profligator_api.main import create_app
        app = create_app(get_settings())
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                assert (await client.post("/api/v1/auth/register", json={"email":"infrastructure@example.com",
                    "handle":"infrastructure_user", "password":"InfrastructureTest2026!"})).status_code == 201
                profile = await client.post("/api/v1/platform-profiles", json={"platform":"leetcode","handle_or_url":"fixture_user"})
                assert profile.status_code == 201, profile.status_code
                linked = profile.json()["id"]
                sync = await client.post("/api/v1/syncs", json={"platform_profile_id":linked})
                assert sync.status_code == 202, sync.status_code
                sync_id = sync.json()["id"]
                assert sync.json()["status"] == "pending"
                await asyncio.to_thread(worker)
                result = (await client.get(f"/api/v1/syncs/{sync_id}")).json()
                assert result["status"] == "succeeded", result
                assert Job.fetch(sync_id, connection=redis).get_status().value == "finished"
                assert (await client.get("/api/v1/dashboard")).json()["total_problems_solved"] == 3
                checks.append("Actual RQ enqueue/worker completion, API polling and PostgreSQL dashboard queries")
                # Refresh rotation and replay rejection use real PostgreSQL storage.
                refresh = client.cookies.get("profligator_refresh")
                assert refresh, "Expected the refresh cookie"
                assert (await client.post("/api/v1/auth/refresh")).status_code == 200
                replay = await client.post("/api/v1/auth/refresh", headers={"Cookie":f"profligator_refresh={refresh}"})
                assert replay.status_code == 401
                checks.append("Refresh token rotation and replay rejection on PostgreSQL")
                # Log in again after replay clears browser cookies.
                assert (await client.post("/api/v1/auth/login", json={"email":"infrastructure@example.com","password":"InfrastructureTest2026!"})).status_code == 200
                # A second sync must preserve unique rows rather than reinsert solves.
                again = await client.post("/api/v1/syncs", json={"platform_profile_id":linked})
                assert again.status_code == 202
                await asyncio.to_thread(worker)
                assert (await client.get(f"/api/v1/syncs/{again.json()['id']}")).json()["status"] == "succeeded"
                assert (await client.get("/api/v1/dashboard")).json()["total_problems_solved"] == 3
                checks.append("Repeated queued sync is idempotent")
        failed = queue.enqueue("profligator_api.jobs.run_sync_job", "nonexistent-" + uuid4().hex)
        await asyncio.to_thread(worker)
        assert failed.get_status(refresh=True).value == "failed"
        assert failed.id in queue.failed_job_registry.get_job_ids()
        checks.append("Real worker failure enters RQ failed-job registry")
        report = {"passed":True,"checks":checks,"data":"isolated PostgreSQL database, unique Redis queue, offline provider fixtures",
                  "live_scraping_or_inference":False,"output":str(output)}
        (output / "results.json").write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
    except Exception as exc:
        (output / "results.json").write_text(json.dumps({"passed":False,"completed_checks":checks,
            "error_type":type(exc).__name__},indent=2)+'\n')
        raise
    finally:
        try:
            queue.delete(delete_jobs=True)
        finally:
            engine.dispose()
            if admin:
                with admin.connect() as connection:
                    connection.execute(text(f'DROP DATABASE "{url.database}" WITH (FORCE)'))
                admin.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=Path(tempfile.mkdtemp(prefix="profligator-infrastructure-")))
    parser.add_argument("--create-test-database",action="store_true",help="Create/drop only a randomly named acceptance database using the configured PostgreSQL server")
    args = parser.parse_args()
    asyncio.run(run(args.output_dir,args.create_test_database))

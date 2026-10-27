from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from profligator_api.config import Settings
from profligator_api.main import create_app


@pytest.fixture(autouse=True)
def disable_default_hosted_matching(monkeypatch):
    # A developer's configured .env must never trigger paid/live inference in tests.
    # Explicit Settings(matching_backend=...) still takes precedence for provider tests.
    monkeypatch.setenv("PROFLIGATOR_MATCHING_BACKEND", "disabled")


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        auto_create_schema=True,
        codeforces_min_interval_seconds=0,
        profile_sync_cooldown_seconds=0,
        extension_history_cooldown_seconds=0,
        leetcode_connector="fixture",
        geeksforgeeks_connector="fixture",
        cors_origins=["http://testserver"],
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            registration = await test_client.post(
                "/api/v1/auth/register",
                json={
                    "email": "alex@example.com",
                    "handle": "alex_dev96",
                    "password": "correct-horse-battery-staple",
                },
            )
            assert registration.status_code == 201
            yield test_client

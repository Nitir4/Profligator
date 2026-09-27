from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest_asyncio

from profligator_api.config import Settings
from profligator_api.main import create_app


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        auto_create_schema=True,
        codeforces_min_interval_seconds=0,
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

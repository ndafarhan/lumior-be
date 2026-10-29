from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lumior.core.config import Settings
from lumior.main import create_app

# Nothing listens on port 1, so any accidental database access fails fast.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://lumior:lumior@127.0.0.1:1/lumior"
ALLOWED_ORIGIN = "http://allowed.example"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "database_url": UNREACHABLE_DATABASE_URL,
        "cors_allowed_origins": [ALLOWED_ORIGIN],
        "log_level": "INFO",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

import asyncio
import time
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from lumior.main import create_app
from tests.conftest import UNREACHABLE_DATABASE_URL, make_settings


async def ready_with_database(database_url: str) -> tuple[int, dict[str, object], float]:
    app = create_app(make_settings(database_url=database_url))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        started = time.monotonic()
        response = await client.get("/health/ready")
        elapsed = time.monotonic() - started
    await app.state.engine.dispose()
    return response.status_code, response.json(), elapsed


@pytest.fixture
async def hanging_database_url() -> AsyncIterator[str]:
    """A TCP server that accepts connections but never answers the PostgreSQL handshake."""
    connections: list[asyncio.StreamWriter] = []

    async def accept(_: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connections.append(writer)

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    yield f"postgresql+asyncpg://lumior:lumior@127.0.0.1:{port}/lumior"
    for writer in connections:
        writer.close()
    server.close()
    await server.wait_closed()


async def test_live_ok_with_reachable_database(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_with_reachable_database(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


async def test_ready_with_unreachable_database() -> None:
    status, body, _ = await ready_with_database(UNREACHABLE_DATABASE_URL)

    assert status == 503
    assert body == {"status": "unavailable", "checks": {"database": "unavailable"}}


async def test_ready_failure_does_not_leak_details() -> None:
    url = "postgresql+asyncpg://leaky_user:leaky_pass@127.0.0.1:1/leaky_db"

    status, body, _ = await ready_with_database(url)

    assert status == 503
    assert body == {"status": "unavailable", "checks": {"database": "unavailable"}}
    assert "leaky" not in str(body)


async def test_ready_times_out_when_database_hangs(hanging_database_url: str) -> None:
    status, body, elapsed = await ready_with_database(hanging_database_url)

    assert status == 503
    assert body == {"status": "unavailable", "checks": {"database": "unavailable"}}
    assert 1.9 <= elapsed < 3.0

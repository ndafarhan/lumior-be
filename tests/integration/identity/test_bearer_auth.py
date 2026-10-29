import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from lumior.modules.identity.models import User
from tests.integration.helpers import FakeClock, error_code, register


async def assert_unauthorized(client: AsyncClient, headers: dict[str, str]) -> None:
    response = await client.get("/api/v1/me", headers=headers)
    assert response.status_code == 401
    assert error_code(response) == "unauthorized"


async def test_missing_token(client: AsyncClient) -> None:
    await assert_unauthorized(client, {})


@pytest.mark.parametrize(
    "authorization",
    ["Bearer", "Bearer not-a-token", "Basic dXNlcjpwYXNz", "Token abc", "bearer"],
)
async def test_malformed_or_invalid_token(client: AsyncClient, authorization: str) -> None:
    await assert_unauthorized(client, {"Authorization": authorization})


async def test_refresh_token_is_not_an_access_token(client: AsyncClient) -> None:
    rina = await register(client)

    await assert_unauthorized(client, {"Authorization": f"Bearer {rina.refresh_token}"})


async def test_token_valid_until_expiry(client: AsyncClient, clock: FakeClock) -> None:
    rina = await register(client)

    clock.advance(seconds=899)
    assert (await client.get("/api/v1/me", headers=rina.headers)).status_code == 200

    clock.advance(seconds=1)
    await assert_unauthorized(client, rina.headers)


async def test_token_for_deleted_user(client: AsyncClient, db_session: AsyncSession) -> None:
    rina = await register(client)
    await db_session.execute(delete(User).where(User.id == rina.id))

    await assert_unauthorized(client, rina.headers)


async def test_rejected_write_has_no_effect(client: AsyncClient) -> None:
    rina = await register(client)

    response = await client.patch(
        "/api/v1/me", json={"name": "Hacked"}, headers={"Authorization": "Bearer nope"}
    )

    assert response.status_code == 401
    me = await client.get("/api/v1/me", headers=rina.headers)
    assert me.json()["name"] == "Rina"

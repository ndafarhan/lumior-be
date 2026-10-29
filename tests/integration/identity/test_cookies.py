from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from lumior.core.db import get_session
from lumior.main import create_app
from tests.conftest import make_settings
from tests.integration.helpers import PASSWORD, set_cookie_headers, unique_email


@pytest.fixture
async def production_client(
    database_url: str, db_session: AsyncSession
) -> AsyncIterator[AsyncClient]:
    application: FastAPI = create_app(
        make_settings(database_url=database_url, environment="production")
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://test"
    ) as client:
        yield client
    await application.state.engine.dispose()


def attributes(set_cookie: str) -> set[str]:
    return {part.strip().lower() for part in set_cookie.split(";")[1:]}


async def test_cookie_attributes_in_production(production_client: AsyncClient) -> None:
    response = await production_client.post(
        "/api/v1/auth/register",
        json={"name": "Rina", "email": unique_email(), "password": PASSWORD},
    )

    [cookie] = set_cookie_headers(response)
    assert cookie.startswith("lumior_refresh=")
    assert attributes(cookie) == {
        "httponly",
        "secure",
        "samesite=lax",
        "path=/api/v1/auth",
        "max-age=2592000",
    }


async def test_cookie_attributes_in_development(
    database_url: str, db_session: AsyncSession
) -> None:
    application = create_app(make_settings(database_url=database_url, environment="development"))

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://localhost"
    ) as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={"name": "Rina", "email": unique_email(), "password": PASSWORD},
        )
    await application.state.engine.dispose()

    [cookie] = set_cookie_headers(response)
    assert "secure" not in attributes(cookie)
    assert {"httponly", "samesite=lax", "path=/api/v1/auth"} <= attributes(cookie)


async def test_login_sets_the_same_cookie(production_client: AsyncClient) -> None:
    email = unique_email()
    await production_client.post(
        "/api/v1/auth/register", json={"name": "Rina", "email": email, "password": PASSWORD}
    )

    response = await production_client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )

    [cookie] = set_cookie_headers(response)
    assert "secure" in attributes(cookie)
    assert "path=/api/v1/auth" in attributes(cookie)


def test_cookie_path_matches_auth_router_mount() -> None:
    from lumior.api.v1 import API_V1_PREFIX
    from lumior.modules.identity.cookies import REFRESH_COOKIE_PATH
    from lumior.modules.identity.router import auth_router

    assert API_V1_PREFIX + auth_router.prefix == REFRESH_COOKIE_PATH

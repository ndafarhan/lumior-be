from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from lumior.modules.identity.models import User
from lumior.modules.identity.repository import EmailAlreadyExistsError, UserRepository
from tests.integration.helpers import (
    PASSWORD,
    error_code,
    refresh_cookie,
    register,
    unique_email,
)


async def test_registration_signs_in_with_normalized_name_and_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "  Rina ", "email": "Rina@Example.com", "password": PASSWORD},
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in", "user"}
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert set(body["user"]) == {"id", "email", "name"}
    assert body["user"]["name"] == "Rina"
    assert body["user"]["email"] == "rina@example.com"
    assert refresh_cookie(response)


async def test_refresh_token_is_never_in_the_body(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "Rina", "email": unique_email(), "password": PASSWORD},
    )

    token = refresh_cookie(response)
    assert token is not None
    assert token not in response.text


async def test_email_taken_is_case_insensitive(client: AsyncClient) -> None:
    await register(client, email="rina@example.com")

    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "Other", "email": "RINA@example.com", "password": PASSWORD},
    )

    assert response.status_code == 409
    assert error_code(response) == "email_taken"


async def test_invalid_registration_fields_each_get_a_detail(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "   ", "email": "not-an-email", "password": "x" * 7},
    )

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    locations = sorted(d["location"] for d in response.json()["error"]["details"])
    assert locations == [["body", "email"], ["body", "name"], ["body", "password"]]


@pytest.mark.parametrize(("field", "value"), [("password", "x" * 129), ("name", "n" * 101)])
async def test_values_over_the_limit_are_rejected(
    client: AsyncClient, field: str, value: str
) -> None:
    payload = {"name": "Rina", "email": unique_email(), "password": PASSWORD, field: value}

    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422
    assert [d["location"] for d in response.json()["error"]["details"]] == [["body", field]]


@pytest.mark.parametrize("password", ["x" * 8, "x" * 128])
async def test_password_at_the_limits_is_accepted(client: AsyncClient, password: str) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "Rina", "email": unique_email(), "password": password},
    )

    assert response.status_code == 201


async def test_login_with_any_email_case(client: AsyncClient) -> None:
    rina = await register(client, email="rina.login@example.com")

    response = await client.post(
        "/api/v1/auth/login", json={"email": " RINA.Login@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(rina.id)
    assert response.json()["expires_in"] == 900
    assert refresh_cookie(response)


async def test_wrong_password_and_unknown_email_look_the_same(client: AsyncClient) -> None:
    rina = await register(client)

    wrong_password = await client.post(
        "/api/v1/auth/login", json={"email": rina.email, "password": "wrong-password"}
    )
    unknown_email = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )

    for response in (wrong_password, unknown_email):
        assert response.status_code == 401
        assert error_code(response) == "invalid_credentials"
        assert refresh_cookie(response) is None
    assert wrong_password.json()["error"]["message"] == unknown_email.json()["error"]["message"]


async def test_concurrent_duplicate_insert_maps_to_email_taken(db_session: AsyncSession) -> None:
    # The pre-check misses a user inserted by a concurrent request; the unique constraint wins.
    users = UserRepository(db_session)
    now = datetime(2026, 11, 1, tzinfo=UTC)
    await users.add(User(email="race@example.com", name="A", password_hash="x", created_at=now))

    with pytest.raises(EmailAlreadyExistsError):
        await users.add(User(email="race@example.com", name="B", password_hash="x", created_at=now))

    # The failed insert rolled back only its savepoint; the session is still usable.
    assert (await users.get_by_email("race@example.com")) is not None

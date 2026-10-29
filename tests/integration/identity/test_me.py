import pytest
from httpx import AsyncClient

from tests.integration.helpers import (
    PASSWORD,
    error_code,
    login,
    post_with_cookie,
    register,
)

NEW_PASSWORD = "new-password-123"
REFRESH = "/api/v1/auth/refresh"


async def test_get_me(client: AsyncClient) -> None:
    rina = await register(client, name="Rina")

    response = await client.get("/api/v1/me", headers=rina.headers)

    assert response.status_code == 200
    assert response.json() == {"id": str(rina.id), "email": rina.email, "name": "Rina"}


async def test_rename_is_trimmed_and_persisted(client: AsyncClient) -> None:
    rina = await register(client)

    response = await client.patch("/api/v1/me", json={"name": "  Rina S. "}, headers=rina.headers)

    assert response.status_code == 200
    assert response.json()["name"] == "Rina S."
    assert (await client.get("/api/v1/me", headers=rina.headers)).json()["name"] == "Rina S."


@pytest.mark.parametrize("name", ["   ", "", "n" * 101])
async def test_invalid_name(client: AsyncClient, name: str) -> None:
    rina = await register(client)

    response = await client.patch("/api/v1/me", json={"name": name}, headers=rina.headers)

    assert response.status_code == 422
    assert [d["location"] for d in response.json()["error"]["details"]] == [["body", "name"]]


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/api/v1/me"), ("patch", "/api/v1/me"), ("post", "/api/v1/me/password")],
)
async def test_me_requires_a_token(client: AsyncClient, method: str, path: str) -> None:
    response = await client.request(method, path, json={})

    assert response.status_code == 401
    assert error_code(response) == "unauthorized"


async def change_password(
    client: AsyncClient, headers: dict[str, str], current: str, new: str
) -> int:
    response = await client.post(
        "/api/v1/me/password",
        json={"current_password": current, "new_password": new},
        headers=headers,
    )
    return response.status_code


async def test_change_password(client: AsyncClient) -> None:
    rina = await register(client)

    assert await change_password(client, rina.headers, PASSWORD, NEW_PASSWORD) == 204

    await login(client, rina.email, NEW_PASSWORD)
    old = await client.post("/api/v1/auth/login", json={"email": rina.email, "password": PASSWORD})
    assert old.status_code == 401
    assert error_code(old) == "invalid_credentials"


async def test_wrong_current_password(client: AsyncClient) -> None:
    rina = await register(client)

    response = await client.post(
        "/api/v1/me/password",
        json={"current_password": "wrong-password", "new_password": NEW_PASSWORD},
        headers=rina.headers,
    )

    assert response.status_code == 400
    assert error_code(response) == "invalid_current_password"
    await login(client, rina.email, PASSWORD)


async def test_new_password_too_short(client: AsyncClient) -> None:
    rina = await register(client)

    response = await client.post(
        "/api/v1/me/password",
        json={"current_password": PASSWORD, "new_password": "x" * 7},
        headers=rina.headers,
    )

    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert [d["location"] for d in details] == [["body", "new_password"]]


async def test_password_change_keeps_calling_session_only(client: AsyncClient) -> None:
    laptop = await register(client)
    phone = await login(client, laptop.email)

    assert await change_password(client, laptop.headers, PASSWORD, NEW_PASSWORD) == 204

    # The calling session: access token and refresh cookie still work.
    assert (await client.get("/api/v1/me", headers=laptop.headers)).status_code == 200
    assert (await post_with_cookie(client, REFRESH, laptop.refresh_token)).status_code == 200
    # The other session is signed out.
    other = await post_with_cookie(client, REFRESH, phone.refresh_token)
    assert other.status_code == 401
    assert error_code(other) == "invalid_refresh_token"

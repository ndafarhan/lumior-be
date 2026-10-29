from httpx import AsyncClient

from tests.integration.helpers import (
    FakeClock,
    error_code,
    post_with_cookie,
    refresh_cookie,
    register,
    set_cookie_headers,
    signed_in,
)

REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"


async def assert_invalid_refresh(client: AsyncClient, token: str | None) -> None:
    response = await post_with_cookie(client, REFRESH, token)
    assert response.status_code == 401
    assert error_code(response) == "invalid_refresh_token"


async def test_refresh_rotates_without_authorization_header(client: AsyncClient) -> None:
    rina = await register(client)

    response = await post_with_cookie(client, REFRESH, rina.refresh_token)

    assert response.status_code == 200
    session = signed_in(response)
    assert session.id == rina.id
    assert session.refresh_token != rina.refresh_token
    assert response.json()["expires_in"] == 900
    assert (await client.get("/api/v1/me", headers=session.headers)).status_code == 200


async def test_refreshed_cookie_has_renewed_lifetime(client: AsyncClient, clock: FakeClock) -> None:
    rina = await register(client)
    clock.advance(days=29)

    first = await post_with_cookie(client, REFRESH, rina.refresh_token)
    clock.advance(days=29)
    second = await post_with_cookie(client, REFRESH, refresh_cookie(first))

    assert second.status_code == 200
    assert "Max-Age=2592000" in set_cookie_headers(second)[0]


async def test_missing_or_unknown_cookie(client: AsyncClient) -> None:
    await assert_invalid_refresh(client, None)
    await assert_invalid_refresh(client, "")
    await assert_invalid_refresh(client, "never-issued")


async def test_expired_refresh_token(client: AsyncClient, clock: FakeClock) -> None:
    rina = await register(client)
    clock.advance(days=30)

    await assert_invalid_refresh(client, rina.refresh_token)


async def test_two_tabs_refresh_within_grace_window(client: AsyncClient, clock: FakeClock) -> None:
    rina = await register(client)

    first = await post_with_cookie(client, REFRESH, rina.refresh_token)
    clock.advance(seconds=29)
    second = await post_with_cookie(client, REFRESH, rina.refresh_token)

    assert first.status_code == 200
    assert second.status_code == 200
    for response in (first, second):
        session = signed_in(response)
        assert (await client.get("/api/v1/me", headers=session.headers)).status_code == 200
        # Each tab's new cookie is itself usable.
        follow_up = await post_with_cookie(client, REFRESH, session.refresh_token)
        assert follow_up.status_code == 200


async def test_replaced_token_rejected_after_grace_window(
    client: AsyncClient, clock: FakeClock
) -> None:
    rina = await register(client)
    first = await post_with_cookie(client, REFRESH, rina.refresh_token)
    assert first.status_code == 200

    clock.advance(seconds=31)

    await assert_invalid_refresh(client, rina.refresh_token)
    # The rotated token is unaffected.
    assert (await post_with_cookie(client, REFRESH, refresh_cookie(first))).status_code == 200


async def test_logout_revokes_and_clears_cookie(client: AsyncClient) -> None:
    rina = await register(client)

    response = await post_with_cookie(client, LOGOUT, rina.refresh_token)

    assert response.status_code == 204
    [cookie] = set_cookie_headers(response)
    assert cookie.startswith('lumior_refresh=""') or cookie.startswith("lumior_refresh=;")
    assert "Path=/api/v1/auth" in cookie
    assert "Max-Age=0" in cookie
    await assert_invalid_refresh(client, rina.refresh_token)


async def test_logout_revokes_grace_window_sibling(client: AsyncClient) -> None:
    rina = await register(client)
    first = await post_with_cookie(client, REFRESH, rina.refresh_token)
    second = await post_with_cookie(client, REFRESH, rina.refresh_token)

    await post_with_cookie(client, LOGOUT, refresh_cookie(first))

    await assert_invalid_refresh(client, refresh_cookie(second))
    await assert_invalid_refresh(client, rina.refresh_token)


async def test_logout_keeps_other_sessions(client: AsyncClient) -> None:
    rina = await register(client)
    # A separate sign-in is a separate session.
    login = await client.post(
        "/api/v1/auth/login", json={"email": rina.email, "password": "correct-horse-battery"}
    )
    client.cookies.clear()

    await post_with_cookie(client, LOGOUT, refresh_cookie(login))

    response = await post_with_cookie(client, REFRESH, rina.refresh_token)
    assert response.status_code == 200


async def test_logout_without_valid_cookie_is_204(client: AsyncClient) -> None:
    for token in (None, "", "never-issued"):
        response = await post_with_cookie(client, LOGOUT, token)
        assert response.status_code == 204

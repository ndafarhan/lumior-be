from datetime import datetime

from httpx import AsyncClient

from tests.integration.helpers import (
    FakeClock,
    SignedIn,
    create_household,
    error_code,
    join,
    login,
    register,
)


async def create_invite(client: AsyncClient, owner: SignedIn, household: str) -> str:
    response = await client.post(f"/api/v1/households/{household}/invites", headers=owner.headers)
    assert response.status_code == 201, response.text
    code: str = response.json()["code"]
    return code


async def test_owner_creates_invite(client: AsyncClient, clock: FakeClock) -> None:
    rina = await register(client)
    household = await create_household(client, rina)
    created_at = clock.current

    response = await client.post(f"/api/v1/households/{household}/invites", headers=rina.headers)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"code", "expires_at"}
    assert all(c.isalnum() or c in "-_" for c in body["code"])
    assert len(body["code"]) >= 22
    assert body["expires_at"].endswith("Z")
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert abs((expires_at - created_at).total_seconds() - 7 * 86400) < 1


async def test_member_cannot_create_invite(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    household = await create_household(client, rina)
    await join(client, rina, household, budi)

    response = await client.post(f"/api/v1/households/{household}/invites", headers=budi.headers)

    assert response.status_code == 403
    assert error_code(response) == "owner_required"


async def test_several_open_invites(client: AsyncClient) -> None:
    rina, budi, sari = [await register(client, n) for n in ("Rina", "Budi", "Sari")]
    household = await create_household(client, rina)
    first, second = (
        await create_invite(client, rina, household),
        await create_invite(client, rina, household),
    )

    assert first != second
    for code, user in ((first, budi), (second, sari)):
        accepted = await client.post(f"/api/v1/invites/{code}/accept", headers=user.headers)
        assert accepted.status_code == 200


async def test_preview_by_new_user(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    household = await create_household(client, rina, "Kos Jakarta")
    code = await create_invite(client, rina, household)

    response = await client.get(f"/api/v1/invites/{code}", headers=budi.headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "household_id",
        "household_name",
        "invited_by",
        "expires_at",
        "already_member",
    }
    assert body["household_id"] == household
    assert body["household_name"] == "Kos Jakarta"
    assert body["invited_by"] == "Rina"
    assert body["already_member"] is False
    assert body["expires_at"].endswith("Z")


async def test_preview_by_existing_member(client: AsyncClient) -> None:
    rina = await register(client, "Rina")
    household = await create_household(client, rina)
    code = await create_invite(client, rina, household)

    response = await client.get(f"/api/v1/invites/{code}", headers=rina.headers)

    assert response.status_code == 200
    assert response.json()["already_member"] is True


async def test_invite_endpoints_require_sign_in(client: AsyncClient) -> None:
    rina = await register(client)
    code = await create_invite(client, rina, await create_household(client, rina))

    for response in (
        await client.get(f"/api/v1/invites/{code}"),
        await client.post(f"/api/v1/invites/{code}/accept"),
    ):
        assert response.status_code == 401
        assert error_code(response) == "unauthorized"


async def assert_invite_error(
    client: AsyncClient, code: str, user: SignedIn, status: int, error: str
) -> None:
    for response in (
        await client.get(f"/api/v1/invites/{code}", headers=user.headers),
        await client.post(f"/api/v1/invites/{code}/accept", headers=user.headers),
    ):
        assert response.status_code == status, response.text
        assert error_code(response) == error


async def test_unknown_code(client: AsyncClient) -> None:
    budi = await register(client, "Budi")

    await assert_invite_error(client, "never-issued", budi, 404, "invite_not_found")


async def test_expired_invite(client: AsyncClient, clock: FakeClock) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    code = await create_invite(client, rina, await create_household(client, rina))

    clock.advance(days=6, hours=23)
    budi = await login(client, budi.email)  # access tokens last 15 minutes
    assert (await client.get(f"/api/v1/invites/{code}", headers=budi.headers)).status_code == 200
    clock.advance(hours=1)
    budi = await login(client, budi.email)

    await assert_invite_error(client, code, budi, 410, "invite_expired")


async def test_used_invite(client: AsyncClient) -> None:
    rina, budi, sari = [await register(client, n) for n in ("Rina", "Budi", "Sari")]
    code = await create_invite(client, rina, await create_household(client, rina))
    await client.post(f"/api/v1/invites/{code}/accept", headers=budi.headers)

    await assert_invite_error(client, code, sari, 410, "invite_used")


async def test_used_wins_over_expired(client: AsyncClient, clock: FakeClock) -> None:
    rina, budi, sari = [await register(client, n) for n in ("Rina", "Budi", "Sari")]
    code = await create_invite(client, rina, await create_household(client, rina))
    await client.post(f"/api/v1/invites/{code}/accept", headers=budi.headers)
    clock.advance(days=8)
    sari = await login(client, sari.email)

    await assert_invite_error(client, code, sari, 410, "invite_used")


async def test_accept_joins_as_member(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    own = await create_household(client, budi, "Budi's")
    household = await create_household(client, rina, "Rumah")
    code = await create_invite(client, rina, household)

    response = await client.post(f"/api/v1/invites/{code}/accept", headers=budi.headers)

    assert response.status_code == 200
    assert response.json() == {
        "id": household,
        "name": "Rumah",
        "role": "member",
        "member_count": 2,
        "currency": "IDR",
    }
    listed = (await client.get("/api/v1/households", headers=budi.headers)).json()
    assert [h["id"] for h in listed] == [own, household]


async def test_already_member_does_not_consume_invite(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    code = await create_invite(client, rina, await create_household(client, rina))

    response = await client.post(f"/api/v1/invites/{code}/accept", headers=rina.headers)

    assert response.status_code == 409
    assert error_code(response) == "already_member"
    accepted = await client.post(f"/api/v1/invites/{code}/accept", headers=budi.headers)
    assert accepted.status_code == 200

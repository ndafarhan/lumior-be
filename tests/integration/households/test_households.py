import uuid

import pytest
from httpx import AsyncClient

from tests.integration.helpers import (
    SignedIn,
    create_household,
    error_code,
    join,
    register,
)


async def list_households(client: AsyncClient, user: SignedIn) -> list[dict[str, object]]:
    response = await client.get("/api/v1/households", headers=user.headers)
    assert response.status_code == 200
    households: list[dict[str, object]] = response.json()
    return households


async def test_create_household(client: AsyncClient) -> None:
    rina = await register(client)

    response = await client.post(
        "/api/v1/households", json={"name": " Rumah Bandung "}, headers=rina.headers
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name", "role", "member_count", "currency"}
    assert body["name"] == "Rumah Bandung"
    assert body["role"] == "owner"
    assert body["member_count"] == 1
    assert body["currency"] == "IDR"


@pytest.mark.parametrize("name", ["n" * 101, "   "])
async def test_create_with_invalid_name(client: AsyncClient, name: str) -> None:
    rina = await register(client)

    response = await client.post("/api/v1/households", json={"name": name}, headers=rina.headers)

    assert response.status_code == 422
    assert [d["location"] for d in response.json()["error"]["details"]] == [["body", "name"]]


async def test_create_without_token_has_no_effect(client: AsyncClient) -> None:
    rina = await register(client)

    response = await client.post(
        "/api/v1/households", json={"name": "Rumah"}, headers={"Authorization": "Bearer nope"}
    )

    assert response.status_code == 401
    assert error_code(response) == "unauthorized"
    assert await list_households(client, rina) == []


async def test_list_is_ordered_by_join_time_with_roles(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    a = await create_household(client, rina, "A")
    b = await create_household(client, budi, "B")
    await join(client, budi, b, rina)
    await create_household(client, budi, "Hidden from Rina")

    households = await list_households(client, rina)

    assert [(h["id"], h["role"]) for h in households] == [(a, "owner"), (b, "member")]
    assert households[1]["member_count"] == 2


async def test_list_without_households_is_empty(client: AsyncClient) -> None:
    assert await list_households(client, await register(client)) == []


async def test_owner_view_counts_all_members(client: AsyncClient) -> None:
    rina = await register(client, "Rina")
    household = await create_household(client, rina)
    for name in ("Budi", "Sari"):
        await join(client, rina, household, await register(client, name))

    [view] = await list_households(client, rina)

    assert view["role"] == "owner"
    assert view["member_count"] == 3


async def test_owner_renames(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    household = await create_household(client, rina)
    await join(client, rina, household, budi)

    response = await client.patch(
        f"/api/v1/households/{household}", json={"name": " Kos Jakarta "}, headers=rina.headers
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": household,
        "name": "Kos Jakarta",
        "role": "owner",
        "member_count": 2,
        "currency": "IDR",
    }
    assert (await list_households(client, budi))[0]["name"] == "Kos Jakarta"


async def test_owner_rename_with_invalid_name(client: AsyncClient) -> None:
    rina = await register(client)
    household = await create_household(client, rina)

    response = await client.patch(
        f"/api/v1/households/{household}", json={"name": ""}, headers=rina.headers
    )

    assert response.status_code == 422


async def test_member_cannot_rename(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    household = await create_household(client, rina, "Rumah")
    await join(client, rina, household, budi)

    response = await client.patch(
        f"/api/v1/households/{household}", json={"name": "Mine"}, headers=budi.headers
    )

    assert response.status_code == 403
    assert error_code(response) == "owner_required"
    assert (await list_households(client, rina))[0]["name"] == "Rumah"


async def test_list_members_in_join_order(client: AsyncClient) -> None:
    rina, budi, sari = [await register(client, n) for n in ("Rina", "Budi", "Sari")]
    household = await create_household(client, rina)
    await join(client, rina, household, budi)
    await join(client, rina, household, sari)

    response = await client.get(f"/api/v1/households/{household}/members", headers=budi.headers)

    assert response.status_code == 200
    assert response.json() == [
        {"user_id": str(rina.id), "name": "Rina", "email": rina.email, "role": "owner"},
        {"user_id": str(budi.id), "name": "Budi", "email": budi.email, "role": "member"},
        {"user_id": str(sari.id), "name": "Sari", "email": sari.email, "role": "member"},
    ]


async def household_with_member(client: AsyncClient) -> tuple[SignedIn, SignedIn, str]:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    household = await create_household(client, rina)
    await join(client, rina, household, budi)
    return rina, budi, household


async def remove(client: AsyncClient, caller: SignedIn, household: str, user_id: object) -> int:
    response = await client.delete(
        f"/api/v1/households/{household}/members/{user_id}", headers=caller.headers
    )
    return response.status_code


async def test_member_leaves(client: AsyncClient) -> None:
    _, budi, household = await household_with_member(client)

    assert await remove(client, budi, household, budi.id) == 204

    response = await client.get(f"/api/v1/households/{household}/members", headers=budi.headers)
    assert response.status_code == 403
    assert error_code(response) == "not_a_member"
    assert await list_households(client, budi) == []


async def test_owner_removes_member(client: AsyncClient) -> None:
    rina, budi, household = await household_with_member(client)

    assert await remove(client, rina, household, budi.id) == 204

    assert (await list_households(client, rina))[0]["member_count"] == 1
    response = await client.get(f"/api/v1/households/{household}/members", headers=budi.headers)
    assert error_code(response) == "not_a_member"


async def test_member_cannot_remove_someone_else(client: AsyncClient) -> None:
    rina, budi, household = await household_with_member(client)
    sari = await register(client, "Sari")
    await join(client, rina, household, sari)

    for target in (sari.id, rina.id, uuid.uuid4()):
        response = await client.delete(
            f"/api/v1/households/{household}/members/{target}", headers=budi.headers
        )
        assert response.status_code == 403
        assert error_code(response) == "owner_required"
    assert (await list_households(client, rina))[0]["member_count"] == 3


async def test_owner_cannot_leave(client: AsyncClient) -> None:
    rina, _, household = await household_with_member(client)

    response = await client.delete(
        f"/api/v1/households/{household}/members/{rina.id}", headers=rina.headers
    )

    assert response.status_code == 409
    assert error_code(response) == "owner_cannot_leave"
    assert (await list_households(client, rina))[0]["member_count"] == 2


@pytest.mark.parametrize("target", ["not-a-uuid", "registered-outsider", "random-uuid"])
async def test_owner_removes_non_member(client: AsyncClient, target: str) -> None:
    rina, _, household = await household_with_member(client)
    outsider = await register(client, "Outsider")
    user_id = {
        "not-a-uuid": "not-a-uuid",
        "registered-outsider": str(outsider.id),
        "random-uuid": str(uuid.uuid4()),
    }[target]

    response = await client.delete(
        f"/api/v1/households/{household}/members/{user_id}", headers=rina.headers
    )

    assert response.status_code == 404
    assert error_code(response) == "member_not_found"

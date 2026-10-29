"""Expense categories (specs/expense-categories)."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response

from lumior.modules.expenses.defaults import DEFAULT_CATEGORY_NAMES
from tests.integration.helpers import SignedIn, create_household, error_code, join, register


def categories_path(household: str) -> str:
    return f"/api/v1/households/{household}/expense-categories"


async def list_categories(
    client: AsyncClient, user: SignedIn, household: str
) -> list[dict[str, Any]]:
    response = await client.get(categories_path(household), headers=user.headers)
    assert response.status_code == 200, response.text
    categories: list[dict[str, Any]] = response.json()
    return categories


async def create_category(
    client: AsyncClient, user: SignedIn, household: str, name: str
) -> Response:
    return await client.post(categories_path(household), json={"name": name}, headers=user.headers)


async def update_category(
    client: AsyncClient, user: SignedIn, household: str, category_id: str, body: dict[str, Any]
) -> Response:
    return await client.patch(
        f"{categories_path(household)}/{category_id}", json=body, headers=user.headers
    )


def by_name(categories: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(c for c in categories if c["name"] == name)


async def owner_and_member(client: AsyncClient) -> tuple[SignedIn, SignedIn, str]:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    household = await create_household(client, rina)
    await join(client, rina, household, budi)
    return rina, budi, household


def detail_locations(response: Response) -> list[list[str]]:
    return [d["location"] for d in response.json()["error"]["details"]]


async def test_member_lists_default_categories(client: AsyncClient) -> None:
    _, budi, household = await owner_and_member(client)

    categories = await list_categories(client, budi, household)

    assert {c["name"] for c in categories} == set(DEFAULT_CATEGORY_NAMES)
    assert all(set(c) == {"id", "name", "archived"} for c in categories)
    assert not any(c["archived"] for c in categories)


async def test_non_member_cannot_list(client: AsyncClient) -> None:
    rina, outsider = await register(client, "Rina"), await register(client, "Out")
    household = await create_household(client, rina)

    response = await client.get(categories_path(household), headers=outsider.headers)

    assert response.status_code == 403
    assert error_code(response) == "not_a_member"


async def test_unknown_household(client: AsyncClient) -> None:
    rina = await register(client)

    response = await client.get(categories_path(str(uuid.uuid4())), headers=rina.headers)

    assert response.status_code == 404
    assert error_code(response) == "household_not_found"


async def test_non_member_with_invalid_body_gets_403(client: AsyncClient) -> None:
    rina, outsider = await register(client, "Rina"), await register(client, "Out")
    household = await create_household(client, rina)

    response = await create_category(client, outsider, household, "   ")

    assert response.status_code == 403
    assert error_code(response) == "not_a_member"


async def test_list_ordered_by_name_ignoring_case_with_archived(client: AsyncClient) -> None:
    rina, _, household = await owner_and_member(client)
    books = (await create_category(client, rina, household, "Books")).json()
    await create_category(client, rina, household, "pets")
    await update_category(client, rina, household, books["id"], {"archived": True})

    names = [c["name"] for c in await list_categories(client, rina, household)]

    assert names == sorted(names, key=str.lower)
    assert names.index("Books") < names.index("Dining out") < names.index("pets")
    assert by_name(await list_categories(client, rina, household), "Books")["archived"] is True


async def test_other_households_categories_hidden(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    mine = await create_household(client, rina)
    other = await create_household(client, budi)
    await create_category(client, budi, other, "Only in other")

    names = {c["name"] for c in await list_categories(client, rina, mine)}

    assert names == set(DEFAULT_CATEGORY_NAMES)


async def test_member_creates_trimmed_category(client: AsyncClient) -> None:
    _, budi, household = await owner_and_member(client)

    response = await create_category(client, budi, household, " Pets ")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Pets"
    assert body["archived"] is False
    assert by_name(await list_categories(client, budi, household), "Pets")["id"] == body["id"]


@pytest.mark.parametrize("name", ["n" * 51, "   "])
async def test_create_with_invalid_name(client: AsyncClient, name: str) -> None:
    rina = await register(client)
    household = await create_household(client, rina)

    response = await create_category(client, rina, household, name)

    assert response.status_code == 422
    assert detail_locations(response) == [["body", "name"]]


async def test_duplicate_name_ignoring_case(client: AsyncClient) -> None:
    rina = await register(client)
    household = await create_household(client, rina)

    response = await create_category(client, rina, household, "groceries")

    assert response.status_code == 409
    assert error_code(response) == "category_name_taken"
    assert detail_locations(response) == [["body", "name"]]


async def test_rename_to_archived_categorys_name(client: AsyncClient) -> None:
    rina = await register(client)
    household = await create_household(client, rina)
    categories = await list_categories(client, rina, household)
    await update_category(
        client, rina, household, by_name(categories, "Health")["id"], {"archived": True}
    )

    response = await update_category(
        client, rina, household, by_name(categories, "Other")["id"], {"name": "health"}
    )

    assert response.status_code == 409
    assert error_code(response) == "category_name_taken"


async def test_same_name_in_another_household(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    await create_category(client, budi, await create_household(client, budi), "Pets")

    response = await create_category(client, rina, await create_household(client, rina), "Pets")

    assert response.status_code == 201


async def test_rename_to_own_name_in_another_case(client: AsyncClient) -> None:
    rina = await register(client)
    household = await create_household(client, rina)
    groceries = by_name(await list_categories(client, rina, household), "Groceries")

    response = await update_category(
        client, rina, household, groceries["id"], {"name": "groceries"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "groceries"


async def test_rename_keeps_archived(client: AsyncClient) -> None:
    _, budi, household = await owner_and_member(client)
    groceries = by_name(await list_categories(client, budi, household), "Groceries")

    response = await update_category(client, budi, household, groceries["id"], {"name": "Food"})

    assert response.status_code == 200
    assert response.json() == {"id": groceries["id"], "name": "Food", "archived": False}


async def test_archive_and_restore(client: AsyncClient) -> None:
    rina = await register(client)
    household = await create_household(client, rina)
    groceries = by_name(await list_categories(client, rina, household), "Groceries")

    archived = await update_category(client, rina, household, groceries["id"], {"archived": True})
    restored = await update_category(client, rina, household, groceries["id"], {"archived": False})

    assert (archived.status_code, archived.json()["archived"]) == (200, True)
    assert (restored.status_code, restored.json()["archived"]) == (200, False)
    assert restored.json()["name"] == "Groceries"


@pytest.mark.parametrize("body", [{"name": None}, {"archived": None}, {"archived": "maybe"}])
async def test_update_rejects_null_and_bad_values(
    client: AsyncClient, body: dict[str, Any]
) -> None:
    rina = await register(client)
    household = await create_household(client, rina)
    groceries = by_name(await list_categories(client, rina, household), "Groceries")

    response = await update_category(client, rina, household, groceries["id"], body)

    assert response.status_code == 422
    assert detail_locations(response) == [["body", next(iter(body))]]


@pytest.mark.parametrize("category_id", ["not-a-uuid", str(uuid.uuid4()), "other-household"])
async def test_unknown_category(client: AsyncClient, category_id: str) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    household = await create_household(client, rina)
    if category_id == "other-household":
        other = await create_household(client, budi)
        category_id = (await list_categories(client, budi, other))[0]["id"]

    response = await update_category(client, rina, household, category_id, {"name": "Taken"})

    assert response.status_code == 404
    assert error_code(response) == "category_not_found"


async def test_other_households_category_unchanged(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    household = await create_household(client, rina)
    other = await create_household(client, budi)
    target = by_name(await list_categories(client, budi, other), "Groceries")

    await update_category(client, rina, household, target["id"], {"name": "Hacked"})

    assert by_name(await list_categories(client, budi, other), "Groceries") == target


async def test_delete_is_not_available(client: AsyncClient) -> None:
    rina = await register(client)
    household = await create_household(client, rina)
    groceries = by_name(await list_categories(client, rina, household), "Groceries")

    response = await client.delete(
        f"{categories_path(household)}/{groceries['id']}", headers=rina.headers
    )

    assert response.status_code == 405
    assert by_name(await list_categories(client, rina, household), "Groceries") == groceries

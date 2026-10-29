"""Listing expenses by month, with a category filter and cursor pagination (specs/expenses)."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response

from tests.integration.expenses.support import add_expense, base, category_ids, detail_locations
from tests.integration.helpers import SignedIn, create_household, error_code, register


async def setup(client: AsyncClient) -> tuple[SignedIn, str, dict[str, str]]:
    rina = await register(client)
    household = await create_household(client, rina)
    return rina, household, await category_ids(client, rina, household)


async def list_expenses(
    client: AsyncClient, user: SignedIn, household: str, **params: Any
) -> Response:
    return await client.get(f"{base(household)}/expenses", params=params, headers=user.headers)


async def ok_page(client: AsyncClient, user: SignedIn, household: str, **params: Any) -> Any:
    response = await list_expenses(client, user, household, **params)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"items", "next_cursor"}
    return response.json()


async def test_month_and_order(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    other = categories["Other"]
    await add_expense(client, rina, household, other, spent_on="2026-09-30")
    first_of_month = await add_expense(client, rina, household, other, spent_on="2026-10-01")
    older = await add_expense(client, rina, household, other, spent_on="2026-10-03")
    newer = await add_expense(client, rina, household, other, spent_on="2026-10-03")
    await add_expense(client, rina, household, other, spent_on="2026-11-01")

    page = await ok_page(client, rina, household, month="2026-10")

    assert [e["id"] for e in page["items"]] == [newer["id"], older["id"], first_of_month["id"]]
    assert page["next_cursor"] is None


@pytest.mark.parametrize("params", [{"month": "2026-13"}, {"month": "2026-1"}, {}])
async def test_invalid_month(client: AsyncClient, params: dict[str, str]) -> None:
    rina, household, _ = await setup(client)

    response = await list_expenses(client, rina, household, **params)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    assert detail_locations(response) == [["query", "month"]]


async def test_empty_month(client: AsyncClient) -> None:
    rina, household, _ = await setup(client)

    assert await ok_page(client, rina, household, month="2026-10") == {
        "items": [],
        "next_cursor": None,
    }


async def test_filter_by_category(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    ride = await add_expense(client, rina, household, categories["Transport"])
    await add_expense(client, rina, household, categories["Groceries"])

    page = await ok_page(
        client, rina, household, month="2026-10", category_id=categories["Transport"]
    )

    assert [e["id"] for e in page["items"]] == [ride["id"]]


@pytest.mark.parametrize("category_id", ["other-household", "unknown", "not-a-uuid"])
async def test_unknown_category_filter_gives_empty_page(
    client: AsyncClient, category_id: str
) -> None:
    rina, household, categories = await setup(client)
    await add_expense(client, rina, household, categories["Other"])
    if category_id == "other-household":
        budi = await register(client, "Budi")
        other = await create_household(client, budi)
        category_id = (await category_ids(client, budi, other))["Other"]
    elif category_id == "unknown":
        category_id = str(uuid.uuid4())

    page = await ok_page(client, rina, household, month="2026-10", category_id=category_id)

    assert page == {"items": [], "next_cursor": None}


async def walk(client: AsyncClient, user: SignedIn, household: str, limit: int) -> list[list[str]]:
    pages: list[list[str]] = []
    params: dict[str, Any] = {"month": "2026-10", "limit": limit}
    while True:
        page = await ok_page(client, user, household, **params)
        pages.append([e["id"] for e in page["items"]])
        if page["next_cursor"] is None:
            return pages
        params["cursor"] = page["next_cursor"]


async def test_walk_all_pages(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    for day in ("01", "02", "02", "03", "04"):
        await add_expense(client, rina, household, categories["Other"], spent_on=f"2026-10-{day}")
    everything = [
        e["id"] for e in (await ok_page(client, rina, household, month="2026-10"))["items"]
    ]

    pages = await walk(client, rina, household, limit=2)

    assert [len(p) for p in pages] == [2, 2, 1]
    assert [i for p in pages for i in p] == everything


async def test_default_limit(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    for _ in range(51):
        await add_expense(client, rina, household, categories["Other"])

    page = await ok_page(client, rina, household, month="2026-10")

    assert len(page["items"]) == 50
    assert page["next_cursor"] is not None
    rest = await ok_page(client, rina, household, month="2026-10", cursor=page["next_cursor"])
    assert len(rest["items"]) == 1
    assert rest["next_cursor"] is None


async def test_expense_added_between_pages_is_not_repeated(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    for day in ("01", "02", "03"):
        await add_expense(client, rina, household, categories["Other"], spent_on=f"2026-10-{day}")
    first = await ok_page(client, rina, household, month="2026-10", limit=2)
    # Newer than everything, so it sorts before the cursor and stays out of later pages.
    await add_expense(client, rina, household, categories["Other"], spent_on="2026-10-31")

    second = await ok_page(
        client, rina, household, month="2026-10", limit=2, cursor=first["next_cursor"]
    )

    seen = [e["id"] for e in first["items"] + second["items"]]
    assert len(seen) == len(set(seen)) == 3
    assert [e["spent_on"] for e in second["items"]] == ["2026-10-01"]


@pytest.mark.parametrize(
    ("params", "location"),
    [
        ({"cursor": "not-a-cursor"}, ["query", "cursor"]),
        ({"limit": 101}, ["query", "limit"]),
        ({"limit": 0}, ["query", "limit"]),
    ],
)
async def test_invalid_cursor_and_limit(
    client: AsyncClient, params: dict[str, Any], location: list[str]
) -> None:
    rina, household, _ = await setup(client)

    response = await list_expenses(client, rina, household, month="2026-10", **params)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    assert detail_locations(response) == [location]


async def test_non_member_cannot_list(client: AsyncClient) -> None:
    _, household, _ = await setup(client)
    outsider = await register(client, "Out")

    response = await list_expenses(client, outsider, household, month="2026-13")

    assert response.status_code == 403
    assert error_code(response) == "not_a_member"

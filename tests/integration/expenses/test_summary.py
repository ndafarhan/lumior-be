"""The monthly summary (specs/expenses)."""

from typing import Any

from httpx import AsyncClient, Response

from tests.integration.expenses.support import (
    add_expense,
    archive,
    base,
    category_ids,
    detail_locations,
)
from tests.integration.helpers import SignedIn, create_household, error_code, register


async def summary(client: AsyncClient, user: SignedIn, household: str, **params: Any) -> Response:
    return await client.get(
        f"{base(household)}/expense-summary", params=params, headers=user.headers
    )


async def test_summary(client: AsyncClient) -> None:
    rina = await register(client)
    household = await create_household(client, rina)
    categories = await category_ids(client, rina, household)
    groceries, transport = categories["Groceries"], categories["Transport"]
    await add_expense(client, rina, household, groceries, amount="45000.00")
    await add_expense(client, rina, household, transport, amount="20000.00")
    await add_expense(client, rina, household, groceries, amount="30000.00")
    await add_expense(client, rina, household, transport, amount="99000.00", spent_on="2026-09-30")

    response = await summary(client, rina, household, month="2026-10")

    assert response.status_code == 200
    assert response.json() == {
        "month": "2026-10",
        "total": {"amount": "95000.00", "currency": "IDR"},
        "categories": [
            {
                "category_id": groceries,
                "total": {"amount": "75000.00", "currency": "IDR"},
                "count": 2,
            },
            {
                "category_id": transport,
                "total": {"amount": "20000.00", "currency": "IDR"},
                "count": 1,
            },
        ],
    }


async def test_empty_month(client: AsyncClient) -> None:
    rina = await register(client)
    idr = await create_household(client, rina)
    jpy = await create_household(client, rina, currency="JPY")

    idr_summary = (await summary(client, rina, idr, month="2026-10")).json()
    jpy_summary = (await summary(client, rina, jpy, month="2026-10")).json()

    assert idr_summary["total"] == {"amount": "0.00", "currency": "IDR"}
    assert jpy_summary["total"] == {"amount": "0", "currency": "JPY"}
    assert idr_summary["categories"] == jpy_summary["categories"] == []


async def test_archived_category_still_counted(client: AsyncClient) -> None:
    rina = await register(client)
    household = await create_household(client, rina)
    health = (await category_ids(client, rina, household))["Health"]
    await add_expense(client, rina, household, health, amount="12000.00")
    await archive(client, rina, household, health)

    body = (await summary(client, rina, household, month="2026-10")).json()

    assert [c["category_id"] for c in body["categories"]] == [health]


async def test_no_rounding_drift(client: AsyncClient) -> None:
    rina = await register(client)
    household = await create_household(client, rina, currency="USD")
    other = (await category_ids(client, rina, household))["Other"]
    for _ in range(3):
        await add_expense(client, rina, household, other, amount="0.10", currency="USD")

    body = (await summary(client, rina, household, month="2026-10")).json()

    assert body["total"] == {"amount": "0.30", "currency": "USD"}


async def test_other_households_not_counted(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    mine = await create_household(client, rina)
    other = await create_household(client, budi)
    await add_expense(client, budi, other, (await category_ids(client, budi, other))["Other"])

    body = (await summary(client, rina, mine, month="2026-10")).json()

    assert body["categories"] == []


async def test_invalid_month(client: AsyncClient) -> None:
    rina = await register(client)
    household = await create_household(client, rina)

    missing = await summary(client, rina, household)
    invalid = await summary(client, rina, household, month="2026-13")

    for response in (missing, invalid):
        assert response.status_code == 422
        assert error_code(response) == "validation_error"
        assert detail_locations(response) == [["query", "month"]]

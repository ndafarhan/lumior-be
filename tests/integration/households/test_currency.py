"""Household currency and the default expense categories (specs/households)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumior.modules.expenses.defaults import DEFAULT_CATEGORY_NAMES
from lumior.modules.expenses.models import ExpenseCategory
from lumior.modules.households.models import Household
from tests.integration.helpers import create_household, register


async def test_create_with_currency(client: AsyncClient) -> None:
    rina = await register(client)

    response = await client.post(
        "/api/v1/households", json={"name": "Tokyo", "currency": "JPY"}, headers=rina.headers
    )

    assert response.status_code == 201
    assert response.json()["currency"] == "JPY"


async def test_unsupported_currency(client: AsyncClient, db_session: AsyncSession) -> None:
    rina = await register(client)

    response = await client.post(
        "/api/v1/households", json={"name": "Rumah", "currency": "XYZ"}, headers=rina.headers
    )

    assert response.status_code == 422
    assert [d["location"] for d in response.json()["error"]["details"]] == [["body", "currency"]]
    assert (
        await db_session.scalars(select(Household).where(Household.name == "Rumah"))
    ).all() == []


async def test_currency_on_every_household_response(client: AsyncClient) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    household = await create_household(client, rina, currency="USD")

    listed = await client.get("/api/v1/households", headers=rina.headers)
    renamed = await client.patch(
        f"/api/v1/households/{household}", json={"name": "Kos"}, headers=rina.headers
    )
    invite = await client.post(f"/api/v1/households/{household}/invites", headers=rina.headers)
    accepted = await client.post(
        f"/api/v1/invites/{invite.json()['code']}/accept", headers=budi.headers
    )

    assert listed.json()[0]["currency"] == "USD"
    assert renamed.json()["currency"] == "USD"
    assert accepted.json()["currency"] == "USD"


async def test_rename_cannot_change_currency(client: AsyncClient) -> None:
    rina = await register(client)
    household = await create_household(client, rina)

    response = await client.patch(
        f"/api/v1/households/{household}",
        json={"name": "Kos Jakarta", "currency": "USD"},
        headers=rina.headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Kos Jakarta"
    assert response.json()["currency"] == "IDR"


async def test_new_household_gets_default_categories(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    rina = await register(client)
    household = await create_household(client, rina)

    categories = (
        await db_session.scalars(
            select(ExpenseCategory).where(ExpenseCategory.household_id == uuid.UUID(household))
        )
    ).all()

    assert sorted(c.name for c in categories) == sorted(DEFAULT_CATEGORY_NAMES)
    assert not any(c.archived for c in categories)

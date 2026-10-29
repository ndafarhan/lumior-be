"""Helpers for expense API tests."""

from typing import Any

from httpx import AsyncClient, Response

from tests.integration.helpers import SignedIn


def base(household: str) -> str:
    return f"/api/v1/households/{household}"


async def category_ids(client: AsyncClient, user: SignedIn, household: str) -> dict[str, str]:
    """Category name → id, for the household's categories."""
    response = await client.get(f"{base(household)}/expense-categories", headers=user.headers)
    assert response.status_code == 200, response.text
    return {c["name"]: c["id"] for c in response.json()}


async def archive(client: AsyncClient, user: SignedIn, household: str, category_id: str) -> None:
    response = await client.patch(
        f"{base(household)}/expense-categories/{category_id}",
        json={"archived": True},
        headers=user.headers,
    )
    assert response.status_code == 200, response.text


def expense_body(
    category_id: str,
    amount: str = "45000.00",
    spent_on: str = "2026-10-03",
    currency: str = "IDR",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "amount": {"amount": amount, "currency": currency},
        "spent_on": spent_on,
        "category_id": category_id,
        **extra,
    }


async def post_expense(
    client: AsyncClient, user: SignedIn, household: str, body: dict[str, Any]
) -> Response:
    return await client.post(f"{base(household)}/expenses", json=body, headers=user.headers)


async def add_expense(
    client: AsyncClient, user: SignedIn, household: str, category_id: str, **fields: Any
) -> dict[str, Any]:
    response = await post_expense(client, user, household, expense_body(category_id, **fields))
    assert response.status_code == 201, response.text
    expense: dict[str, Any] = response.json()
    return expense


async def patch_expense(
    client: AsyncClient, user: SignedIn, household: str, expense_id: str, body: dict[str, Any]
) -> Response:
    return await client.patch(
        f"{base(household)}/expenses/{expense_id}", json=body, headers=user.headers
    )


def detail_locations(response: Response) -> list[list[str]]:
    return [d["location"] for d in response.json()["error"]["details"]]

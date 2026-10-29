"""Creating, updating, and deleting expenses (specs/expenses)."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.expenses.support import (
    add_expense,
    archive,
    base,
    category_ids,
    detail_locations,
    expense_body,
    patch_expense,
    post_expense,
)
from tests.integration.helpers import (
    FakeClock,
    SignedIn,
    create_household,
    error_code,
    join,
    register,
)


async def setup(client: AsyncClient, currency: str = "IDR") -> tuple[SignedIn, str, dict[str, str]]:
    rina = await register(client)
    household = await create_household(client, rina, currency=currency)
    return rina, household, await category_ids(client, rina, household)


async def test_create(client: AsyncClient, clock: FakeClock) -> None:
    rina, household, categories = await setup(client)
    now = clock.current

    response = await post_expense(
        client,
        rina,
        household,
        expense_body(categories["Groceries"], note="Weekly market"),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id", "amount", "spent_on", "category_id", "note", "created_at", "updated_at"
    }  # fmt: skip
    assert body["amount"] == {"amount": "45000.00", "currency": "IDR"}
    assert body["spent_on"] == "2026-10-03"
    assert body["category_id"] == categories["Groceries"]
    assert body["note"] == "Weekly market"
    assert body["created_at"] == body["updated_at"]
    assert datetime.fromisoformat(body["created_at"]) >= now
    listed = await client.get(
        f"{base(household)}/expenses", params={"month": "2026-10"}, headers=rina.headers
    )
    assert [e["id"] for e in listed.json()["items"]] == [body["id"]]


@pytest.mark.parametrize(
    ("currency", "amount", "returned"), [("IDR", "45000", "45000.00"), ("JPY", "1200", "1200")]
)
async def test_amount_has_the_currency_decimals(
    client: AsyncClient, currency: str, amount: str, returned: str
) -> None:
    rina, household, categories = await setup(client, currency)

    expense = await add_expense(
        client, rina, household, categories["Other"], amount=amount, currency=currency
    )

    assert expense["amount"] == {"amount": returned, "currency": currency}


async def test_member_who_is_not_owner_can_do_everything(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    budi = await register(client, "Budi")
    await join(client, rina, household, budi)

    expense = await add_expense(client, budi, household, categories["Transport"])
    updated = await patch_expense(client, budi, household, expense["id"], {"note": "Ojek"})
    listed = await client.get(
        f"{base(household)}/expenses", params={"month": "2026-10"}, headers=budi.headers
    )
    deleted = await client.delete(
        f"{base(household)}/expenses/{expense['id']}", headers=budi.headers
    )

    assert (updated.status_code, listed.status_code, deleted.status_code) == (200, 200, 204)


async def test_missing_field(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    body = expense_body(categories["Other"])
    del body["spent_on"]

    response = await post_expense(client, rina, household, body)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    assert detail_locations(response) == [["body", "spent_on"]]


@pytest.mark.parametrize(
    ("currency", "amount"),
    [
        ("IDR", "0"),
        ("IDR", "-5.00"),
        ("IDR", "10.005"),
        ("JPY", "10.5"),
        ("IDR", "1000000000000"),
        ("IDR", 45000),
    ],
)
async def test_invalid_amount(client: AsyncClient, currency: str, amount: Any) -> None:
    rina, household, categories = await setup(client, currency)
    body = expense_body(categories["Other"], currency=currency)
    body["amount"]["amount"] = amount

    response = await post_expense(client, rina, household, body)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    assert detail_locations(response) == [["body", "amount", "amount"]]


async def test_largest_amount(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)

    expense = await add_expense(
        client, rina, household, categories["Housing"], amount="999999999999.99"
    )

    assert expense["amount"]["amount"] == "999999999999.99"


async def test_currency_mismatch(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)

    response = await post_expense(
        client, rina, household, expense_body(categories["Other"], currency="USD", amount="5.00")
    )

    assert response.status_code == 422
    assert error_code(response) == "currency_mismatch"
    assert detail_locations(response) == [["body", "amount", "currency"]]


@pytest.mark.parametrize(
    ("spent_on", "status"),
    [
        ("2026-10-30", 201),
        ("2026-10-29", 201),
        ("2000-01-01", 201),
        ("2026-10-31", 422),
        ("1999-12-31", 422),
        ("2026-02-30", 422),
        ("not-a-date", 422),
    ],
)
async def test_spending_date_range(
    client: AsyncClient, clock: FakeClock, spent_on: str, status: int
) -> None:
    # Late in the UTC day, so the frontend's "tomorrow" is already today for some users.
    clock.current = datetime(2026, 10, 29, 23, 0, tzinfo=UTC)
    rina, household, categories = await setup(client)

    response = await post_expense(
        client, rina, household, expense_body(categories["Other"], spent_on=spent_on)
    )

    assert response.status_code == status, response.text
    if status == 422:
        assert error_code(response) == "validation_error"
        assert detail_locations(response) == [["body", "spent_on"]]


async def test_category_of_another_household(client: AsyncClient) -> None:
    rina, household, _ = await setup(client)
    budi = await register(client, "Budi")
    other = await create_household(client, budi)
    foreign = (await category_ids(client, budi, other))["Groceries"]

    response = await post_expense(client, rina, household, expense_body(foreign))

    assert response.status_code == 422
    assert error_code(response) == "category_not_found"
    assert detail_locations(response) == [["body", "category_id"]]


async def test_unknown_category_id(client: AsyncClient) -> None:
    rina, household, _ = await setup(client)

    response = await post_expense(client, rina, household, expense_body(str(uuid.uuid4())))

    assert response.status_code == 422
    assert error_code(response) == "category_not_found"


async def test_archived_category_on_create(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    await archive(client, rina, household, categories["Health"])

    response = await post_expense(client, rina, household, expense_body(categories["Health"]))

    assert response.status_code == 422
    assert error_code(response) == "category_archived"
    assert detail_locations(response) == [["body", "category_id"]]


@pytest.mark.parametrize(("note", "stored"), [("   ", None), (" Weekly market ", "Weekly market")])
async def test_note_normalized(client: AsyncClient, note: str, stored: str | None) -> None:
    rina, household, categories = await setup(client)

    expense = await add_expense(client, rina, household, categories["Other"], note=note)

    assert expense["note"] == stored


async def test_note_too_long(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)

    response = await post_expense(
        client, rina, household, expense_body(categories["Other"], note="n" * 501)
    )

    assert response.status_code == 422
    assert detail_locations(response) == [["body", "note"]]


async def test_schema_error_reported_before_service_errors(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    body = expense_body(categories["Other"], currency="USD", amount="5.00")
    del body["spent_on"]

    response = await post_expense(client, rina, household, body)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    assert detail_locations(response) == [["body", "spent_on"]]


async def test_partial_update(client: AsyncClient, clock: FakeClock) -> None:
    rina, household, categories = await setup(client)
    expense = await add_expense(client, rina, household, categories["Groceries"], note="Market")
    clock.advance(minutes=5)

    response = await patch_expense(
        client,
        rina,
        household,
        expense["id"],
        {"amount": {"amount": "50000.00", "currency": "IDR"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["amount"] == {"amount": "50000.00", "currency": "IDR"}
    unchanged = ("id", "spent_on", "category_id", "note", "created_at")
    assert {k: body[k] for k in unchanged} == {k: expense[k] for k in unchanged}
    assert body["updated_at"] > body["created_at"]


async def test_update_validates_sent_fields(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    expense = await add_expense(client, rina, household, categories["Other"])

    mismatch = await patch_expense(
        client, rina, household, expense["id"], {"amount": {"amount": "1.00", "currency": "USD"}}
    )
    too_late = await patch_expense(
        client, rina, household, expense["id"], {"spent_on": "2030-01-01"}
    )
    null_amount = await patch_expense(client, rina, household, expense["id"], {"amount": None})

    assert error_code(mismatch) == "currency_mismatch"
    assert detail_locations(too_late) == [["body", "spent_on"]]
    assert detail_locations(null_amount) == [["body", "amount"]]


async def test_clear_note(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    expense = await add_expense(client, rina, household, categories["Other"], note="Something")

    response = await patch_expense(client, rina, household, expense["id"], {"note": None})

    assert response.status_code == 200
    assert response.json()["note"] is None


async def test_move_to_archived_category(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    expense = await add_expense(client, rina, household, categories["Groceries"])
    await archive(client, rina, household, categories["Health"])

    response = await patch_expense(
        client, rina, household, expense["id"], {"category_id": categories["Health"]}
    )

    assert response.status_code == 422
    assert error_code(response) == "category_archived"
    listed = await client.get(
        f"{base(household)}/expenses", params={"month": "2026-10"}, headers=rina.headers
    )
    assert listed.json()["items"][0]["category_id"] == categories["Groceries"]


async def test_edit_expense_whose_category_was_archived_later(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    expense = await add_expense(client, rina, household, categories["Health"])
    await archive(client, rina, household, categories["Health"])

    response = await patch_expense(
        client,
        rina,
        household,
        expense["id"],
        {"note": "Vitamins", "category_id": categories["Health"]},
    )

    assert response.status_code == 200
    assert response.json()["note"] == "Vitamins"
    assert response.json()["category_id"] == categories["Health"]


async def test_delete_then_delete_again(client: AsyncClient) -> None:
    rina, household, categories = await setup(client)
    expense = await add_expense(client, rina, household, categories["Other"])
    path = f"{base(household)}/expenses/{expense['id']}"

    deleted = await client.delete(path, headers=rina.headers)
    again = await client.delete(path, headers=rina.headers)

    assert deleted.status_code == 204
    assert (again.status_code, error_code(again)) == (404, "expense_not_found")
    listed = await client.get(
        f"{base(household)}/expenses", params={"month": "2026-10"}, headers=rina.headers
    )
    assert listed.json()["items"] == []


@pytest.mark.parametrize("method", ["patch", "delete"])
@pytest.mark.parametrize("expense_id", ["not-a-uuid", "unknown", "other-household"])
async def test_unknown_expense(client: AsyncClient, method: str, expense_id: str) -> None:
    rina, household, _ = await setup(client)
    budi = await register(client, "Budi")
    other = await create_household(client, budi)
    if expense_id == "unknown":
        expense_id = str(uuid.uuid4())
    elif expense_id == "other-household":
        foreign = (await category_ids(client, budi, other))["Other"]
        expense_id = (await add_expense(client, budi, other, foreign))["id"]
    path = f"{base(household)}/expenses/{expense_id}"

    if method == "patch":
        response = await client.patch(path, json={"note": "x"}, headers=rina.headers)
    else:
        response = await client.delete(path, headers=rina.headers)

    assert response.status_code == 404
    assert error_code(response) == "expense_not_found"
    listed = await client.get(
        f"{base(other)}/expenses", params={"month": "2026-10"}, headers=budi.headers
    )
    assert all(e["note"] is None for e in listed.json()["items"])

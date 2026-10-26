from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from lumior.core.money import (
    Money,
    MoneySchema,
    UnknownCurrencyError,
    currency_precision,
    round_half_up,
)


@pytest.mark.parametrize(
    ("value", "places", "expected"),
    [
        ("2.345", 2, "2.35"),
        ("2.344", 2, "2.34"),
        ("2.5", 0, "3"),
        ("-2.5", 0, "-3"),
        ("0.125", 2, "0.13"),
        ("12500", 2, "12500.00"),
    ],
)
def test_round_half_up(value: str, places: int, expected: str) -> None:
    assert round_half_up(Decimal(value), places) == Decimal(expected)
    assert str(round_half_up(Decimal(value), places)) == expected


@pytest.mark.parametrize(("currency", "precision"), [("USD", 2), ("IDR", 2), ("JPY", 0)])
def test_currency_precision(currency: str, precision: int) -> None:
    assert currency_precision(currency) == precision


def test_unknown_currency() -> None:
    with pytest.raises(UnknownCurrencyError):
        currency_precision("XXX")


def test_money_of_rounds_to_currency_precision() -> None:
    assert Money.of("10.005", "USD") == Money(Decimal("10.01"), "USD")
    assert Money.of("199.5", "JPY") == Money(Decimal("200"), "JPY")


def test_money_rejects_floats() -> None:
    with pytest.raises(TypeError):
        Money.of(1.1, "USD")  # type: ignore[arg-type]


def test_amount_serialized_as_decimal_string() -> None:
    schema = MoneySchema.from_money(Money.of(12500, "IDR"))

    assert schema.model_dump(mode="json") == {"amount": "12500.00", "currency": "IDR"}
    assert schema.model_dump_json() == '{"amount":"12500.00","currency":"IDR"}'


def test_amount_parsed_from_string() -> None:
    schema = MoneySchema.model_validate_json('{"amount": "19.999", "currency": "USD"}')

    assert schema.amount == Decimal("20.00")
    assert schema.to_money() == Money(Decimal("20.00"), "USD")


@pytest.mark.parametrize("amount", ["12500", "12500.5", "true", '"1e5"', '"abc"', '""', "null"])
def test_non_decimal_string_amounts_rejected(amount: str) -> None:
    with pytest.raises(PydanticValidationError):
        MoneySchema.model_validate_json(f'{{"amount": {amount}, "currency": "USD"}}')


def test_unknown_currency_rejected_by_schema() -> None:
    with pytest.raises(PydanticValidationError):
        MoneySchema.model_validate_json('{"amount": "1.00", "currency": "XXX"}')


def test_json_schema_declares_string_amount() -> None:
    schema = MoneySchema.model_json_schema()

    assert schema["properties"]["amount"]["type"] == "string"


class Payment(BaseModel):
    total: MoneySchema


router = APIRouter(prefix="/api/v1/_test")


@router.post("/payments")
async def echo_payment(payment: Payment) -> Payment:
    return payment


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_api_returns_amount_as_string(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/_test/payments", json={"total": {"amount": "12500", "currency": "IDR"}}
    )

    assert response.status_code == 200
    assert response.json() == {"total": {"amount": "12500.00", "currency": "IDR"}}


async def test_api_rejects_amount_sent_as_number(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/_test/payments", json={"total": {"amount": 12500, "currency": "IDR"}}
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["location"] == ["body", "total", "amount"]

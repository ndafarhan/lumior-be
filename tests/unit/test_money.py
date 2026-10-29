from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from lumior.core.money import (
    Money,
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
    assert Money.of("10.005", "USD").amount == Decimal("10.01")
    assert Money.of("199.5", "JPY").amount == Decimal("200")


def test_money_of_allows_server_values_that_requests_may_not_send() -> None:
    assert Money.of(0, "IDR").model_dump(mode="json") == {"amount": "0.00", "currency": "IDR"}
    assert Money.of("-5", "USD").amount == Decimal("-5.00")


def test_money_rejects_floats() -> None:
    with pytest.raises(TypeError):
        Money.of(1.1, "USD")  # type: ignore[arg-type]


def test_amount_serialized_as_decimal_string() -> None:
    money = Money.of(12500, "IDR")

    assert money.model_dump(mode="json") == {"currency": "IDR", "amount": "12500.00"}
    assert money.model_dump_json() == '{"currency":"IDR","amount":"12500.00"}'


def test_parsed_amount_is_written_with_the_currency_decimals() -> None:
    money = Money.model_validate_json('{"amount": "19.9", "currency": "USD"}')

    assert money == Money.of("19.90", "USD")
    assert money.model_dump(mode="json")["amount"] == "19.90"


@pytest.mark.parametrize("amount", ["12500", "12500.5", "true", '"1e5"', '"abc"', '""', "null"])
def test_non_decimal_string_amounts_rejected(amount: str) -> None:
    with pytest.raises(PydanticValidationError):
        Money.model_validate_json(f'{{"amount": {amount}, "currency": "USD"}}')


def test_json_schema_declares_string_amount() -> None:
    schema = Money.model_json_schema()

    assert schema["properties"]["amount"]["type"] == "string"


def money_errors(body: str) -> list[tuple[object, ...]]:
    with pytest.raises(PydanticValidationError) as excinfo:
        Money.model_validate_json(body)
    return [error["loc"] for error in excinfo.value.errors()]


@pytest.mark.parametrize(
    ("amount", "currency"),
    [("0", "IDR"), ("-1", "IDR"), ("10.005", "IDR"), ("10.5", "JPY"), ("1000000000000", "IDR")],
)
def test_request_amounts_rejected_instead_of_rounded(amount: str, currency: str) -> None:
    body = f'{{"amount": "{amount}", "currency": "{currency}"}}'

    assert money_errors(body) == [("amount",)]


def test_unknown_currency_reports_only_currency() -> None:
    assert money_errors('{"amount": "10.005", "currency": "XXX"}') == [("currency",)]


@pytest.mark.parametrize(
    ("amount", "currency"), [("999999999999.99", "IDR"), ("0.01", "USD"), ("1200", "JPY")]
)
def test_request_amounts_at_the_limits(amount: str, currency: str) -> None:
    money = Money.model_validate_json(f'{{"amount": "{amount}", "currency": "{currency}"}}')

    assert money == Money.of(amount, currency)


@pytest.mark.parametrize(
    ("stored", "currency", "expected"),
    [("1200.00", "JPY", "1200"), ("45000", "IDR", "45000.00"), ("0", "IDR", "0.00")],
)
def test_output_has_exactly_the_currency_decimals(
    stored: str, currency: str, expected: str
) -> None:
    money = Money.of(Decimal(stored), currency)

    assert money.model_dump(mode="json") == {"amount": expected, "currency": currency}


class Payment(BaseModel):
    total: Money


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

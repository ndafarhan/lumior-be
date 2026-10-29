"""Money primitives: Decimal amounts, ISO 4217 currencies, half-up rounding, string JSON."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    PlainSerializer,
    ValidationInfo,
    WithJsonSchema,
    field_validator,
)

# ISO 4217 minor units. Extend as markets are added; storage is NUMERIC(14,2), so
# currencies with more than 2 minor units need a storage change first.
CURRENCY_PRECISION: dict[str, int] = {
    "AUD": 2,
    "CNY": 2,
    "EUR": 2,
    "GBP": 2,
    "IDR": 2,
    "INR": 2,
    "JPY": 0,
    "KRW": 0,
    "MYR": 2,
    "PHP": 2,
    "SGD": 2,
    "THB": 2,
    "USD": 2,
    "VND": 0,
}

AMOUNT_PRECISION = 14
AMOUNT_SCALE = 2

_DECIMAL_STRING = re.compile(r"^-?\d+(\.\d+)?$")


class UnknownCurrencyError(ValueError):
    pass


def currency_precision(currency: str) -> int:
    try:
        return CURRENCY_PRECISION[currency]
    except KeyError:
        raise UnknownCurrencyError(f"unsupported currency: {currency!r}") from None


def round_half_up(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _parse_amount(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str) and _DECIMAL_STRING.fullmatch(value.strip()):
        try:
            return Decimal(value.strip())
        except InvalidOperation:
            pass
    raise ValueError("amount must be a decimal string such as '12500.00'")


def _check_currency(value: str) -> str:
    currency_precision(value)
    return value


DecimalString = Annotated[
    Decimal,
    BeforeValidator(_parse_amount),
    PlainSerializer(lambda value: format(value, "f"), return_type=str),
    WithJsonSchema(
        {"type": "string", "pattern": _DECIMAL_STRING.pattern, "examples": ["12500.00"]}
    ),
]
"""A Decimal that is read from and written to JSON as a string, never a number."""

CurrencyCode = Annotated[
    str,
    AfterValidator(_check_currency),
    WithJsonSchema({"type": "string", "pattern": "^[A-Z]{3}$", "examples": ["IDR"]}),
]


MAX_INTEGER_DIGITS = AMOUNT_PRECISION - AMOUNT_SCALE


class Money(BaseModel):
    """A monetary amount, in JSON `{"amount": "12500.00", "currency": "IDR"}`.

    Parsed from a request, the amount must be greater than 0, fit storage (at most
    `MAX_INTEGER_DIGITS` digits before the point), and have at most the currency's decimal
    places: extra decimals are rejected, not rounded. Values the server computes, such as a
    zero total, are built with `Money.of`, which rounds and skips those request rules.
    """

    model_config = ConfigDict(frozen=True)

    # `currency` is validated first so the `amount` check can read its precision.
    currency: CurrencyCode
    amount: DecimalString

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be greater than 0")
        if value >= Decimal(10) ** MAX_INTEGER_DIGITS:
            raise ValueError(
                f"amount must have at most {MAX_INTEGER_DIGITS} digits before the point"
            )
        currency = info.data.get("currency")
        if currency is not None:
            places = currency_precision(currency)
            normalized = round_half_up(value, places)
            if normalized != value:
                raise ValueError(f"amount must have at most {places} decimal places for {currency}")
            # Same value, written with exactly the currency's decimals ("12500" -> "12500.00").
            return normalized
        return value

    @classmethod
    def of(cls, amount: Decimal | str | int, currency: str) -> "Money":
        """Build a Money rounded half-up to the currency's precision."""
        if isinstance(amount, float):
            raise TypeError("floats are not accepted for money; use Decimal or str")
        precision = currency_precision(currency)
        return cls.model_construct(
            currency=currency, amount=round_half_up(Decimal(amount), precision)
        )

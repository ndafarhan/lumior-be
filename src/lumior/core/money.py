"""Money primitives: Decimal amounts, ISO 4217 currencies, half-up rounding, string JSON."""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated, Any, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    PlainSerializer,
    WithJsonSchema,
    model_validator,
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


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    @classmethod
    def of(cls, amount: Decimal | str | int, currency: str) -> Self:
        """Build a Money rounded half-up to the currency's precision."""
        if isinstance(amount, float):
            raise TypeError("floats are not accepted for money; use Decimal or str")
        precision = currency_precision(currency)
        return cls(round_half_up(Decimal(amount), precision), currency)


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


class MoneySchema(BaseModel):
    """API representation of a monetary amount: `{"amount": "12500.00", "currency": "IDR"}`."""

    amount: DecimalString
    currency: CurrencyCode

    @model_validator(mode="after")
    def _round_to_currency(self) -> Self:
        self.amount = round_half_up(self.amount, currency_precision(self.currency))
        return self

    @classmethod
    def from_money(cls, money: Money) -> Self:
        return cls(amount=money.amount, currency=money.currency)

    def to_money(self) -> Money:
        return Money.of(self.amount, self.currency)

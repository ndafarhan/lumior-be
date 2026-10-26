from decimal import Decimal

import pytest

from lumior.core.units import (
    BaseUnit,
    Dimension,
    IncompatibleUnitsError,
    Quantity,
    UnknownUnitError,
    convert,
    dimension_of,
    to_base,
)


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        ("1.5", "kg", Quantity(Decimal("1500"), BaseUnit.GRAM)),
        ("250", "g", Quantity(Decimal("250"), BaseUnit.GRAM)),
        ("500", "mg", Quantity(Decimal("0.5"), BaseUnit.GRAM)),
        ("1", "lb", Quantity(Decimal("453.59237"), BaseUnit.GRAM)),
        ("1", "oz", Quantity(Decimal("28.349523125"), BaseUnit.GRAM)),
        ("2", "l", Quantity(Decimal("2000"), BaseUnit.MILLILITER)),
        ("330", "ml", Quantity(Decimal("330"), BaseUnit.MILLILITER)),
        ("75", "cl", Quantity(Decimal("750"), BaseUnit.MILLILITER)),
        ("5", "dl", Quantity(Decimal("500"), BaseUnit.MILLILITER)),
        ("6", "piece", Quantity(Decimal("6"), BaseUnit.PIECE)),
        ("3", "pair", Quantity(Decimal("6"), BaseUnit.PIECE)),
        ("1", "dozen", Quantity(Decimal("12"), BaseUnit.PIECE)),
    ],
)
def test_to_base(value: str, unit: str, expected: Quantity) -> None:
    assert to_base(Decimal(value), unit) == expected


def test_convert_within_dimension() -> None:
    assert convert(Decimal("1500"), "g", "kg") == Decimal("1.5")
    assert convert(Decimal("1"), "l", "cl") == Decimal("100")
    assert convert(Decimal("24"), "piece", "dozen") == Decimal("2")


@pytest.mark.parametrize(("from_unit", "to_unit"), [("kg", "l"), ("ml", "g"), ("piece", "kg")])
def test_cross_dimension_conversion_rejected(from_unit: str, to_unit: str) -> None:
    with pytest.raises(IncompatibleUnitsError):
        convert(Decimal(1), from_unit, to_unit)


def test_unknown_unit_rejected() -> None:
    with pytest.raises(UnknownUnitError):
        to_base(Decimal(1), "bushel")


def test_dimension_of() -> None:
    assert dimension_of("kg") is Dimension.MASS
    assert dimension_of("l") is Dimension.VOLUME
    assert dimension_of("dozen") is Dimension.COUNT

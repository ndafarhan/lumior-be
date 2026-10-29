"""Quantity units: three base units and conversions into them."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Dimension(StrEnum):
    MASS = "mass"
    VOLUME = "volume"
    COUNT = "count"


class BaseUnit(StrEnum):
    GRAM = "g"
    MILLILITER = "ml"
    PIECE = "piece"


BASE_UNIT_BY_DIMENSION: dict[Dimension, BaseUnit] = {
    Dimension.MASS: BaseUnit.GRAM,
    Dimension.VOLUME: BaseUnit.MILLILITER,
    Dimension.COUNT: BaseUnit.PIECE,
}

# unit -> (dimension, how many base units one of it equals)
UNITS: dict[str, tuple[Dimension, Decimal]] = {
    "mg": (Dimension.MASS, Decimal("0.001")),
    "g": (Dimension.MASS, Decimal(1)),
    "kg": (Dimension.MASS, Decimal(1000)),
    "oz": (Dimension.MASS, Decimal("28.349523125")),
    "lb": (Dimension.MASS, Decimal("453.59237")),
    "ml": (Dimension.VOLUME, Decimal(1)),
    "cl": (Dimension.VOLUME, Decimal(10)),
    "dl": (Dimension.VOLUME, Decimal(100)),
    "l": (Dimension.VOLUME, Decimal(1000)),
    "piece": (Dimension.COUNT, Decimal(1)),
    "pair": (Dimension.COUNT, Decimal(2)),
    "dozen": (Dimension.COUNT, Decimal(12)),
}


class UnknownUnitError(ValueError):
    pass


class IncompatibleUnitsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal
    unit: BaseUnit


def _lookup(unit: str) -> tuple[Dimension, Decimal]:
    try:
        return UNITS[unit]
    except KeyError:
        raise UnknownUnitError(f"unknown unit: {unit!r}") from None


def dimension_of(unit: str) -> Dimension:
    return _lookup(unit)[0]


def to_base(value: Decimal, unit: str) -> Quantity:
    dimension, factor = _lookup(unit)
    return Quantity(value * factor, BASE_UNIT_BY_DIMENSION[dimension])


def convert(value: Decimal, from_unit: str, to_unit: str) -> Decimal:
    from_dimension, from_factor = _lookup(from_unit)
    to_dimension, to_factor = _lookup(to_unit)
    if from_dimension != to_dimension:
        raise IncompatibleUnitsError(
            f"cannot convert {from_unit!r} ({from_dimension}) to {to_unit!r} ({to_dimension})"
        )
    return value * from_factor / to_factor

from datetime import date

import pytest
from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from lumior.core.validation import Month, month_range

month_adapter: TypeAdapter[str] = TypeAdapter(Month)


@pytest.mark.parametrize(
    ("month", "start", "end"),
    [
        ("2026-10", date(2026, 10, 1), date(2026, 11, 1)),
        ("2026-12", date(2026, 12, 1), date(2027, 1, 1)),
        ("2000-01", date(2000, 1, 1), date(2000, 2, 1)),
    ],
)
def test_month_range(month: str, start: date, end: date) -> None:
    assert month_range(month_adapter.validate_python(month)) == (start, end)


@pytest.mark.parametrize("month", ["2026-13", "2026-00", "2026-1", "26-10", "2026-10-01", ""])
def test_invalid_months_rejected(month: str) -> None:
    with pytest.raises(PydanticValidationError):
        month_adapter.validate_python(month)

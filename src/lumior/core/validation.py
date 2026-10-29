"""Field types shared by request schemas, matching the limits the frontend enforces."""

from datetime import date
from typing import Annotated

from pydantic import StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
"""A display name: 1-100 characters after trimming, stored trimmed."""

Month = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
"""A calendar month as `YYYY-MM`, month 01-12."""


def month_range(month: str) -> tuple[date, date]:
    """The half-open range `[first day, first day of the next month)` of a `Month`."""
    year, number = (int(part) for part in month.split("-"))
    start = date(year, number, 1)
    end = date(year + 1, 1, 1) if number == 12 else date(year, number + 1, 1)
    return start, end

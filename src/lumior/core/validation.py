"""Field types shared by request schemas, matching the limits the frontend enforces."""

from typing import Annotated

from pydantic import StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
"""A display name: 1-100 characters after trimming, stored trimmed."""

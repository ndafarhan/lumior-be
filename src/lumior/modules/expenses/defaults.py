"""The categories every household starts with.

Kept apart from the expenses service so households can call it without an import cycle."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from lumior.modules.expenses.models import ExpenseCategory

DEFAULT_CATEGORY_NAMES = (
    "Groceries",
    "Dining out",
    "Transport",
    "Utilities",
    "Housing",
    "Health",
    "Education",
    "Entertainment",
    "Other",
)


async def add_default_categories(
    session: AsyncSession, household_id: uuid.UUID, *, now: datetime
) -> None:
    session.add_all(
        ExpenseCategory(id=uuid.uuid4(), household_id=household_id, name=name, created_at=now)
        for name in DEFAULT_CATEGORY_NAMES
    )
    await session.flush()

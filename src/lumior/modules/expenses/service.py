"""Expense categories, expenses, and the monthly summary, all scoped to one household."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from lumior.core.errors import (
    CategoryArchivedError,
    CategoryNameTakenError,
    CategoryNotFoundError,
    CategoryNotFoundInBodyError,
    CurrencyMismatchError,
    ExpenseNotFoundError,
    ValidationError,
    field_detail,
)
from lumior.core.money import Money
from lumior.core.validation import month_range
from lumior.modules.expenses.cursor import (
    Cursor,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from lumior.modules.expenses.models import Expense, ExpenseCategory
from lumior.modules.expenses.repository import (
    CategoryRepository,
    CategoryTotal,
    ExpenseRepository,
)
from lumior.modules.households.service import HouseholdAccessContext

EARLIEST_SPENT_ON = date(2000, 1, 1)
# The user's local "today" may be a day ahead of the server's UTC date.
LATEST_SPENT_ON_AFTER_TODAY = timedelta(days=1)


@dataclass(frozen=True)
class ExpenseChanges:
    """Fields to write. `None` means "not sent", except `note` when `note_sent` is true."""

    amount: Money | None = None
    spent_on: date | None = None
    category_id: uuid.UUID | None = None
    note: str | None = None
    note_sent: bool = False


@dataclass(frozen=True)
class ExpenseListPage:
    items: list[Expense]
    next_cursor: str | None


@dataclass(frozen=True)
class MonthSummary:
    total: Decimal
    categories: list[CategoryTotal]


def parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


class ExpenseService:
    def __init__(self, session: AsyncSession) -> None:
        self.categories = CategoryRepository(session)
        self.expenses = ExpenseRepository(session)

    async def list_categories(self, access: HouseholdAccessContext) -> list[ExpenseCategory]:
        return await self.categories.list(access.household.id)

    async def create_category(
        self, access: HouseholdAccessContext, name: str, *, now: datetime
    ) -> ExpenseCategory:
        household_id = access.household.id
        if await self.categories.name_taken(household_id, name):
            raise CategoryNameTakenError()
        category = ExpenseCategory(
            id=uuid.uuid4(), household_id=household_id, name=name, archived=False, created_at=now
        )
        await self.categories.save(category)
        return category

    async def update_category(
        self,
        access: HouseholdAccessContext,
        category_id: str,
        *,
        name: str | None,
        archived: bool | None,
    ) -> ExpenseCategory:
        """Apply the given fields; `None` leaves a field unchanged."""
        category = await self._category(access, category_id)
        if name is not None:
            if await self.categories.name_taken(category.household_id, name, except_id=category.id):
                raise CategoryNameTakenError()
            category.name = name
        if archived is not None:
            category.archived = archived
        await self.categories.save(category)
        return category

    async def _category(self, access: HouseholdAccessContext, category_id: str) -> ExpenseCategory:
        """404 `category_not_found` for an unknown, malformed, or other household's id."""
        parsed = parse_uuid(category_id)
        category = await self.categories.get(access.household.id, parsed) if parsed else None
        if category is None:
            raise CategoryNotFoundError()
        return category

    async def create_expense(
        self,
        access: HouseholdAccessContext,
        *,
        amount: Money,
        spent_on: date,
        category_id: uuid.UUID,
        note: str | None,
        now: datetime,
    ) -> Expense:
        await self._check(access, ExpenseChanges(amount, spent_on, category_id), None, now=now)
        expense = Expense(
            id=uuid.uuid4(),
            household_id=access.household.id,
            category_id=category_id,
            amount=amount.amount,
            spent_on=spent_on,
            note=note,
            created_at=now,
            updated_at=now,
        )
        await self.expenses.add(expense)
        return expense

    async def update_expense(
        self,
        access: HouseholdAccessContext,
        expense_id: str,
        changes: ExpenseChanges,
        *,
        now: datetime,
    ) -> Expense:
        expense = await self._expense(access, expense_id)
        await self._check(access, changes, expense, now=now)
        if changes.amount is not None:
            expense.amount = changes.amount.amount
        if changes.spent_on is not None:
            expense.spent_on = changes.spent_on
        if changes.category_id is not None:
            expense.category_id = changes.category_id
        if changes.note_sent:
            expense.note = changes.note
        expense.updated_at = now
        await self.expenses.flush()
        return expense

    async def delete_expense(self, access: HouseholdAccessContext, expense_id: str) -> None:
        await self.expenses.delete(await self._expense(access, expense_id))

    async def list_expenses(
        self,
        access: HouseholdAccessContext,
        month: str,
        *,
        category_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> ExpenseListPage:
        after = None
        if cursor is not None:
            try:
                after = decode_cursor(cursor)
            except InvalidCursorError:
                raise ValidationError(
                    details=[field_detail(["query", "cursor"], "invalid cursor", "invalid_cursor")]
                ) from None
        category: uuid.UUID | None = None
        if category_id is not None:
            category = parse_uuid(category_id)
            # Not one of the household's categories: an empty page, not an error.
            if category is None or await self.categories.get(access.household.id, category) is None:
                return ExpenseListPage(items=[], next_cursor=None)
        start, end = month_range(month)
        # One extra row tells whether another page follows.
        rows = await self.expenses.list_month(
            access.household.id, start, end, category_id=category, after=after, limit=limit + 1
        )
        items = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = encode_cursor(Cursor(last.spent_on, last.created_at, last.id))
        return ExpenseListPage(items=items, next_cursor=next_cursor)

    async def summarize(self, access: HouseholdAccessContext, month: str) -> MonthSummary:
        start, end = month_range(month)
        categories = await self.expenses.totals_by_category(access.household.id, start, end)
        return MonthSummary(
            total=sum((c.total for c in categories), Decimal(0)), categories=categories
        )

    async def _check(
        self,
        access: HouseholdAccessContext,
        changes: ExpenseChanges,
        current: Expense | None,
        *,
        now: datetime,
    ) -> None:
        """The rules that need the household, the clock, or the database, in a fixed order;
        the first failure is reported. `current` is the expense being updated, if any."""
        if changes.amount is not None and changes.amount.currency != access.household.currency:
            raise CurrencyMismatchError()
        if changes.spent_on is not None:
            latest = now.date() + LATEST_SPENT_ON_AFTER_TODAY
            if not EARLIEST_SPENT_ON <= changes.spent_on <= latest:
                raise ValidationError(
                    details=[
                        field_detail(
                            ["body", "spent_on"],
                            f"spent_on must be between {EARLIEST_SPENT_ON} and {latest}",
                            "date_out_of_range",
                        )
                    ]
                )
        if changes.category_id is not None:
            category = await self.categories.get(access.household.id, changes.category_id)
            if category is None:
                raise CategoryNotFoundInBodyError()
            # An expense may keep a category that was archived after it was recorded.
            changing = current is None or current.category_id != category.id
            if category.archived and changing:
                raise CategoryArchivedError()

    async def _expense(self, access: HouseholdAccessContext, expense_id: str) -> Expense:
        """404 `expense_not_found` for an unknown, malformed, or other household's id."""
        parsed = parse_uuid(expense_id)
        expense = await self.expenses.get(access.household.id, parsed) if parsed else None
        if expense is None:
            raise ExpenseNotFoundError()
        return expense

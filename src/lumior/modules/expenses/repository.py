import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lumior.core.errors import CategoryNameTakenError
from lumior.modules.expenses.cursor import Cursor
from lumior.modules.expenses.models import Expense, ExpenseCategory


@dataclass(frozen=True)
class CategoryTotal:
    category_id: uuid.UUID
    total: Decimal
    count: int


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, household_id: uuid.UUID) -> list[ExpenseCategory]:
        result = await self.session.scalars(
            select(ExpenseCategory)
            .where(ExpenseCategory.household_id == household_id)
            .order_by(func.lower(ExpenseCategory.name), ExpenseCategory.id)
        )
        return list(result)

    async def get(self, household_id: uuid.UUID, category_id: uuid.UUID) -> ExpenseCategory | None:
        category = await self.session.get(ExpenseCategory, category_id)
        if category is None or category.household_id != household_id:
            return None
        return category

    async def name_taken(
        self, household_id: uuid.UUID, name: str, *, except_id: uuid.UUID | None = None
    ) -> bool:
        query = select(ExpenseCategory.id).where(
            ExpenseCategory.household_id == household_id,
            func.lower(ExpenseCategory.name) == name.lower(),
        )
        if except_id is not None:
            query = query.where(ExpenseCategory.id != except_id)
        return (await self.session.scalar(query.limit(1))) is not None

    async def save(self, category: ExpenseCategory) -> None:
        """Insert or update `category`; raises `CategoryNameTakenError` if a concurrent
        write took the name first."""
        try:
            # A savepoint keeps the outer transaction usable if the write fails.
            async with self.session.begin_nested():
                self.session.add(category)
        except IntegrityError as exc:
            raise CategoryNameTakenError() from exc


class ExpenseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, household_id: uuid.UUID, expense_id: uuid.UUID) -> Expense | None:
        expense = await self.session.get(Expense, expense_id)
        if expense is None or expense.household_id != household_id:
            return None
        return expense

    async def add(self, expense: Expense) -> None:
        self.session.add(expense)
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def delete(self, expense: Expense) -> None:
        await self.session.delete(expense)
        await self.session.flush()

    async def list_month(
        self,
        household_id: uuid.UUID,
        start: date,
        end: date,
        *,
        category_id: uuid.UUID | None,
        after: Cursor | None,
        limit: int,
    ) -> list[Expense]:
        """Up to `limit` expenses with `start <= spent_on < end`, newest first, after `after`."""
        query = select(Expense).where(
            Expense.household_id == household_id,
            Expense.spent_on >= start,
            Expense.spent_on < end,
        )
        if category_id is not None:
            query = query.where(Expense.category_id == category_id)
        if after is not None:
            query = query.where(
                tuple_(Expense.spent_on, Expense.created_at, Expense.id)
                < tuple_(after.spent_on, after.created_at, after.id)
            )
        query = query.order_by(
            Expense.spent_on.desc(), Expense.created_at.desc(), Expense.id.desc()
        ).limit(limit)
        return list(await self.session.scalars(query))

    async def totals_by_category(
        self, household_id: uuid.UUID, start: date, end: date
    ) -> list[CategoryTotal]:
        """Per-category sums for `start <= spent_on < end`, largest first."""
        total = func.sum(Expense.amount)
        rows = await self.session.execute(
            select(Expense.category_id, total, func.count())
            .where(
                Expense.household_id == household_id,
                Expense.spent_on >= start,
                Expense.spent_on < end,
            )
            .group_by(Expense.category_id)
            .order_by(total.desc(), Expense.category_id)
        )
        return [CategoryTotal(*row) for row in rows]

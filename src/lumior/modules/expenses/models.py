import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from lumior.core.db import Base
from lumior.core.money import AMOUNT_PRECISION, AMOUNT_SCALE

CATEGORY_NAME_MAX_LENGTH = 50
NOTE_MAX_LENGTH = 500


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    __table_args__ = (
        # Case-insensitive and including archived categories.
        Index(
            "uq_expense_categories_household_id_lower_name",
            "household_id",
            text("lower(name)"),
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(CATEGORY_NAME_MAX_LENGTH))
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        # Serves the month list and its cursor seek (scanned backward for the descending order).
        Index(
            "ix_expenses_household_id_spent_on",
            "household_id",
            "spent_on",
            "created_at",
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"))
    # Categories are never deleted, only archived.
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("expense_categories.id", ondelete="RESTRICT"), index=True
    )
    # In the household's currency, which cannot change, so it is not stored per row.
    amount: Mapped[Decimal] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE))
    spent_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(NOTE_MAX_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

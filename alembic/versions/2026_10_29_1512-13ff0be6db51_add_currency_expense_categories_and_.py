"""add currency, expense categories and expenses

Revision ID: 13ff0be6db51
Revises: de50fb9d0bec
Create Date: 2026-10-29 15:12:14.275429

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# A copy of `lumior.modules.expenses.defaults.DEFAULT_CATEGORY_NAMES` at the time of this
# migration, so later edits to that list do not change what this revision seeds.
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

revision: str = "13ff0be6db51"
down_revision: str | Sequence[str] | None = "de50fb9d0bec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing households get IDR. The server default is only for this backfill.
    op.add_column(
        "households",
        sa.Column("currency", sa.String(length=3), server_default="IDR", nullable=False),
    )
    op.alter_column("households", "currency", server_default=None)
    op.create_table(
        "expense_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_expense_categories_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expense_categories")),
    )
    op.create_index(
        "uq_expense_categories_household_id_lower_name",
        "expense_categories",
        ["household_id", sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["expense_categories.id"],
            name=op.f("fk_expenses_category_id_expense_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_expenses_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expenses")),
    )
    op.create_index(op.f("ix_expenses_category_id"), "expenses", ["category_id"], unique=False)
    op.create_index(
        "ix_expenses_household_id_spent_on",
        "expenses",
        ["household_id", "spent_on", "created_at", "id"],
        unique=False,
    )
    op.execute(
        sa.text(
            "INSERT INTO expense_categories (id, household_id, name, archived, created_at) "
            "SELECT gen_random_uuid(), households.id, defaults.name, false, now() "
            "FROM households CROSS JOIN unnest(CAST(:names AS varchar[])) AS defaults(name)"
        ).bindparams(names=list(DEFAULT_CATEGORY_NAMES))
    )


def downgrade() -> None:
    op.drop_index(
        "ix_expenses_household_id_spent_on",
        table_name="expenses",
    )
    op.drop_index(op.f("ix_expenses_category_id"), table_name="expenses")
    op.drop_table("expenses")
    op.drop_index("uq_expense_categories_household_id_lower_name", table_name="expense_categories")
    op.drop_table("expense_categories")
    op.drop_column("households", "currency")

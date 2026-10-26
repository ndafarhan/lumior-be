"""baseline: enable pg_trgm

Revision ID: 8e37e267a13c
Revises:
Create Date: 2026-10-26 14:55:34.284079

"""

from collections.abc import Sequence

from alembic import op

revision: str = "8e37e267a13c"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")

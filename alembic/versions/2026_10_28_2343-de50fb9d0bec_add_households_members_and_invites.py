"""add households members and invites

Revision ID: de50fb9d0bec
Revises: 52d1cda47294
Create Date: 2026-10-28 23:43:27.036647

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "de50fb9d0bec"
down_revision: str | Sequence[str] | None = "52d1cda47294"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "households",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_households")),
    )
    op.create_table(
        "household_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_household_invites_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_household_invites_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["used_by"],
            ["users.id"],
            name=op.f("fk_household_invites_used_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_household_invites")),
        sa.UniqueConstraint("code", name=op.f("uq_household_invites_code")),
    )
    op.create_index(
        op.f("ix_household_invites_household_id"),
        "household_invites",
        ["household_id"],
        unique=False,
    )
    op.create_table(
        "household_members",
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'member')", name=op.f("ck_household_members_role")),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_household_members_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_household_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("household_id", "user_id", name=op.f("pk_household_members")),
    )
    op.create_index("ix_household_members_user_id", "household_members", ["user_id"], unique=False)
    op.create_index(
        "uq_household_members_one_owner",
        "household_members",
        ["household_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_household_members_one_owner",
        table_name="household_members",
        postgresql_where=sa.text("role = 'owner'"),
    )
    op.drop_index("ix_household_members_user_id", table_name="household_members")
    op.drop_table("household_members")
    op.drop_index(op.f("ix_household_invites_household_id"), table_name="household_invites")
    op.drop_table("household_invites")
    op.drop_table("households")

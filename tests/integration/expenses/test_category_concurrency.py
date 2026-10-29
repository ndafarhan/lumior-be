"""Two members create the same category name at once, on separate connections that commit."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from lumior.core.errors import CategoryNameTakenError
from lumior.modules.expenses.models import ExpenseCategory
from lumior.modules.expenses.service import ExpenseService
from lumior.modules.households.models import Household
from lumior.modules.households.service import HouseholdService
from lumior.modules.identity.models import User

NOW = datetime.now(UTC)


@pytest.fixture
async def committed_household(db_engine: AsyncEngine) -> AsyncIterator[tuple[User, uuid.UUID]]:
    """A committed owner and household. Deleting them cascades to the categories."""
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    owner = User(email=f"{uuid.uuid4()}@example.com", name="O", password_hash="x", created_at=NOW)
    async with sessions.begin() as session:
        session.add(owner)
        await session.flush()
        view = await HouseholdService(session, invite_ttl=timedelta(days=7)).create(
            owner.id, "Rumah", "IDR", now=NOW
        )
    yield owner, view.id
    async with sessions.begin() as session:
        await session.execute(delete(Household).where(Household.id == view.id))
        await session.execute(delete(User).where(User.id == owner.id))


async def test_concurrent_creates_admit_exactly_one(
    db_engine: AsyncEngine, committed_household: tuple[User, uuid.UUID]
) -> None:
    owner, household_id = committed_household
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)

    async def create(name: str, hold: float) -> str:
        session: AsyncSession
        async with sessions() as session:
            households = HouseholdService(session, invite_ttl=timedelta(days=7))
            access = await households.check_access(str(household_id), owner.id)
            try:
                await ExpenseService(session).create_category(access, name, now=NOW)
                # Keep the row uncommitted so the other request passes its pre-check.
                await asyncio.sleep(hold)
                await session.commit()
                return "created"
            except CategoryNameTakenError:
                await session.rollback()
                return "category_name_taken"

    results = await asyncio.gather(create("Pets", 0.3), create("PETS", 0))

    assert sorted(results) == ["category_name_taken", "created"]
    async with sessions() as session:
        count = await session.scalar(
            select(func.count()).where(
                ExpenseCategory.household_id == household_id,
                func.lower(ExpenseCategory.name) == "pets",
            )
        )
    assert count == 1

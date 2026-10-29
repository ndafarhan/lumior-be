"""Two users accept one invite at the same time, on separate connections that really commit."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from lumior.core.errors import InviteUsedError
from lumior.modules.households.models import Household, HouseholdMember
from lumior.modules.households.service import HouseholdService
from lumior.modules.identity.models import User

NOW = datetime.now(UTC)
TTL = timedelta(days=7)


@pytest.fixture
async def committed_users(db_engine: AsyncEngine) -> AsyncIterator[list[User]]:
    """Three committed users (owner first). Deleting them cascades to everything they own."""
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    users = [
        User(email=f"{uuid.uuid4()}@example.com", name=name, password_hash="x", created_at=NOW)
        for name in ("Owner", "A", "B")
    ]
    async with sessions.begin() as session:
        session.add_all(users)
    yield users
    async with sessions.begin() as session:
        household_ids = select(HouseholdMember.household_id).where(
            HouseholdMember.user_id == users[0].id
        )
        await session.execute(delete(Household).where(Household.id.in_(household_ids)))
        await session.execute(delete(User).where(User.id.in_([u.id for u in users])))


async def test_concurrent_accepts_admit_exactly_one(
    db_engine: AsyncEngine, committed_users: list[User]
) -> None:
    owner, first, second = committed_users
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        service = HouseholdService(session, invite_ttl=TTL)
        view = await service.create(owner.id, "Rumah", now=NOW)
        access = await service.check_access(str(view.id), owner.id)
        code = (await service.create_invite(access, now=NOW)).code

    async def accept(user: User) -> str:
        session: AsyncSession
        async with sessions() as session:
            try:
                await HouseholdService(session, invite_ttl=TTL).accept_invite(
                    code, user.id, now=NOW
                )
                # Hold the row lock briefly so the other request has to wait for it.
                await asyncio.sleep(0.2)
                await session.commit()
                return "joined"
            except InviteUsedError:
                await session.rollback()
                return "invite_used"

    results = await asyncio.gather(accept(first), accept(second))

    assert sorted(results) == ["invite_used", "joined"]
    async with sessions() as session:
        members = await session.scalar(
            select(func.count()).where(HouseholdMember.household_id == view.id)
        )
    assert members == 2

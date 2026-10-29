import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lumior.modules.households.models import Household, HouseholdMember, Role
from lumior.modules.identity.models import User

NOW = datetime(2026, 11, 1, tzinfo=UTC)


async def make_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", name="U", password_hash="x", created_at=NOW)
    session.add(user)
    await session.flush()
    return user


async def test_household_has_at_most_one_owner(db_session: AsyncSession) -> None:
    first, second = await make_user(db_session), await make_user(db_session)
    household = Household(name="Rumah", created_at=NOW)
    db_session.add(household)
    await db_session.flush()
    db_session.add(
        HouseholdMember(household_id=household.id, user_id=first.id, role=Role.OWNER, joined_at=NOW)
    )
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_household_members_one_owner"):
        async with db_session.begin_nested():
            db_session.add(
                HouseholdMember(
                    household_id=household.id, user_id=second.id, role=Role.OWNER, joined_at=NOW
                )
            )


async def test_role_is_owner_or_member(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    household = Household(name="Rumah", created_at=NOW)
    db_session.add(household)
    await db_session.flush()

    with pytest.raises(IntegrityError, match="ck_household_members_role"):
        async with db_session.begin_nested():
            db_session.add(
                HouseholdMember(
                    household_id=household.id, user_id=user.id, role="admin", joined_at=NOW
                )
            )

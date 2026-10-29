import uuid
from dataclasses import dataclass

from sqlalchemy import ScalarSelect, Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumior.modules.households.models import Household, HouseholdInvite, HouseholdMember
from lumior.modules.identity.models import User

# Member names and emails come from a read-only join on `users`, owned by the identity module.
# This avoids one service call per member; households never writes to `users`.


@dataclass(frozen=True)
class HouseholdView:
    id: uuid.UUID
    name: str
    role: str
    member_count: int
    currency: str


@dataclass(frozen=True)
class MemberView:
    user_id: uuid.UUID
    name: str
    email: str
    role: str


@dataclass(frozen=True)
class InvitePreview:
    invite: HouseholdInvite
    household_name: str
    invited_by: str


def _member_count() -> ScalarSelect[int]:
    return (
        select(func.count())
        .where(HouseholdMember.household_id == Household.id)
        .correlate(Household)
        .scalar_subquery()
    )


def _views_for(user_id: uuid.UUID) -> Select[uuid.UUID, str, str, int, str]:
    return (
        select(
            Household.id, Household.name, HouseholdMember.role, _member_count(), Household.currency
        )
        .join(HouseholdMember, HouseholdMember.household_id == Household.id)
        .where(HouseholdMember.user_id == user_id)
    )


class HouseholdRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, household_id: uuid.UUID) -> Household | None:
        return await self.session.get(Household, household_id)

    async def get_membership(
        self, household_id: uuid.UUID, user_id: uuid.UUID
    ) -> HouseholdMember | None:
        return await self.session.get(HouseholdMember, (household_id, user_id))

    async def list_views(self, user_id: uuid.UUID) -> list[HouseholdView]:
        query = _views_for(user_id).order_by(HouseholdMember.joined_at, Household.id)
        rows = await self.session.execute(query)
        return [HouseholdView(*row) for row in rows]

    async def get_view(self, household_id: uuid.UUID, user_id: uuid.UUID) -> HouseholdView:
        row = (
            await self.session.execute(_views_for(user_id).where(Household.id == household_id))
        ).one()
        return HouseholdView(*row)

    async def list_members(self, household_id: uuid.UUID) -> list[MemberView]:
        rows = await self.session.execute(
            select(User.id, User.name, User.email, HouseholdMember.role)
            .join(HouseholdMember, HouseholdMember.user_id == User.id)
            .where(HouseholdMember.household_id == household_id)
            .order_by(HouseholdMember.joined_at, User.id)
        )
        return [MemberView(*row) for row in rows]

    async def add(self, household: Household) -> None:
        self.session.add(household)
        await self.session.flush()

    async def add_member(self, member: HouseholdMember) -> None:
        self.session.add(member)
        await self.session.flush()

    async def remove_member(self, household_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(HouseholdMember).where(
                HouseholdMember.household_id == household_id, HouseholdMember.user_id == user_id
            )
        )


class InviteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, invite: HouseholdInvite) -> None:
        self.session.add(invite)
        await self.session.flush()

    async def get_by_code(self, code: str, *, for_update: bool = False) -> HouseholdInvite | None:
        query = select(HouseholdInvite).where(HouseholdInvite.code == code)
        if for_update:
            # Concurrent accepts of one invite run in turn; the second sees it used.
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_preview(self, invite: HouseholdInvite) -> InvitePreview:
        household_name, invited_by = (
            await self.session.execute(
                select(Household.name, User.name)
                .select_from(HouseholdInvite)
                .join(Household, Household.id == HouseholdInvite.household_id)
                .join(User, User.id == HouseholdInvite.created_by)
                .where(HouseholdInvite.id == invite.id)
            )
        ).one()
        return InvitePreview(invite=invite, household_name=household_name, invited_by=invited_by)

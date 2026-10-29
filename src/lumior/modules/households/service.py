"""Households, membership, and invites, including the access rules for household routes."""

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from lumior.core.errors import (
    AlreadyMemberError,
    HouseholdNotFoundError,
    InviteExpiredError,
    InviteNotFoundError,
    InviteUsedError,
    MemberNotFoundError,
    NotAMemberError,
    OwnerCannotLeaveError,
    OwnerRequiredError,
)
from lumior.modules.expenses.defaults import add_default_categories
from lumior.modules.households.models import (
    Household,
    HouseholdInvite,
    HouseholdMember,
    Role,
)
from lumior.modules.households.repository import (
    HouseholdRepository,
    HouseholdView,
    InvitePreview,
    InviteRepository,
    MemberView,
)


@dataclass(frozen=True)
class HouseholdAccessContext:
    """The household of a `/households/{household_id}/...` request and the caller's membership."""

    household: Household
    membership: HouseholdMember

    @property
    def is_owner(self) -> bool:
        return self.membership.role == Role.OWNER

    def require_owner(self) -> None:
        if not self.is_owner:
            raise OwnerRequiredError()


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


class HouseholdService:
    def __init__(self, session: AsyncSession, *, invite_ttl: timedelta) -> None:
        self.session = session
        self.households = HouseholdRepository(session)
        self.invites = InviteRepository(session)
        self.invite_ttl = invite_ttl

    async def check_access(self, household_id: str, user_id: uuid.UUID) -> HouseholdAccessContext:
        """404 `household_not_found` for an unknown (or malformed) id, then 403 `not_a_member`."""
        parsed = _parse_uuid(household_id)
        household = await self.households.get(parsed) if parsed else None
        if household is None:
            raise HouseholdNotFoundError()
        membership = await self.households.get_membership(household.id, user_id)
        if membership is None:
            raise NotAMemberError()
        return HouseholdAccessContext(household=household, membership=membership)

    async def list_for_user(self, user_id: uuid.UUID) -> list[HouseholdView]:
        return await self.households.list_views(user_id)

    async def create(
        self, user_id: uuid.UUID, name: str, currency: str, *, now: datetime
    ) -> HouseholdView:
        household = Household(id=uuid.uuid4(), name=name, currency=currency, created_at=now)
        await self.households.add(household)
        await add_default_categories(self.session, household.id, now=now)
        await self.households.add_member(
            HouseholdMember(
                household_id=household.id, user_id=user_id, role=Role.OWNER, joined_at=now
            )
        )
        return await self.households.get_view(household.id, user_id)

    async def rename(self, access: HouseholdAccessContext, name: str) -> HouseholdView:
        access.require_owner()
        access.household.name = name
        return await self.households.get_view(access.household.id, access.membership.user_id)

    async def list_members(self, access: HouseholdAccessContext) -> list[MemberView]:
        return await self.households.list_members(access.household.id)

    async def remove_member(self, access: HouseholdAccessContext, target_user_id: str) -> None:
        """Leave (target is the caller) or, for the owner, remove another member."""
        household_id = access.household.id
        caller_id = access.membership.user_id
        target_id = _parse_uuid(target_user_id)
        if target_id == caller_id:
            if access.is_owner:
                raise OwnerCannotLeaveError()
            await self.households.remove_member(household_id, caller_id)
            return
        access.require_owner()
        if (
            target_id is None
            or await self.households.get_membership(household_id, target_id) is None
        ):
            raise MemberNotFoundError()
        # The caller is the only owner, so the target here is always a plain member.
        await self.households.remove_member(household_id, target_id)

    async def create_invite(
        self, access: HouseholdAccessContext, *, now: datetime
    ) -> HouseholdInvite:
        access.require_owner()
        invite = HouseholdInvite(
            id=uuid.uuid4(),
            household_id=access.household.id,
            code=secrets.token_urlsafe(16),
            created_by=access.membership.user_id,
            created_at=now,
            expires_at=(now + self.invite_ttl).replace(microsecond=0),
        )
        await self.invites.add(invite)
        return invite

    async def preview_invite(
        self, code: str, user_id: uuid.UUID, *, now: datetime
    ) -> tuple[InvitePreview, bool]:
        """Return the preview and whether the caller is already a member."""
        invite = await self._usable_invite(code, now=now, for_update=False)
        membership = await self.households.get_membership(invite.household_id, user_id)
        return await self.invites.get_preview(invite), membership is not None

    async def accept_invite(self, code: str, user_id: uuid.UUID, *, now: datetime) -> HouseholdView:
        invite = await self._usable_invite(code, now=now, for_update=True)
        if await self.households.get_membership(invite.household_id, user_id) is not None:
            # The invite is not consumed, so someone else can still use it.
            raise AlreadyMemberError()
        await self.households.add_member(
            HouseholdMember(
                household_id=invite.household_id, user_id=user_id, role=Role.MEMBER, joined_at=now
            )
        )
        invite.used_at = now
        invite.used_by = user_id
        return await self.households.get_view(invite.household_id, user_id)

    async def _usable_invite(
        self, code: str, *, now: datetime, for_update: bool
    ) -> HouseholdInvite:
        invite = await self.invites.get_by_code(code, for_update=for_update)
        if invite is None:
            raise InviteNotFoundError()
        # A used invite reports `invite_used` even after it has also expired.
        if invite.used_at is not None:
            raise InviteUsedError()
        if invite.expires_at <= now:
            raise InviteExpiredError()
        return invite

from fastapi import APIRouter, Response, status

from lumior.api.deps import CurrentUser, HouseholdAccess, HouseholdServiceDep, OwnerAccess
from lumior.core.clock import ClockDep
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
    UnauthorizedError,
    ValidationError,
    error_responses,
)
from lumior.modules.households.models import Role
from lumior.modules.households.repository import HouseholdView
from lumior.modules.households.schemas import (
    HouseholdNameRequest,
    HouseholdOut,
    InviteOut,
    InvitePreviewOut,
    MemberOut,
)

ACCESS_ERRORS = (NotAMemberError, HouseholdNotFoundError)
INVITE_ERRORS = (InviteNotFoundError, InviteExpiredError, InviteUsedError)

households_router = APIRouter(
    prefix="/households", tags=["households"], responses=error_responses(UnauthorizedError)
)
# The contract names these `households_*` too, so they share the tag.
invites_router = APIRouter(
    prefix="/invites", tags=["households"], responses=error_responses(UnauthorizedError)
)


def household_out(view: HouseholdView) -> HouseholdOut:
    return HouseholdOut(
        id=view.id,
        name=view.name,
        role=Role(view.role).value,
        member_count=view.member_count,
    )


@households_router.get(
    "",
    name="list",
    description="The current user's households, ordered by when they joined (oldest first).",
)
async def list_households(user: CurrentUser, service: HouseholdServiceDep) -> list[HouseholdOut]:
    return [household_out(view) for view in await service.list_for_user(user.id)]


@households_router.post(
    "",
    name="create",
    status_code=status.HTTP_201_CREATED,
    description="Create a household. The current user becomes its owner.",
    responses=error_responses(ValidationError),
)
async def create_household(
    body: HouseholdNameRequest, user: CurrentUser, service: HouseholdServiceDep, clock: ClockDep
) -> HouseholdOut:
    return household_out(await service.create(user.id, body.name, now=clock()))


@households_router.patch(
    "/{id}",
    name="update",
    description="Rename the household. Owner only.",
    responses=error_responses(*ACCESS_ERRORS, OwnerRequiredError, ValidationError),
)
async def update_household(
    body: HouseholdNameRequest, access: OwnerAccess, service: HouseholdServiceDep
) -> HouseholdOut:
    return household_out(await service.rename(access, body.name))


@households_router.get(
    "/{id}/members",
    name="list_members",
    description="Members ordered by when they joined (oldest first).",
    responses=error_responses(*ACCESS_ERRORS),
)
async def list_members(access: HouseholdAccess, service: HouseholdServiceDep) -> list[MemberOut]:
    return [
        MemberOut(user_id=m.user_id, name=m.name, email=m.email, role=Role(m.role).value)
        for m in await service.list_members(access)
    ]


@households_router.delete(
    "/{id}/members/{user_id}",
    name="remove_member",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    description=(
        "Leave the household (own `user_id`) or, as the owner, remove another member. "
        "The owner cannot leave."
    ),
    responses=error_responses(
        *ACCESS_ERRORS, OwnerRequiredError, MemberNotFoundError, OwnerCannotLeaveError
    ),
)
async def remove_member(
    user_id: str, access: HouseholdAccess, service: HouseholdServiceDep
) -> Response:
    await service.remove_member(access, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@households_router.post(
    "/{id}/invites",
    name="create_invite",
    status_code=status.HTTP_201_CREATED,
    description="Create a single-use invite. Owner only.",
    responses=error_responses(*ACCESS_ERRORS, OwnerRequiredError),
)
async def create_invite(
    access: OwnerAccess, service: HouseholdServiceDep, clock: ClockDep
) -> InviteOut:
    invite = await service.create_invite(access, now=clock())
    return InviteOut(code=invite.code, expires_at=invite.expires_at)


@invites_router.get(
    "/{code}",
    name="get_invite",
    description="Preview an invite before accepting it.",
    responses=error_responses(*INVITE_ERRORS),
)
async def get_invite(
    code: str, user: CurrentUser, service: HouseholdServiceDep, clock: ClockDep
) -> InvitePreviewOut:
    preview, already_member = await service.preview_invite(code, user.id, now=clock())
    return InvitePreviewOut(
        household_id=preview.invite.household_id,
        household_name=preview.household_name,
        invited_by=preview.invited_by,
        expires_at=preview.invite.expires_at,
        already_member=already_member,
    )


@invites_router.post(
    "/{code}/accept",
    name="accept_invite",
    description="Join the household as a member. The invite is used up.",
    responses=error_responses(*INVITE_ERRORS, AlreadyMemberError),
)
async def accept_invite(
    code: str, user: CurrentUser, service: HouseholdServiceDep, clock: ClockDep
) -> HouseholdOut:
    return household_out(await service.accept_invite(code, user.id, now=clock()))

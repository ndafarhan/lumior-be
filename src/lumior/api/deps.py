"""Dependencies shared by module routers: the authenticated caller and household access."""

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from lumior.core.clock import ClockDep
from lumior.core.config import Settings
from lumior.core.db import SessionDep
from lumior.core.errors import UnauthorizedError
from lumior.modules.households.service import HouseholdAccessContext, HouseholdService
from lumior.modules.identity.models import User
from lumior.modules.identity.service import AuthContext, IdentityService

# auto_error=False: missing or malformed credentials raise our 401 `unauthorized`,
# not FastAPI's default 403. The scheme still appears in the OpenAPI document.
_bearer = HTTPBearer(auto_error=False, description="Access token from a `Session`.")


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_identity_service(session: SessionDep, settings: SettingsDep) -> IdentityService:
    return IdentityService(session, settings)


IdentityServiceDep = Annotated[IdentityService, Depends(get_identity_service)]


async def get_auth_context(
    service: IdentityServiceDep,
    clock: ClockDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    if credentials is None:
        raise UnauthorizedError()
    return await service.authenticate(credentials.credentials, now=clock())


async def get_current_user(auth: Annotated[AuthContext, Depends(get_auth_context)]) -> User:
    return auth.user


CurrentSession = Annotated[AuthContext, Depends(get_auth_context)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def get_household_service(session: SessionDep, settings: SettingsDep) -> HouseholdService:
    return HouseholdService(session, invite_ttl=timedelta(days=settings.invite_ttl_days))


HouseholdServiceDep = Annotated[HouseholdService, Depends(get_household_service)]


async def get_household_access(
    user: CurrentUser,
    service: HouseholdServiceDep,
    # A string, not UUID: a malformed id must be 404 `household_not_found`, not 422.
    household_id: Annotated[str, Path(alias="id")],
) -> HouseholdAccessContext:
    return await service.check_access(household_id, user.id)


async def get_owner_access(
    access: Annotated[HouseholdAccessContext, Depends(get_household_access)],
) -> HouseholdAccessContext:
    access.require_owner()
    return access


HouseholdAccess = Annotated[HouseholdAccessContext, Depends(get_household_access)]
"""The caller is a member of the `{id}` household: 404 `household_not_found`, 403 `not_a_member`.

Use on every `/households/{id}/...` route. Dependencies run before the body is validated, so
these checks come before 422."""

OwnerAccess = Annotated[HouseholdAccessContext, Depends(get_owner_access)]
"""Like `HouseholdAccess`, and the caller is the owner: otherwise 403 `owner_required`."""

from fastapi import APIRouter, Request, Response, status

from lumior.api.deps import CurrentSession, CurrentUser, IdentityServiceDep, SettingsDep
from lumior.core.clock import ClockDep
from lumior.core.config import Settings
from lumior.core.errors import (
    EmailTakenError,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
    InvalidRefreshTokenError,
    UnauthorizedError,
    ValidationError,
    error_responses,
)
from lumior.modules.identity import models
from lumior.modules.identity.cookies import (
    clear_refresh_cookie,
    read_refresh_cookie,
    set_refresh_cookie,
)
from lumior.modules.identity.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    Session,
    UpdateMeRequest,
    User,
)
from lumior.modules.identity.service import IssuedSession

REFRESH_COOKIE_NOTE = "Authenticated by the refresh token cookie only; no `Authorization` header."

auth_router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(prefix="/me", tags=["identity"], responses=error_responses(UnauthorizedError))


def user_out(user: models.User) -> User:
    return User(id=user.id, email=user.email, name=user.name)


def session_response(issued: IssuedSession, response: Response, settings: Settings) -> Session:
    set_refresh_cookie(response, issued.refresh_token, settings)
    return Session(
        access_token=issued.access_token,
        token_type="bearer",  # noqa: S106 - the token scheme, not a secret
        expires_in=settings.access_token_ttl_seconds,
        user=user_out(issued.user),
    )


@auth_router.post(
    "/register",
    name="register",
    status_code=status.HTTP_201_CREATED,
    description="Create an account and sign in. Sets the refresh token cookie.",
    responses=error_responses(EmailTakenError, ValidationError),
)
async def register(
    body: RegisterRequest,
    response: Response,
    service: IdentityServiceDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> Session:
    issued = await service.register(
        name=body.name, email=body.email, password=body.password, now=clock()
    )
    return session_response(issued, response, settings)


@auth_router.post(
    "/login",
    name="login",
    description="Sign in. Sets the refresh token cookie.",
    responses=error_responses(InvalidCredentialsError, ValidationError),
)
async def login(
    body: LoginRequest,
    response: Response,
    service: IdentityServiceDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> Session:
    issued = await service.login(email=body.email, password=body.password, now=clock())
    return session_response(issued, response, settings)


@auth_router.post(
    "/refresh",
    name="refresh",
    description=f"Rotate the refresh token and return a new session. {REFRESH_COOKIE_NOTE}",
    responses=error_responses(InvalidRefreshTokenError),
)
async def refresh(
    request: Request,
    response: Response,
    service: IdentityServiceDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> Session:
    issued = await service.refresh(read_refresh_cookie(request, settings), now=clock())
    return session_response(issued, response, settings)


@auth_router.post(
    "/logout",
    name="logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    description=f"Revoke the session and clear the cookie. Always 204. {REFRESH_COOKIE_NOTE}",
)
async def logout(
    request: Request, service: IdentityServiceDep, settings: SettingsDep, clock: ClockDep
) -> Response:
    await service.logout(read_refresh_cookie(request, settings), now=clock())
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response, settings)
    return response


@me_router.get("", name="get_me")
async def get_me(user: CurrentUser) -> User:
    return user_out(user)


@me_router.patch("", name="update_me", responses=error_responses(ValidationError))
async def update_me(body: UpdateMeRequest, user: CurrentUser, service: IdentityServiceDep) -> User:
    return user_out(await service.update_name(user, body.name))


@me_router.post(
    "/password",
    name="change_password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    description="Change the password. This session stays signed in; other sessions are signed out.",
    responses=error_responses(InvalidCurrentPasswordError, ValidationError),
)
async def change_password(
    body: ChangePasswordRequest, auth: CurrentSession, service: IdentityServiceDep, clock: ClockDep
) -> Response:
    await service.change_password(
        auth,
        current_password=body.current_password,
        new_password=body.new_password,
        now=clock(),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

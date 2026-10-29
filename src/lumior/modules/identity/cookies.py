"""The refresh token cookie (contracts/auth-and-households.md section 5)."""

from fastapi import Request, Response

from lumior.core.config import Settings

# Only the auth endpoints receive the cookie. Must match where the auth router is mounted.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def read_refresh_cookie(request: Request, settings: Settings) -> str | None:
    return request.cookies.get(settings.refresh_cookie_name)


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.refresh_cookie_name,
        token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=REFRESH_COOKIE_PATH,
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )

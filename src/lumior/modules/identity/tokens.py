"""Access tokens (signed JWT) and refresh tokens (random, stored hashed)."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - a claim value, not a secret


class InvalidAccessTokenError(Exception):
    """The access token is malformed, tampered with, expired, or not an access token."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    # The sign-in session the token belongs to (shared with its refresh tokens).
    session_id: uuid.UUID


def create_access_token(
    claims: AccessTokenClaims, *, secret_key: str, now: datetime, ttl: timedelta
) -> str:
    payload = {
        "sub": str(claims.user_id),
        "sid": str(claims.session_id),
        "typ": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str, *, secret_key: str, now: datetime) -> AccessTokenClaims:
    try:
        # Time is checked against `now` below instead of the wall clock, so tests control it.
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[ALGORITHM],
            options={
                "require": ["sub", "sid", "typ", "exp"],
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
        if payload["typ"] != ACCESS_TOKEN_TYPE:
            raise InvalidAccessTokenError("wrong token type")
        if not isinstance(payload["exp"], int) or payload["exp"] <= now.timestamp():
            raise InvalidAccessTokenError("expired")
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]), session_id=uuid.UUID(payload["sid"])
        )
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise InvalidAccessTokenError(str(exc)) from exc


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

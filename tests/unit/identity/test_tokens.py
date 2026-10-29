import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from lumior.modules.identity.tokens import (
    AccessTokenClaims,
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)

SECRET = "unit-test-secret-key-at-least-32-chars"
NOW = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
TTL = timedelta(minutes=15)
CLAIMS = AccessTokenClaims(user_id=uuid.uuid4(), session_id=uuid.uuid4())


def make_token(**overrides: object) -> str:
    payload: dict[str, object] = {
        "sub": str(CLAIMS.user_id),
        "sid": str(CLAIMS.session_id),
        "typ": "access",
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + TTL).timestamp()),
    }
    payload.update(overrides)
    return jwt.encode({k: v for k, v in payload.items() if v is not None}, SECRET, "HS256")


def test_round_trip() -> None:
    token = create_access_token(CLAIMS, secret_key=SECRET, now=NOW, ttl=TTL)

    assert decode_access_token(token, secret_key=SECRET, now=NOW) == CLAIMS


def test_valid_until_just_before_expiry() -> None:
    token = create_access_token(CLAIMS, secret_key=SECRET, now=NOW, ttl=TTL)
    almost = NOW + TTL - timedelta(seconds=1)

    assert decode_access_token(token, secret_key=SECRET, now=almost) == CLAIMS


def test_expired() -> None:
    token = create_access_token(CLAIMS, secret_key=SECRET, now=NOW, ttl=TTL)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, secret_key=SECRET, now=NOW + TTL)


def test_wrong_signature() -> None:
    token = create_access_token(
        CLAIMS, secret_key="another-secret-key-at-least-32-chars", now=NOW, ttl=TTL
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, secret_key=SECRET, now=NOW)


def test_tampered_payload() -> None:
    header, _, signature = create_access_token(CLAIMS, secret_key=SECRET, now=NOW, ttl=TTL).split(
        "."
    )
    other_payload = make_token(sub=str(uuid.uuid4())).split(".")[1]

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(f"{header}.{other_payload}.{signature}", secret_key=SECRET, now=NOW)


@pytest.mark.parametrize(
    "token",
    [
        make_token(typ="refresh"),
        make_token(sid=None),
        make_token(sub="not-a-uuid"),
        make_token(exp=None),
        "not.a.jwt",
        "",
    ],
)
def test_invalid_tokens(token: str) -> None:
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, secret_key=SECRET, now=NOW)


def test_refresh_tokens_are_random_and_url_safe() -> None:
    first, second = new_refresh_token(), new_refresh_token()

    assert first != second
    assert len(first) >= 43
    assert all(c.isalnum() or c in "-_" for c in first)


def test_refresh_token_hash_is_stable_sha256_hex() -> None:
    token = new_refresh_token()

    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert len(hash_refresh_token(token)) == 64
    assert hash_refresh_token(token) != token

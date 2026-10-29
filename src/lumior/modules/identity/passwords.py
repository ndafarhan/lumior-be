"""Argon2id password hashing, run off the event loop."""

from dataclasses import dataclass

from anyio import to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# Verified against when the email is unknown, so a failed login takes the same time either way.
_DUMMY_HASH = _hasher.hash("lumior-dummy-password")


@dataclass(frozen=True)
class VerifyResult:
    valid: bool
    needs_rehash: bool = False


async def hash_password(password: str) -> str:
    return await to_thread.run_sync(_hasher.hash, password)


def _verify(password_hash: str, password: str) -> VerifyResult:
    try:
        _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return VerifyResult(valid=False)
    return VerifyResult(valid=True, needs_rehash=_hasher.check_needs_rehash(password_hash))


async def verify_password(password_hash: str | None, password: str) -> VerifyResult:
    """Check `password` against `password_hash`; `None` (unknown user) is never valid."""
    if password_hash is None:
        await to_thread.run_sync(_verify, _DUMMY_HASH, password)
        return VerifyResult(valid=False)
    return await to_thread.run_sync(_verify, password_hash, password)

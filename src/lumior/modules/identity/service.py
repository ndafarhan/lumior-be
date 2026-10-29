"""Sign-up, sign-in, sessions, and the current user's account."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from lumior.core.config import Settings
from lumior.core.errors import (
    EmailTakenError,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
    InvalidRefreshTokenError,
    UnauthorizedError,
)
from lumior.modules.identity.models import RefreshToken, User
from lumior.modules.identity.passwords import hash_password, verify_password
from lumior.modules.identity.repository import (
    EmailAlreadyExistsError,
    RefreshTokenRepository,
    UserRepository,
)
from lumior.modules.identity.tokens import (
    AccessTokenClaims,
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)


@dataclass(frozen=True)
class IssuedSession:
    user: User
    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class AuthContext:
    """The caller of an authenticated request."""

    user: User
    session_id: uuid.UUID


class IdentityService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.settings = settings

    @property
    def access_token_ttl(self) -> timedelta:
        return timedelta(seconds=self.settings.access_token_ttl_seconds)

    @property
    def refresh_token_ttl(self) -> timedelta:
        return timedelta(days=self.settings.refresh_token_ttl_days)

    async def register(
        self, *, name: str, email: str, password: str, now: datetime
    ) -> IssuedSession:
        if await self.users.get_by_email(email) is not None:
            raise EmailTakenError()
        user = User(
            id=uuid.uuid4(),
            email=email,
            name=name,
            password_hash=await hash_password(password),
            created_at=now,
        )
        try:
            await self.users.add(user)
        except EmailAlreadyExistsError:
            raise EmailTakenError() from None
        return await self._issue(user, session_id=uuid.uuid4(), now=now)

    async def login(self, *, email: str, password: str, now: datetime) -> IssuedSession:
        user = await self.users.get_by_email(email.strip().lower())
        result = await verify_password(user.password_hash if user else None, password)
        if user is None or not result.valid:
            raise InvalidCredentialsError()
        if result.needs_rehash:
            user.password_hash = await hash_password(password)
        return await self._issue(user, session_id=uuid.uuid4(), now=now)

    async def refresh(self, refresh_token: str | None, *, now: datetime) -> IssuedSession:
        """Rotate `refresh_token`. A token replaced within the grace window still works."""
        if not refresh_token:
            raise InvalidRefreshTokenError()
        stored = await self.refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
        if stored is None or stored.revoked_at is not None or stored.expires_at <= now:
            raise InvalidRefreshTokenError()
        grace = timedelta(seconds=self.settings.refresh_grace_seconds)
        if stored.replaced_at is not None and now - stored.replaced_at > grace:
            raise InvalidRefreshTokenError()
        user = await self.users.get(stored.user_id)
        if user is None:
            raise InvalidRefreshTokenError()
        if stored.replaced_at is None:
            stored.replaced_at = now
        return await self._issue(user, session_id=stored.session_id, now=now)

    async def logout(self, refresh_token: str | None, *, now: datetime) -> None:
        """Revoke the session the token belongs to. Unknown or invalid tokens are ignored."""
        if not refresh_token:
            return
        stored = await self.refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
        if stored is not None:
            await self.refresh_tokens.revoke_session(stored.session_id, now)

    async def authenticate(self, access_token: str, *, now: datetime) -> AuthContext:
        try:
            claims = decode_access_token(
                access_token, secret_key=self.settings.secret_key.get_secret_value(), now=now
            )
        except InvalidAccessTokenError:
            raise UnauthorizedError() from None
        user = await self.users.get(claims.user_id)
        if user is None:
            raise UnauthorizedError()
        return AuthContext(user=user, session_id=claims.session_id)

    async def update_name(self, user: User, name: str) -> User:
        user.name = name
        return user

    async def change_password(
        self, auth: AuthContext, *, current_password: str, new_password: str, now: datetime
    ) -> None:
        """Replace the password and sign out every other session of the user."""
        if not (await verify_password(auth.user.password_hash, current_password)).valid:
            raise InvalidCurrentPasswordError()
        auth.user.password_hash = await hash_password(new_password)
        await self.refresh_tokens.revoke_other_sessions(auth.user.id, auth.session_id, now)

    async def _issue(self, user: User, *, session_id: uuid.UUID, now: datetime) -> IssuedSession:
        refresh_token = new_refresh_token()
        await self.refresh_tokens.add(
            RefreshToken(
                id=uuid.uuid4(),
                user_id=user.id,
                session_id=session_id,
                token_hash=hash_refresh_token(refresh_token),
                created_at=now,
                expires_at=now + self.refresh_token_ttl,
            )
        )
        access_token = create_access_token(
            AccessTokenClaims(user_id=user.id, session_id=session_id),
            secret_key=self.settings.secret_key.get_secret_value(),
            now=now,
            ttl=self.access_token_ttl,
        )
        return IssuedSession(user=user, access_token=access_token, refresh_token=refresh_token)

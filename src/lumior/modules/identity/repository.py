import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lumior.modules.identity.models import RefreshToken, User


class EmailAlreadyExistsError(Exception):
    pass


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def add(self, user: User) -> None:
        """Insert `user`; raises `EmailAlreadyExistsError` if a concurrent insert won."""
        try:
            # A savepoint keeps the outer transaction usable if the insert fails.
            async with self.session.begin_nested():
                self.session.add(user)
        except IntegrityError as exc:
            raise EmailAlreadyExistsError from exc


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, token: RefreshToken) -> None:
        self.session.add(token)
        await self.session.flush()

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        """Load and lock the token row, so concurrent refreshes of one token run in turn."""
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        return result.scalar_one_or_none()

    async def revoke_session(self, session_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id == session_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_other_sessions(
        self, user_id: uuid.UUID, keep_session_id: uuid.UUID, now: datetime
    ) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.session_id != keep_session_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

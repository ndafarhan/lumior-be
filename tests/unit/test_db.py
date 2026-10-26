from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from lumior.core.db import Base, relationship, session_scope


def fake_sessionmaker() -> tuple[MagicMock, AsyncMock]:
    session = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=context), session


async def test_session_commits_on_success() -> None:
    sessionmaker, session = fake_sessionmaker()

    async for _ in session_scope(sessionmaker):
        pass

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


async def test_session_rolls_back_on_exception() -> None:
    sessionmaker, session = fake_sessionmaker()
    scope = session_scope(sessionmaker)
    await anext(scope)

    with pytest.raises(RuntimeError):
        await scope.athrow(RuntimeError("boom"))

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


class _Parent(Base):
    __tablename__ = "test_parent"
    id: Mapped[int] = mapped_column(primary_key=True)
    children: Mapped[list["_Child"]] = relationship(back_populates="parent")


class _Child(Base):
    __tablename__ = "test_child"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("test_parent.id"))
    parent: Mapped[_Parent] = relationship(back_populates="children")


def test_relationships_default_to_lazy_raise() -> None:
    assert _Parent.children.property.lazy == "raise"
    assert _Child.parent.property.lazy == "raise"


def test_constraint_naming_convention() -> None:
    fk = next(iter(_Child.__table__.foreign_keys)).constraint
    assert fk.name == "fk_test_child_parent_id_test_parent"
    assert _Parent.__table__.primary_key.name == "pk_test_parent"

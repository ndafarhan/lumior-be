from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def test_pg_trgm_installed_after_migration(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
    )

    assert result.scalar_one() == "pg_trgm"


async def test_alembic_is_at_head(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT version_num FROM alembic_version"))

    assert result.scalar_one() == "8e37e267a13c"


async def test_test_writes_are_isolated(db_session: AsyncSession, db_engine: AsyncEngine) -> None:
    await db_session.execute(text("CREATE TABLE isolation_probe (id int)"))
    await db_session.execute(text("INSERT INTO isolation_probe VALUES (1)"))
    await db_session.commit()

    async with db_engine.connect() as other:
        visible = await other.execute(text("SELECT to_regclass('public.isolation_probe')"))
        assert visible.scalar_one() is None

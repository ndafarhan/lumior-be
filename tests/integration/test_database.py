from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.integration.conftest import PROJECT_ROOT


async def test_pg_trgm_installed_after_migration(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
    )

    assert result.scalar_one() == "pg_trgm"


async def test_alembic_is_at_head(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT version_num FROM alembic_version"))

    script = ScriptDirectory.from_config(Config(str(PROJECT_ROOT / "alembic.ini")))
    assert result.scalar_one() == script.get_current_head()


async def test_test_writes_are_isolated(db_session: AsyncSession, db_engine: AsyncEngine) -> None:
    await db_session.execute(text("CREATE TABLE isolation_probe (id int)"))
    await db_session.execute(text("INSERT INTO isolation_probe VALUES (1)"))
    await db_session.commit()

    async with db_engine.connect() as other:
        visible = await other.execute(text("SELECT to_regclass('public.isolation_probe')"))
        assert visible.scalar_one() is None


async def test_auth_and_household_tables_exist(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    )

    assert {
        "users",
        "refresh_tokens",
        "households",
        "household_members",
        "household_invites",
    } <= set(result.scalars())

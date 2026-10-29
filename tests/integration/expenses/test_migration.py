"""The expenses migration backfills households that existed before it."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from tests.integration.conftest import PROJECT_ROOT

BEFORE_EXPENSES = "de50fb9d0bec"

DEFAULT_NAMES = {
    "Groceries",
    "Dining out",
    "Transport",
    "Utilities",
    "Housing",
    "Health",
    "Education",
    "Entertainment",
    "Other",
}


def upgrade(url: str, revision: str) -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(command.upgrade, config, revision).result()


@pytest.fixture(scope="module")
def fresh_database_url() -> Iterator[str]:
    """A database of its own, since this test stops at an older revision."""
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


async def test_existing_households_get_currency_and_default_categories(
    fresh_database_url: str,
) -> None:
    upgrade(fresh_database_url, BEFORE_EXPENSES)
    engine = create_async_engine(fresh_database_url, poolclass=pool.NullPool)
    try:
        async with engine.begin() as connection:
            for name in ("Rumah", "Kos"):
                await connection.execute(
                    text(
                        "INSERT INTO households (id, name, created_at) "
                        "VALUES (gen_random_uuid(), :name, now())"
                    ),
                    {"name": name},
                )

        upgrade(fresh_database_url, "head")

        async with engine.connect() as connection:
            currencies = (await connection.execute(text("SELECT currency FROM households"))).all()
            categories = (
                await connection.execute(
                    text(
                        "SELECT h.name, c.name, c.archived FROM expense_categories c "
                        "JOIN households h ON h.id = c.household_id"
                    )
                )
            ).all()
    finally:
        await engine.dispose()

    assert [row.currency for row in currencies] == ["IDR", "IDR"]
    for household in ("Rumah", "Kos"):
        names = {row[1] for row in categories if row[0] == household}
        assert names == DEFAULT_NAMES
    assert len(categories) == 18
    assert not any(row.archived for row in categories)

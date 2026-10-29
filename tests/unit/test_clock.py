from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from lumior.core.clock import ClockDep, system_clock

FIXED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

router = APIRouter(prefix="/api/v1/_test")


@router.get("/now")
async def now(clock: ClockDep) -> dict[str, str]:
    return {"now": clock().isoformat()}


def test_system_clock_is_aware_utc() -> None:
    assert system_clock().tzinfo is UTC


def test_app_uses_system_clock_by_default(app: FastAPI) -> None:
    assert app.state.clock is system_clock


async def test_replaced_clock_is_returned_by_dependency(app: FastAPI) -> None:
    app.include_router(router)
    app.state.clock = lambda: FIXED

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/_test/now")

    assert response.json() == {"now": FIXED.isoformat()}

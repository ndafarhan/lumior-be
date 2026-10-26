import json
import logging

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from lumior.main import create_app
from tests.conftest import make_settings

router = APIRouter(prefix="/api/v1/_test")


@router.get("/boom")
async def boom() -> None:
    raise RuntimeError("database password is hunter2")


def parse_json_lines(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


async def test_unhandled_error_logs_traceback_and_request_id_server_side(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(make_settings(environment="test"))
    app.include_router(router)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/_test/boom", headers={"X-Request-ID": "req-500"})

    assert response.status_code == 500
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text

    records = parse_json_lines(capsys.readouterr().out)
    errors = [r for r in records if r["level"] == "ERROR"]
    assert len(errors) == 1
    assert errors[0]["request_id"] == "req-500"
    assert errors[0]["path"] == "/api/v1/_test/boom"
    assert "Traceback" in str(errors[0]["exc_info"])
    assert "hunter2" in str(errors[0]["exc_info"])
    await app.state.engine.dispose()


async def test_every_log_line_has_request_id(capsys: pytest.CaptureFixture[str]) -> None:
    app = create_app(make_settings(environment="staging"))
    log = logging.getLogger("lumior.test")

    test_router = APIRouter()

    @test_router.get("/_log")
    async def emit() -> dict[str, str]:
        log.info("inside request")
        return {}

    app.include_router(test_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/_log", headers={"X-Request-ID": "req-log"})
    log.info("outside request")

    records = parse_json_lines(capsys.readouterr().out)
    by_message = {r["message"]: r for r in records}
    assert by_message["inside request"]["request_id"] == "req-log"
    assert by_message["outside request"]["request_id"] is None
    assert all("request_id" in r for r in records)
    await app.state.engine.dispose()


async def test_development_uses_plain_text(capsys: pytest.CaptureFixture[str]) -> None:
    app = create_app(make_settings(environment="development"))
    logging.getLogger("lumior.test").warning("plain line")

    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "plain line" in out
    assert not parse_json_lines(out)
    await app.state.engine.dispose()

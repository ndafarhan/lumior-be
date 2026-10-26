import pytest
from httpx import AsyncClient

from lumior.core.request_id import resolve_request_id


async def test_supplied_request_id_is_reused(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={"X-Request-ID": "abc-123"})

    assert response.headers["X-Request-ID"] == "abc-123"


async def test_missing_request_id_is_generated(client: AsyncClient) -> None:
    first = await client.get("/health/live")
    second = await client.get("/health/live")

    assert first.headers["X-Request-ID"]
    assert second.headers["X-Request-ID"]
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


async def test_too_long_request_id_is_replaced(client: AsyncClient) -> None:
    supplied = "a" * 129

    response = await client.get("/health/live", headers={"X-Request-ID": supplied})

    assert response.headers["X-Request-ID"]
    assert response.headers["X-Request-ID"] != supplied


async def test_request_id_on_error_responses(client: AsyncClient) -> None:
    response = await client.get("/api/v1/nope", headers={"X-Request-ID": "trace-1"})

    assert response.headers["X-Request-ID"] == "trace-1"
    assert response.json()["error"]["request_id"] == "trace-1"


@pytest.mark.parametrize("value", ["a", "x" * 128, "!~", "Req.ID_42:abc"])
def test_valid_values_are_kept(value: str) -> None:
    assert resolve_request_id(value) == value


@pytest.mark.parametrize("value", [None, "", "x" * 129, "has space", "tab\there", "café"])
def test_invalid_values_are_replaced(value: str | None) -> None:
    generated = resolve_request_id(value)
    assert generated != value
    assert len(generated) == 32

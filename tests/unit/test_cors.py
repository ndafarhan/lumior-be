from httpx import AsyncClient

from tests.conftest import ALLOWED_ORIGIN


async def test_preflight_from_allowed_origin(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/openapi.json",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert response.headers["Access-Control-Allow-Credentials"] == "true"


async def test_simple_request_from_allowed_origin(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={"Origin": ALLOWED_ORIGIN})

    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert "X-Request-ID" in response.headers["Access-Control-Expose-Headers"]


async def test_request_from_disallowed_origin(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={"Origin": "http://evil.example"})

    assert "Access-Control-Allow-Origin" not in response.headers


async def test_preflight_from_disallowed_origin(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/openapi.json",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )

    assert "Access-Control-Allow-Origin" not in response.headers


async def test_error_responses_carry_cors_headers(client: AsyncClient) -> None:
    response = await client.get("/api/v1/nope", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 404
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN

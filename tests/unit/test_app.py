from httpx import AsyncClient


async def test_client_fixture_serves_the_app(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200


async def test_openapi_document_is_served_under_api_prefix(client: AsyncClient) -> None:
    response = await client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    assert response.json()["openapi"].startswith("3.")

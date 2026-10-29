from httpx import AsyncClient


async def test_live_returns_ok_without_reachable_database(client: AsyncClient) -> None:
    # The default test settings point at a database that does not exist.
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_live_requires_no_credentials(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={"Authorization": "Bearer nonsense"})

    assert response.status_code == 200

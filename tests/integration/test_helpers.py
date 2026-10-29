from datetime import timedelta

from httpx import AsyncClient

from tests.integration.helpers import FakeClock, register


async def test_registered_user_can_call_authenticated_endpoint(client: AsyncClient) -> None:
    rina = await register(client)

    response = await client.get("/api/v1/me", headers=rina.headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(rina.id)


def test_fake_clock_moves_forward() -> None:
    clock = FakeClock()
    first = clock()
    clock.advance(seconds=30)

    assert clock() - first >= timedelta(seconds=30)

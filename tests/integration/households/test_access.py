"""The access check shared by every `/households/{id}/...` route (specs/households)."""

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.helpers import create_household, error_code, join, register

# (method, path suffix, json body) for each household-scoped route.
ROUTES = [
    ("patch", "", {"name": "New name"}),
    ("get", "/members", None),
    ("delete", "/members/{other}", None),
    ("post", "/invites", None),
]


@pytest.mark.parametrize(("method", "suffix", "body"), ROUTES)
@pytest.mark.parametrize("household_id", [str(uuid.uuid4()), "not-a-uuid"])
async def test_unknown_or_malformed_household(
    client: AsyncClient, method: str, suffix: str, body: object, household_id: str
) -> None:
    rina = await register(client)
    path = f"/api/v1/households/{household_id}{suffix.format(other=uuid.uuid4())}"

    response = await client.request(method, path, json=body, headers=rina.headers)

    assert response.status_code == 404
    assert error_code(response) == "household_not_found"


@pytest.mark.parametrize(("method", "suffix", "body"), ROUTES)
async def test_not_a_member(client: AsyncClient, method: str, suffix: str, body: object) -> None:
    rina, outsider = await register(client, "Rina"), await register(client, "Out")
    household = await create_household(client, rina)
    path = f"/api/v1/households/{household}{suffix.format(other=rina.id)}"

    response = await client.request(method, path, json=body, headers=outsider.headers)

    assert response.status_code == 403
    assert error_code(response) == "not_a_member"


@pytest.mark.parametrize("body", [{"name": "   "}, {}, {"name": 5}])
async def test_non_member_with_invalid_body_gets_403_not_422(
    client: AsyncClient, body: object
) -> None:
    rina, outsider = await register(client, "Rina"), await register(client, "Out")
    household = await create_household(client, rina)

    response = await client.patch(
        f"/api/v1/households/{household}", json=body, headers=outsider.headers
    )

    assert response.status_code == 403
    assert error_code(response) == "not_a_member"


async def test_member_on_owner_only_route_with_invalid_body_gets_403(
    client: AsyncClient,
) -> None:
    rina, budi = await register(client, "Rina"), await register(client, "Budi")
    household = await create_household(client, rina)
    await join(client, rina, household, budi)

    response = await client.patch(
        f"/api/v1/households/{household}", json={"name": ""}, headers=budi.headers
    )

    assert response.status_code == 403
    assert error_code(response) == "owner_required"


@pytest.mark.parametrize(("method", "suffix", "body"), ROUTES)
async def test_unauthenticated_comes_first(
    client: AsyncClient, method: str, suffix: str, body: object
) -> None:
    path = f"/api/v1/households/not-a-uuid{suffix.format(other=uuid.uuid4())}"

    response = await client.request(method, path, json=body)

    assert response.status_code == 401
    assert error_code(response) == "unauthorized"

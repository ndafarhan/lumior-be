"""The frontend's main flow end to end (contracts/auth-and-households.md)."""

from httpx import AsyncClient

from tests.integration.helpers import error_code, post_with_cookie, register, signed_in


async def test_frontend_flow(client: AsyncClient) -> None:
    # Rina signs up and creates a household.
    rina = await register(client, "Rina", "rina.flow@example.com")
    created = await client.post(
        "/api/v1/households", json={"name": "Rumah Bandung"}, headers=rina.headers
    )
    household = created.json()["id"]

    # She invites Budi, who signs up, previews the link, and joins.
    invite = await client.post(f"/api/v1/households/{household}/invites", headers=rina.headers)
    code = invite.json()["code"]
    budi = await register(client, "Budi", "budi.flow@example.com")
    preview = await client.get(f"/api/v1/invites/{code}", headers=budi.headers)
    assert preview.json()["invited_by"] == "Rina"
    assert preview.json()["already_member"] is False
    accepted = await client.post(f"/api/v1/invites/{code}/accept", headers=budi.headers)
    assert accepted.json()["role"] == "member"

    # Rina sees both members.
    members = await client.get(f"/api/v1/households/{household}/members", headers=rina.headers)
    assert [(m["name"], m["role"]) for m in members.json()] == [
        ("Rina", "owner"),
        ("Budi", "member"),
    ]

    # Budi leaves; the household is gone from his list.
    left = await client.delete(
        f"/api/v1/households/{household}/members/{budi.id}", headers=budi.headers
    )
    assert left.status_code == 204
    assert (await client.get("/api/v1/households", headers=budi.headers)).json() == []

    # A page load: Rina's app refreshes to restore the session, then signs out.
    refreshed = await post_with_cookie(client, "/api/v1/auth/refresh", rina.refresh_token)
    assert refreshed.status_code == 200
    session = signed_in(refreshed)
    households = await client.get("/api/v1/households", headers=session.headers)
    assert [h["member_count"] for h in households.json()] == [1]

    logout = await post_with_cookie(client, "/api/v1/auth/logout", session.refresh_token)
    assert logout.status_code == 204
    after = await post_with_cookie(client, "/api/v1/auth/refresh", session.refresh_token)
    assert error_code(after) == "invalid_refresh_token"

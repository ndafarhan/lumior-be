"""The frontend's main flows end to end (contracts/auth-and-households.md, expenses.md)."""

from httpx import AsyncClient

from tests.integration.helpers import error_code, join, post_with_cookie, register, signed_in


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


async def test_expenses_flow(client: AsyncClient) -> None:
    # Rina creates a household; Budi joins it.
    rina = await register(client, "Rina", "rina.expenses@example.com")
    budi = await register(client, "Budi", "budi.expenses@example.com")
    created = await client.post(
        "/api/v1/households", json={"name": "Rumah Bandung"}, headers=rina.headers
    )
    assert created.json()["currency"] == "IDR"
    household = created.json()["id"]
    await join(client, rina, household, budi)
    base = f"/api/v1/households/{household}"

    # The expenses screen loads the categories once and looks names up by id.
    categories = await client.get(f"{base}/expense-categories", headers=budi.headers)
    ids = {c["name"]: c["id"] for c in categories.json()}
    assert len(ids) == 9

    # Both of them record expenses.
    for user, category, amount, day in [
        (rina, "Groceries", "45000.00", "2026-10-03"),
        (budi, "Groceries", "30000.00", "2026-10-05"),
        (budi, "Transport", "20000.00", "2026-10-05"),
    ]:
        response = await client.post(
            f"{base}/expenses",
            json={
                "amount": {"amount": amount, "currency": "IDR"},
                "spent_on": day,
                "category_id": ids[category],
            },
            headers=user.headers,
        )
        assert response.status_code == 201, response.text

    # The month list, two at a time, newest first.
    first = await client.get(
        f"{base}/expenses", params={"month": "2026-10", "limit": 2}, headers=rina.headers
    )
    second = await client.get(
        f"{base}/expenses",
        params={"month": "2026-10", "limit": 2, "cursor": first.json()["next_cursor"]},
        headers=rina.headers,
    )
    items = first.json()["items"] + second.json()["items"]
    assert [e["spent_on"] for e in items] == ["2026-10-05", "2026-10-05", "2026-10-03"]
    assert second.json()["next_cursor"] is None

    # The summary card.
    summary = await client.get(
        f"{base}/expense-summary", params={"month": "2026-10"}, headers=rina.headers
    )
    assert summary.json()["total"] == {"amount": "95000.00", "currency": "IDR"}
    assert [(c["category_id"], c["count"]) for c in summary.json()["categories"]] == [
        (ids["Groceries"], 2),
        (ids["Transport"], 1),
    ]

    # Groceries is archived; its expenses can still be edited, but no new ones go in it.
    archived = await client.patch(
        f"{base}/expense-categories/{ids['Groceries']}",
        json={"archived": True},
        headers=rina.headers,
    )
    assert archived.json()["archived"] is True
    groceries = next(e for e in items if e["spent_on"] == "2026-10-03")
    edited = await client.patch(
        f"{base}/expenses/{groceries['id']}",
        json={"note": "Weekly market", "category_id": ids["Groceries"]},
        headers=budi.headers,
    )
    assert edited.status_code == 200
    assert edited.json()["note"] == "Weekly market"
    rejected = await client.post(
        f"{base}/expenses",
        json={
            "amount": {"amount": "10000.00", "currency": "IDR"},
            "spent_on": "2026-10-06",
            "category_id": ids["Groceries"],
        },
        headers=budi.headers,
    )
    assert error_code(rejected) == "category_archived"

    # Budi deletes his transport expense; the summary follows.
    transport = next(e for e in items if e["category_id"] == ids["Transport"])
    deleted = await client.delete(f"{base}/expenses/{transport['id']}", headers=budi.headers)
    assert deleted.status_code == 204
    after = await client.get(
        f"{base}/expense-summary", params={"month": "2026-10"}, headers=rina.headers
    )
    assert after.json()["total"]["amount"] == "75000.00"

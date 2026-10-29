"""Helpers for API tests: a controllable clock and signed-in test users."""

import itertools
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient, Response

COOKIE_NAME = "lumior_refresh"
PASSWORD = "correct-horse-battery"

_emails = itertools.count(1)


class FakeClock:
    """A clock tests can move. Each reading is 1 ms later than the previous one, so rows
    written in one test still get distinct, increasing timestamps."""

    def __init__(self, start: datetime = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)) -> None:
        self.current = start

    def __call__(self) -> datetime:
        now = self.current
        self.current += timedelta(milliseconds=1)
        return now

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


@dataclass
class SignedIn:
    id: uuid.UUID
    name: str
    email: str
    access_token: str
    refresh_token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def refresh_cookie(response: Response) -> str | None:
    return response.cookies.get(COOKIE_NAME)


def set_cookie_headers(response: Response) -> list[str]:
    return response.headers.get_list("set-cookie")


async def post_with_cookie(client: AsyncClient, path: str, token: str | None) -> Response:
    """POST with only the given refresh cookie (the client's cookie jar is ignored)."""
    client.cookies.clear()
    headers = {"Cookie": f"{COOKIE_NAME}={token}"} if token is not None else {}
    response = await client.post(path, headers=headers)
    client.cookies.clear()
    return response


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}{next(_emails)}@example.com"


async def register(
    client: AsyncClient,
    name: str = "Rina",
    email: str | None = None,
    password: str = PASSWORD,
    **extra: Any,
) -> SignedIn:
    email = email or unique_email(name.lower())
    response = await client.post(
        "/api/v1/auth/register", json={"name": name, "email": email, "password": password}
    )
    client.cookies.clear()
    assert response.status_code == 201, response.text
    return signed_in(response)


async def login(client: AsyncClient, email: str, password: str = PASSWORD) -> SignedIn:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    client.cookies.clear()
    assert response.status_code == 200, response.text
    return signed_in(response)


def signed_in(response: Response) -> SignedIn:
    body = response.json()
    token = refresh_cookie(response)
    assert token is not None
    return SignedIn(
        id=uuid.UUID(body["user"]["id"]),
        name=body["user"]["name"],
        email=body["user"]["email"],
        access_token=body["access_token"],
        refresh_token=token,
    )


def error_code(response: Response) -> str:
    code: str = response.json()["error"]["code"]
    return code


async def create_household(
    client: AsyncClient, owner: SignedIn, name: str = "Rumah", currency: str | None = None
) -> str:
    body = {"name": name} if currency is None else {"name": name, "currency": currency}
    response = await client.post("/api/v1/households", json=body, headers=owner.headers)
    assert response.status_code == 201, response.text
    household_id: str = response.json()["id"]
    return household_id


async def join(client: AsyncClient, owner: SignedIn, household_id: str, user: SignedIn) -> None:
    """Add `user` to the household through an invite from `owner`."""
    invite = await client.post(f"/api/v1/households/{household_id}/invites", headers=owner.headers)
    assert invite.status_code == 201, invite.text
    accepted = await client.post(
        f"/api/v1/invites/{invite.json()['code']}/accept", headers=user.headers
    )
    assert accepted.status_code == 200, accepted.text

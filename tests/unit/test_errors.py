from collections.abc import AsyncIterator

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient, Response
from pydantic import BaseModel

from lumior.core.errors import (
    AlreadyMemberError,
    AppError,
    ConflictError,
    EmailTakenError,
    ErrorResponse,
    ForbiddenError,
    HouseholdNotFoundError,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
    InvalidRefreshTokenError,
    InviteExpiredError,
    InviteNotFoundError,
    InviteUsedError,
    MemberNotFoundError,
    NotAMemberError,
    NotFoundError,
    OwnerCannotLeaveError,
    OwnerRequiredError,
    UnauthorizedError,
    ValidationError,
    error_responses,
)

SECRET_TEXT = "secret-dsn postgresql://admin:hunter2@db/prod"


class Item(BaseModel):
    name: str
    quantity: int


router = APIRouter(prefix="/api/v1/_test")


@router.post("/items")
async def create_item(item: Item) -> Item:
    return item


@router.get("/items")
async def list_items() -> list[Item]:
    return []


@router.get("/boom")
async def boom() -> None:
    raise RuntimeError(SECRET_TEXT)


@router.get("/missing")
async def missing() -> None:
    raise NotFoundError("Item 42 does not exist.", details=[{"id": 42}])


@router.get("/conflict")
async def conflict() -> None:
    raise ConflictError()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def assert_envelope(response: Response, status: int, code: str) -> dict[str, object]:
    assert response.status_code == status
    error = response.json()["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert error["message"]
    assert isinstance(error["details"], list)
    assert error["request_id"] == response.headers["X-Request-ID"]
    return error  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("exc_type", "status", "code"),
    [
        (NotFoundError, 404, "not_found"),
        (ConflictError, 409, "conflict"),
        (ValidationError, 422, "validation_error"),
        (UnauthorizedError, 401, "unauthorized"),
        (ForbiddenError, 403, "forbidden"),
        (AppError, 400, "bad_request"),
        # contracts/auth-and-households.md section 7
        (InvalidCurrentPasswordError, 400, "invalid_current_password"),
        (InvalidCredentialsError, 401, "invalid_credentials"),
        (InvalidRefreshTokenError, 401, "invalid_refresh_token"),
        (NotAMemberError, 403, "not_a_member"),
        (OwnerRequiredError, 403, "owner_required"),
        (HouseholdNotFoundError, 404, "household_not_found"),
        (MemberNotFoundError, 404, "member_not_found"),
        (InviteNotFoundError, 404, "invite_not_found"),
        (EmailTakenError, 409, "email_taken"),
        (OwnerCannotLeaveError, 409, "owner_cannot_leave"),
        (AlreadyMemberError, 409, "already_member"),
        (InviteExpiredError, 410, "invite_expired"),
        (InviteUsedError, 410, "invite_used"),
    ],
)
def test_domain_exception_mapping(exc_type: type[AppError], status: int, code: str) -> None:
    exc = exc_type()
    assert exc.status_code == status
    assert exc.code == code
    assert exc.message
    assert exc.details == []


async def test_unknown_path_under_api_prefix(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")

    assert_envelope(response, 404, "not_found")


async def test_method_not_allowed(client: AsyncClient) -> None:
    response = await client.delete("/api/v1/_test/items")

    assert_envelope(response, 405, "method_not_allowed")
    assert response.headers["Allow"]


async def test_validation_error_identifies_missing_field(client: AsyncClient) -> None:
    response = await client.post("/api/v1/_test/items", json={"quantity": 1})

    error = assert_envelope(response, 422, "validation_error")
    assert error["details"] == [
        {"location": ["body", "name"], "reason": "Field required", "type": "missing"}
    ]


async def test_validation_error_has_one_entry_per_field(client: AsyncClient) -> None:
    response = await client.post("/api/v1/_test/items", json={"quantity": "many"})

    error = assert_envelope(response, 422, "validation_error")
    locations = [d["location"] for d in error["details"]]  # type: ignore[attr-defined]
    assert locations == [["body", "name"], ["body", "quantity"]]


async def test_unhandled_exception_returns_generic_500(client: AsyncClient) -> None:
    response = await client.get("/api/v1/_test/boom")

    error = assert_envelope(response, 500, "internal_error")
    assert error["message"] == "An unexpected error occurred."
    assert error["details"] == []
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


async def test_domain_error_response(client: AsyncClient) -> None:
    response = await client.get("/api/v1/_test/missing")

    error = assert_envelope(response, 404, "not_found")
    assert error["message"] == "Item 42 does not exist."
    assert error["details"] == [{"id": 42}]


async def test_domain_error_default_message(client: AsyncClient) -> None:
    response = await client.get("/api/v1/_test/conflict")

    assert_envelope(response, 409, "conflict")


def test_error_responses_group_codes_by_status() -> None:
    responses = error_responses(NotAMemberError, HouseholdNotFoundError, OwnerRequiredError)

    assert list(responses) == [403, 404]
    assert responses[403]["model"] is ErrorResponse
    assert responses[403]["description"] == "Error codes: `not_a_member`, `owner_required`"
    assert responses[404]["description"] == "Error codes: `household_not_found`"

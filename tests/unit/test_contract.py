"""The generated OpenAPI document matches contracts/auth-and-households.md."""

from pathlib import Path
from typing import Any

import pytest

from lumior.contract import render_openapi
from lumior.main import create_app
from tests.conftest import make_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    return create_app(make_settings()).openapi()


def operation(document: dict[str, Any], method: str, path: str) -> dict[str, Any]:
    op: dict[str, Any] = document["paths"][path][method]
    return op


def documented_codes(op: dict[str, Any], status: int) -> str:
    description: str = op["responses"][str(status)]["description"]
    return description


@pytest.mark.parametrize(
    ("method", "path", "operation_id", "success", "errors"),
    [
        ("post", "/api/v1/auth/register", "auth_register", 201, {409: "email_taken", 422: ""}),
        ("post", "/api/v1/auth/login", "auth_login", 200, {401: "invalid_credentials"}),
        ("post", "/api/v1/auth/refresh", "auth_refresh", 200, {401: "invalid_refresh_token"}),
        ("post", "/api/v1/auth/logout", "auth_logout", 204, {}),
    ],
)
def test_auth_operations(
    document: dict[str, Any],
    method: str,
    path: str,
    operation_id: str,
    success: int,
    errors: dict[int, str],
) -> None:
    op = operation(document, method, path)

    assert op["operationId"] == operation_id
    assert str(success) in op["responses"]
    for status, code in errors.items():
        assert code in documented_codes(op, status)


@pytest.mark.parametrize("path", ["/api/v1/auth/refresh", "/api/v1/auth/logout"])
def test_cookie_endpoints_do_not_require_a_bearer_token(
    document: dict[str, Any], path: str
) -> None:
    assert "security" not in operation(document, "post", path)


@pytest.mark.parametrize(
    ("method", "path", "operation_id", "success", "errors"),
    [
        ("get", "/api/v1/me", "identity_get_me", 200, {401: "unauthorized"}),
        ("patch", "/api/v1/me", "identity_update_me", 200, {401: "unauthorized", 422: ""}),
        (
            "post",
            "/api/v1/me/password",
            "identity_change_password",
            204,
            {400: "invalid_current_password", 401: "unauthorized", 422: ""},
        ),
    ],
)
def test_identity_operations(
    document: dict[str, Any],
    method: str,
    path: str,
    operation_id: str,
    success: int,
    errors: dict[int, str],
) -> None:
    op = operation(document, method, path)

    assert op["operationId"] == operation_id
    assert str(success) in op["responses"]
    assert op["security"] == [{"HTTPBearer": []}]
    for status, code in errors.items():
        assert code in documented_codes(op, status)


# Every operation in contracts/auth-and-households.md section 3.
CONTRACT_OPERATIONS = {
    ("post", "/api/v1/auth/register"): "auth_register",
    ("post", "/api/v1/auth/login"): "auth_login",
    ("post", "/api/v1/auth/refresh"): "auth_refresh",
    ("post", "/api/v1/auth/logout"): "auth_logout",
    ("get", "/api/v1/me"): "identity_get_me",
    ("patch", "/api/v1/me"): "identity_update_me",
    ("post", "/api/v1/me/password"): "identity_change_password",
    ("get", "/api/v1/households"): "households_list",
    ("post", "/api/v1/households"): "households_create",
    ("patch", "/api/v1/households/{id}"): "households_update",
    ("get", "/api/v1/households/{id}/members"): "households_list_members",
    ("delete", "/api/v1/households/{id}/members/{user_id}"): "households_remove_member",
    ("post", "/api/v1/households/{id}/invites"): "households_create_invite",
    ("get", "/api/v1/invites/{code}"): "households_get_invite",
    ("post", "/api/v1/invites/{code}/accept"): "households_accept_invite",
}

CONTRACT_PREFIXES = ("/api/v1/auth", "/api/v1/me", "/api/v1/households", "/api/v1/invites")


def test_document_has_exactly_the_contract_operations(document: dict[str, Any]) -> None:
    operations = {
        (method, path): op["operationId"]
        for path, path_item in document["paths"].items()
        if path.startswith(CONTRACT_PREFIXES)
        for method, op in path_item.items()
    }

    assert operations == CONTRACT_OPERATIONS


@pytest.mark.parametrize(
    ("method", "path", "success", "errors"),
    [
        ("get", "/api/v1/households", 200, {401: "unauthorized"}),
        ("post", "/api/v1/households", 201, {401: "unauthorized", 422: ""}),
        (
            "patch",
            "/api/v1/households/{id}",
            200,
            {403: "owner_required", 404: "household_not_found", 422: ""},
        ),
        ("get", "/api/v1/households/{id}/members", 200, {403: "not_a_member"}),
        (
            "delete",
            "/api/v1/households/{id}/members/{user_id}",
            204,
            {403: "owner_required", 404: "member_not_found", 409: "owner_cannot_leave"},
        ),
        ("post", "/api/v1/households/{id}/invites", 201, {403: "not_a_member"}),
        (
            "get",
            "/api/v1/invites/{code}",
            200,
            {404: "invite_not_found", 410: "invite_expired"},
        ),
        (
            "post",
            "/api/v1/invites/{code}/accept",
            200,
            {409: "already_member", 410: "invite_used"},
        ),
    ],
)
def test_household_operations(
    document: dict[str, Any],
    method: str,
    path: str,
    success: int,
    errors: dict[int, str],
) -> None:
    op = operation(document, method, path)

    assert str(success) in op["responses"]
    assert op["security"] == [{"HTTPBearer": []}]
    for status, code in errors.items():
        assert code in documented_codes(op, status)


def test_household_id_path_parameter_is_a_string(document: dict[str, Any]) -> None:
    # A malformed id must reach the access check (404), not fail validation (422).
    params = operation(document, "get", "/api/v1/households/{id}/members")["parameters"]

    assert params == [
        {"name": "id", "in": "path", "required": True, "schema": {"type": "string", "title": "Id"}}
    ]


def test_committed_openapi_document_is_up_to_date() -> None:
    committed = (PROJECT_ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8")

    assert committed == render_openapi(), (
        "contracts/openapi.json is out of date. "
        "Run `uv run python scripts/export_openapi.py` and commit the result."
    )

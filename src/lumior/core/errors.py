"""Domain exceptions, the error envelope, and the handlers that map one to the other."""

import logging
from collections.abc import Mapping
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from lumior.core.request_id import get_request_id

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable snake_case error code.")
    message: str = Field(description="Human-readable description of the error.")
    details: list[dict[str, Any]] = Field(default_factory=list)
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


def error_responses(*errors: type["AppError"]) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses=` entries documenting the error codes a route can return."""
    codes: dict[int, list[str]] = {}
    for error in errors:
        codes.setdefault(error.status_code, []).append(f"`{error.code}`")
    return {
        status: {"model": ErrorResponse, "description": "Error codes: " + ", ".join(names)}
        for status, names in sorted(codes.items())
    }


class AppError(Exception):
    """Base class for errors that domain code raises and the API turns into responses."""

    status_code: ClassVar[int] = 400
    code: ClassVar[str] = "bad_request"
    default_message: ClassVar[str] = "The request could not be processed."

    def __init__(
        self, message: str | None = None, *, details: list[dict[str, Any]] | None = None
    ) -> None:
        self.message = message or self.default_message
        self.details = details or []
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "The request conflicts with the current state of the resource."


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"
    default_message = "The request contains invalid data."


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    default_message = "Authentication is required."


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "You do not have permission to perform this action."


# Auth and household errors from contracts/auth-and-households.md. The frontend branches on
# `code`. Later household-scoped modules reuse the household codes.


class InvalidCurrentPasswordError(AppError):
    status_code = 400
    code = "invalid_current_password"
    default_message = "The current password is incorrect."


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "invalid_credentials"
    default_message = "The email or password is incorrect."


class InvalidRefreshTokenError(AppError):
    status_code = 401
    code = "invalid_refresh_token"
    default_message = "The session has expired. Please sign in again."


class NotAMemberError(AppError):
    status_code = 403
    code = "not_a_member"
    default_message = "You are not a member of this household."


class OwnerRequiredError(AppError):
    status_code = 403
    code = "owner_required"
    default_message = "Only the household owner can do this."


class HouseholdNotFoundError(AppError):
    status_code = 404
    code = "household_not_found"
    default_message = "The household was not found."


class MemberNotFoundError(AppError):
    status_code = 404
    code = "member_not_found"
    default_message = "The member was not found in this household."


class InviteNotFoundError(AppError):
    status_code = 404
    code = "invite_not_found"
    default_message = "The invite was not found."


class EmailTakenError(AppError):
    status_code = 409
    code = "email_taken"
    default_message = "An account with this email already exists."


class OwnerCannotLeaveError(AppError):
    status_code = 409
    code = "owner_cannot_leave"
    default_message = "The household owner cannot leave or be removed."


class AlreadyMemberError(AppError):
    status_code = 409
    code = "already_member"
    default_message = "You are already a member of this household."


class InviteExpiredError(AppError):
    status_code = 410
    code = "invite_expired"
    default_message = "The invite has expired."


class InviteUsedError(AppError):
    status_code = 410
    code = "invite_used"
    default_message = "The invite has already been used."


HTTP_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    410: "gone",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_error",
    503: "service_unavailable",
}

INTERNAL_ERROR_MESSAGE = "An unexpected error occurred."


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, details=details or [], request_id=get_request_id()
        )
    )
    return JSONResponse(body.model_dump(), status_code=status_code, headers=headers)


async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = HTTP_STATUS_CODES.get(exc.status_code, "http_error")
    return error_response(exc.status_code, code, str(exc.detail), headers=exc.headers)


async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # The offending input is deliberately not echoed back.
    details = [
        {"location": list(err["loc"]), "reason": err["msg"], "type": err["type"]}
        for err in exc.errors()
    ]
    return error_response(422, "validation_error", ValidationError.default_message, details)


def register_exception_handlers(app: FastAPI) -> None:
    # Starlette types handlers as taking `Exception`; each handler is only called for its class.
    app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]


class UnhandledErrorMiddleware:
    """Turn unhandled exceptions into a generic 500 envelope and log them server-side.

    Starlette routes `Exception` handlers to its outermost middleware, which sits outside
    CORS and the request ID middleware. Catching here keeps both applied to 500 responses.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception(
                "Unhandled exception",
                extra={"method": scope.get("method"), "path": scope.get("path")},
            )
            if response_started:
                raise
            response = error_response(500, "internal_error", INTERNAL_ERROR_MESSAGE)
            await response(scope, receive, send)

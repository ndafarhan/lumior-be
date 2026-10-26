"""Request ID propagation: reuse or generate `X-Request-ID` and expose it via a context var."""

import re
import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[\x21-\x7e]{1,128}$")

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return _request_id.get()


def resolve_request_id(supplied: str | None) -> str:
    if supplied is not None and _VALID_REQUEST_ID.fullmatch(supplied):
        return supplied
    return uuid.uuid4().hex


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied: str | None = None
        for name, value in scope["headers"]:
            if name == b"x-request-id":
                supplied = value.decode("latin-1")
                break
        request_id = resolve_request_id(supplied)
        token = _request_id.set(request_id)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _request_id.reset(token)

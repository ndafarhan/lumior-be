"""Application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from lumior.api import health
from lumior.api.v1 import API_V1_PREFIX, api_router
from lumior.core.clock import system_clock
from lumior.core.config import Settings, get_settings
from lumior.core.db import create_engine, create_sessionmaker
from lumior.core.errors import UnhandledErrorMiddleware, register_exception_handlers
from lumior.core.logging import configure_logging
from lumior.core.request_id import REQUEST_ID_HEADER, RequestIDMiddleware


def generate_operation_id(route: APIRoute) -> str:
    """`<module>_<action>`: the router's first tag is the module, the route name the action."""
    if route.tags:
        return f"{route.tags[0]}_{route.name}"
    return route.name


# FastAPI documents a 422 with these schemas on every route that has parameters. Our 422s
# use the error envelope instead, and each route that can return one declares it.
FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")


def without_default_validation_responses(document: dict[str, Any]) -> dict[str, Any]:
    ref = "#/components/schemas/HTTPValidationError"
    for path_item in document["paths"].values():
        for operation in path_item.values():
            response = operation["responses"].get("422", {})
            if response.get("content", {}).get("application/json", {}).get("schema") == {
                "$ref": ref
            }:
                del operation["responses"]["422"]
    schemas = document.get("components", {}).get("schemas", {})
    for name in FASTAPI_VALIDATION_SCHEMAS:
        schemas.pop(name, None)
    return document


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    docs_enabled = not settings.is_production
    app = FastAPI(
        title="Lumior API",
        version="0.1.0",
        openapi_url=f"{API_V1_PREFIX}/openapi.json",
        docs_url=f"{API_V1_PREFIX}/docs" if docs_enabled else None,
        redoc_url=f"{API_V1_PREFIX}/redoc" if docs_enabled else None,
        generate_unique_id_function=generate_operation_id,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.clock = system_clock
    app.state.engine = create_engine(settings)
    app.state.sessionmaker = create_sessionmaker(app.state.engine)

    register_exception_handlers(app)
    # Added innermost first: RequestID -> CORS -> UnhandledError -> routes.
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestIDMiddleware)

    app.include_router(health.router)
    app.include_router(api_router)

    build_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = without_default_validation_responses(build_openapi())
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn lumior.main:app` builds the app on first access, so importing this module
    # (for example in tests) does not require a configured environment.
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

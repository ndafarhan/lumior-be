from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from lumior.main import create_app
from tests.conftest import make_settings

pantry = APIRouter(prefix="/api/v1/_test/pantry", tags=["pantry"])
cellar = APIRouter(prefix="/api/v1/_test/cellar", tags=["cellar"])


@pantry.get("")
async def list_items() -> list[str]:
    return []


@pantry.post("")
async def create_item() -> None:
    return None


@cellar.get("")
async def list_bottles() -> list[str]:
    return []


async def fetch(environment: str, path: str) -> tuple[int, dict[str, object] | None]:
    app = create_app(make_settings(environment=environment))
    app.include_router(pantry)
    app.include_router(cellar)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)
    await app.state.engine.dispose()
    is_json = response.headers.get("content-type") == "application/json"
    return response.status_code, response.json() if is_json else None


async def test_operation_ids_are_module_action_and_unique() -> None:
    status, document = await fetch("development", "/api/v1/openapi.json")

    assert status == 200
    assert document is not None
    operation_ids = [
        operation["operationId"]
        for path_item in document["paths"].values()  # type: ignore[attr-defined]
        for operation in path_item.values()
    ]
    test_operation_ids = [
        operation["operationId"]
        for path, path_item in document["paths"].items()  # type: ignore[attr-defined]
        if path.startswith("/api/v1/_test/")
        for operation in path_item.values()
    ]
    assert sorted(test_operation_ids) == [
        "cellar_list_bottles",
        "pantry_create_item",
        "pantry_list_items",
    ]
    assert len(operation_ids) == len(set(operation_ids))


async def test_health_endpoints_are_not_in_the_document() -> None:
    _, document = await fetch("development", "/api/v1/openapi.json")

    assert document is not None
    assert not any(path.startswith("/health") for path in document["paths"])  # type: ignore[attr-defined]


async def test_docs_ui_available_in_development() -> None:
    status, _ = await fetch("development", "/api/v1/docs")

    assert status == 200


async def test_docs_ui_disabled_in_production() -> None:
    docs_status, _ = await fetch("production", "/api/v1/docs")
    redoc_status, _ = await fetch("production", "/api/v1/redoc")

    assert docs_status == 404
    assert redoc_status == 404


async def test_openapi_document_still_served_in_production() -> None:
    status, document = await fetch("production", "/api/v1/openapi.json")

    assert status == 200
    assert document is not None

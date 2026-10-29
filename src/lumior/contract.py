"""Render the OpenAPI document that is committed as `contracts/openapi.json` for the frontend."""

import json

from lumior.core.config import Settings
from lumior.main import create_app

# Never connected to; the app factory only needs a URL to build its engine.
_UNUSED_DATABASE_URL = "postgresql+asyncpg://unused@localhost/unused"


def render_openapi() -> str:
    settings = Settings(_env_file=None, database_url=_UNUSED_DATABASE_URL)
    document = create_app(settings).openapi()
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

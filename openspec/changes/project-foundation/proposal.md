# Proposal

## Why

Lumior is a household budgeting and grocery price optimization app, and this repository (`lumior-be`) is its backend. The repository is currently empty. Every planned MVP capability needs the same groundwork: an application skeleton, configuration, database access, migrations, and API conventions that a separate frontend client can rely on. Setting these up once, before any feature work, keeps the later MVP changes small and consistent.

The planned MVP sequence this change unblocks:

1. `project-foundation` (this change)
2. `auth-and-households`
3. `budgets-and-expenses` and `catalog-stores-prices` (in parallel)
4. `shopping-lists` (including "complete trip", which records an expense and price observations)
5. `basket-optimization`

## What Changes

- Create a Python FastAPI service with a modular-monolith layout (`src/lumior/core`, `src/lumior/api`, `src/lumior/modules/*`).
- Add environment-based configuration (database URL, CORS origins, environment name, secrets).
- Add async PostgreSQL access (SQLAlchemy 2.x + asyncpg) and Alembic migrations, with an initial empty baseline.
- Expose liveness and readiness health endpoints; readiness checks database connectivity.
- Establish API conventions for all future modules: `/api/v1` versioned routing, a single JSON error format, configurable CORS for a separate frontend, and a published OpenAPI document for client generation.
- Add shared building blocks needed by every later module: money handling with `Decimal` (no floats) and a base-unit model for quantities.
- Add developer tooling: dependency management with uv, local PostgreSQL via docker-compose, ruff, mypy, pytest with integration tests against a real PostgreSQL, and a CI pipeline running them.

No product features (auth, households, budgets, prices, lists, optimization) are part of this change.

## Capabilities

### New Capabilities

- `service-health`: Liveness and readiness reporting for the backend service, including database connectivity status.
- `api-conventions`: Contract every API endpoint follows: versioned base path, uniform error response format, CORS policy for allowed frontend origins, and the published OpenAPI document.

### Modified Capabilities

None. No specs exist yet.

## Impact

- **Code**: New project skeleton under `src/lumior/`, `alembic/`, `tests/`; new `pyproject.toml`, `docker-compose.yml`, CI workflow.
- **Dependencies**: FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2.x (async), asyncpg, Alembic, Uvicorn; dev: pytest, httpx, testcontainers, ruff, mypy.
- **Systems**: Requires a PostgreSQL instance per environment.
- **Clients**: The frontend lives in a separate repository and integrates through `/api/v1` and the OpenAPI document. Its type (web, mobile, or both) is still undecided. That decision affects token handling in `auth-and-households`, not this change.

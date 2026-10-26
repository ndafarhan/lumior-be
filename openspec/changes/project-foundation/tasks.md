# Tasks

## 1. Project scaffolding and tooling

- [x] 1.1 Initialize the project with uv: `pyproject.toml` (package `lumior`, src layout), `.python-version` pinned to 3.12 (system Python is 3.9, so uv manages the interpreter), and `uv.lock`; verify `uv sync` succeeds and `uv run python -c "import lumior"` works
- [x] 1.2 Add runtime dependencies (fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy[asyncio], asyncpg, alembic) and dev dependencies (pytest, pytest-asyncio, httpx, testcontainers[postgres], ruff, mypy); verify `uv sync` resolves and the lockfile is committed
- [x] 1.3 Create the package layout `src/lumior/{core,api,modules}/` with `__init__.py` files and an empty `tests/{unit,integration}/` tree; verify the tree matches design.md Decision 1
- [x] 1.4 Configure ruff (lint + format) and mypy strict for `src/` in `pyproject.toml`; verify `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy src` pass on the skeleton
- [x] 1.5 Add `docker-compose.yml` with PostgreSQL 16 (named volume, healthcheck) and `.env.example`; add `.gitignore` for `.env`, `.venv`, caches; verify `docker compose up -d` brings the database to healthy

## 2. Configuration and application factory

- [x] 2.1 Implement `core/config` `Settings` (ENVIRONMENT, DATABASE_URL, CORS_ALLOWED_ORIGINS, LOG_LEVEL, SECRET_KEY) loaded from env/`.env` with validation; add unit tests verifying that defaults load, a missing DATABASE_URL fails at startup, and comma-separated origins are parsed into a list
- [x] 2.2 Implement `main.create_app(settings)` mounting an empty `/api/v1` router from `api/` and setting the OpenAPI URL to `/api/v1/openapi.json`; verify `uv run uvicorn lumior.main:app` starts and `GET /api/v1/openapi.json` returns 200
- [x] 2.3 Add a pytest fixture that builds the app with test settings and an httpx `AsyncClient`; verify a trivial test using the client passes

## 3. Database access and migrations

- [x] 3.1 Implement `core/db`: async engine created from settings, `AsyncSession` per-request dependency that commits on success and rolls back on error, declarative `Base` with constraint naming convention and `lazy="raise"` default; add unit tests verifying commit-on-success and rollback-on-exception behavior of the dependency
- [x] 3.2 Set up Alembic (async env using `Base.metadata` and `DATABASE_URL` from settings) with a baseline migration that only runs `CREATE EXTENSION IF NOT EXISTS pg_trgm`; verify `uv run alembic upgrade head` and `alembic downgrade base` both succeed against the docker-compose database
- [x] 3.3 Add integration test fixtures: a session-scoped testcontainers PostgreSQL, migrations applied once, each test wrapped in a rolled-back transaction; add a test verifying `pg_trgm` is installed after migration

## 4. Error handling and request ID (api-conventions)

- [x] 4.1 Implement `core/errors`: typed domain exceptions (`NotFoundError`, `ConflictError`, `ValidationError`, ...) and the error envelope schema with codes from specs/api-conventions; verify with unit tests that each exception maps to the expected status code and `code`
- [x] 4.2 Implement request ID middleware (reuse a valid 1–128 visible-ASCII `X-Request-ID`, otherwise generate) storing the ID in a context variable; add tests covering the supplied, missing, and too-long header scenarios from specs/api-conventions
- [x] 4.3 Register exception handlers for domain errors, HTTP 404/405, request validation (422 with per-field `details`), and unhandled exceptions (500 `internal_error`, no exception text); add API tests for every error scenario in specs/api-conventions, using test-only routes to trigger validation and unhandled errors
- [x] 4.4 Configure structured logging (JSON in non-development environments) including `request_id` on every log line, and log unhandled exceptions with stack traces server-side only; verify by a test that captures logs for a 500 and finds the request ID and traceback in the log but not in the response

## 5. CORS and OpenAPI (api-conventions)

- [x] 5.1 Add CORS middleware using `CORS_ALLOWED_ORIGINS` with credentials allowed and no wildcard; add tests for preflight from an allowed origin and a request from a disallowed origin per specs/api-conventions
- [x] 5.2 Configure stable `operationId` generation (`<module>_<action>` from route names) and disable the docs UI when ENVIRONMENT is production; add tests verifying unique operationIds in the generated document and docs UI 200 in development vs 404 in production

## 6. Health endpoints (service-health)

- [x] 6.1 Implement `GET /health/live` returning `{"status": "ok"}` with no dependency checks; add tests verifying 200 with and without a reachable database
- [x] 6.2 Implement `GET /health/ready` running `SELECT 1` with a 2-second timeout and returning 200/503 with `checks.database`, without leaking error details; add integration tests for reachable, unreachable (bad DATABASE_URL), and timeout scenarios from specs/service-health

## 7. Shared money and unit primitives

- [x] 7.1 Implement `core/money`: `Money` (Decimal amount + ISO 4217 currency), currency precision table, half-up rounding, and a Pydantic type that serializes amounts as decimal strings and rejects JSON numbers; add unit tests for rounding, precision lookup, string serialization, and number rejection (422 via a test-only route) per specs/api-conventions
- [x] 7.2 Implement `core/units`: base units `g`, `ml`, `piece` and conversions from `kg`, `l`, and other common units, rejecting cross-dimension conversions; add unit tests for each conversion and the rejection case

## 8. CI and documentation

- [x] 8.1 Add a GitHub Actions workflow running `uv sync`, ruff check, ruff format check, mypy, and pytest (unit + integration with Docker) on push and pull request; verify the workflow passes on a pushed branch
- [x] 8.2 Write `README.md` covering the project purpose, local setup (`uv sync`, `docker compose up -d`, `alembic upgrade head`, run server), running tests, module layout, and the layering rule `router -> service -> repository`; verify by following the README from a clean clone to a passing `/health/ready`

## 9. Integration check

- [x] 9.1 Run the full suite (`uv run pytest`) plus lint and type checks locally and confirm all pass; start the app against docker-compose PostgreSQL and verify by hand `/health/live`, `/health/ready`, `/api/v1/openapi.json`, and a 404 under `/api/v1` with the error envelope and `X-Request-ID`
- [x] 9.2 Run `openspec validate project-foundation --strict` and confirm it passes

## Workflow follow-up

- Archive the change with `/opsx:archive` after review, which creates `openspec/specs/service-health` and `openspec/specs/api-conventions`.
- Next change: `auth-and-households`.

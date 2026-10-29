# lumior-be

Backend for Lumior, a household budgeting and grocery price optimization app. It is a FastAPI
service backed by PostgreSQL. The frontend lives in a separate repository and integrates through
the versioned HTTP API under `/api/v1` and its OpenAPI document.

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs and manages Python 3.12 for you)
- Docker (for the local database and the integration tests)

## Local setup

```bash
uv sync                      # create .venv with Python 3.12 and install dependencies
cp .env.example .env         # local configuration
docker compose up -d         # PostgreSQL 16 on localhost:5433
uv run alembic upgrade head  # apply migrations
uv run uvicorn lumior.main:app --reload
```

Then check:

- `GET http://localhost:8000/health/live` returns `{"status": "ok"}`
- `GET http://localhost:8000/health/ready` returns `{"status": "ok", "checks": {"database": "ok"}}`
- API docs: <http://localhost:8000/api/v1/docs> (not served in production)
- OpenAPI document: <http://localhost:8000/api/v1/openapi.json>

The compose database listens on host port 5433 so it does not clash with a natively installed
PostgreSQL. Change `POSTGRES_PORT` and `DATABASE_URL` in `.env` together if you need another port.

### Configuration

All settings come from environment variables (or `.env`) and are validated at startup.

| Variable                   | Default          | Notes                                                         |
| -------------------------- | ---------------- | ------------------------------------------------------------- |
| `DATABASE_URL`             | (required)       | `postgresql+asyncpg://user:pass@host:port/db`                 |
| `ENVIRONMENT`              | `development`    | `development`, `test`, `staging`, or `production`             |
| `CORS_ALLOWED_ORIGINS`     | empty            | Comma-separated origins; `*` is rejected                      |
| `LOG_LEVEL`                | `INFO`           | Logs are JSON outside `development`                           |
| `SECRET_KEY`               | `change-me`      | Signs access tokens; ≥32 chars required in staging/production |
| `ACCESS_TOKEN_TTL_SECONDS` | `900`            | Access token lifetime                                         |
| `REFRESH_TOKEN_TTL_DAYS`   | `30`             | Refresh cookie lifetime, renewed on every refresh             |
| `REFRESH_GRACE_SECONDS`    | `30`             | How long a just-rotated refresh token is still accepted       |
| `INVITE_TTL_DAYS`          | `7`              | Household invite lifetime                                     |
| `REFRESH_COOKIE_NAME`      | `lumior_refresh` | Name of the refresh token cookie                              |

## Tests and checks

```bash
uv run pytest                   # everything
uv run pytest tests/unit        # fast, no I/O
uv run pytest tests/integration # starts a throwaway PostgreSQL container (needs Docker)
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Integration tests start PostgreSQL with testcontainers, apply migrations once per session, and wrap
each test in a transaction that is rolled back. Use the `db_session` fixture for database access
and the `client` fixture for API calls against the real database.

CI (`.github/workflows/ci.yml`) runs the same checks on every push and pull request.

## Layout

```
src/lumior/
  main.py          app factory: create_app(settings)
  core/            config, db, errors, logging, request_id, clock, validation, money, units
  api/             /api/v1 router aggregation (v1.py), shared dependencies (deps.py), health
  modules/<name>/  models.py, schemas.py, repository.py, service.py, router.py
alembic/           migrations
tests/unit/        tests without I/O
tests/integration/ tests against real PostgreSQL
```

### Layering rule

```
router -> service -> repository -> models
```

- **Routers** handle HTTP only: path operations, Pydantic schemas, dependencies. Tag each module
  router with the module name; operation IDs become `<module>_<function name>`.
- **Services** hold business rules and never import FastAPI. They raise exceptions from
  `lumior.core.errors` (`NotFoundError`, `ConflictError`, ...), which become the standard error
  response.
- **Repositories** are the only place that queries the database. Load relationships explicitly
  (`selectinload`): relationships default to `lazy="raise"` (use `lumior.core.db.relationship`).
- Modules talk to each other through services, never through another module's repository or
  models.
- One session per request (`SessionDep`), committed when the request succeeds and rolled back on
  error. Services do not commit.

### API conventions

- Business routes live under `/api/v1`; register module routers in `src/lumior/api/v1.py`.
- Every non-2xx response has the body
  `{"error": {"code", "message", "details", "request_id"}}`.
- Every response carries `X-Request-ID` (echoed if the client sent a valid one), and the same ID
  appears in logs and error bodies.
- Money is `Decimal`, never float. In JSON it is a string plus currency:
  `{"amount": "12500.00", "currency": "IDR"}` (`lumior.core.money.Money`).
- Quantities are stored in base units `g`, `ml`, or `piece` (`lumior.core.units`).

### Authentication

The contract with the frontend is `contracts/auth-and-households.md` (machine-readable:
`contracts/openapi.json`).

- Authenticated routes take `CurrentUser` (or `CurrentSession` when the sign-in session is
  needed) from `lumior.api.deps`. A missing, invalid, or expired `Authorization: Bearer` token
  is 401 `unauthorized`, raised before the route does anything.
- Access tokens are short-lived JWTs. Refresh tokens are random, stored hashed, sent only as an
  `HttpOnly` cookie on `Path=/api/v1/auth`, and rotated on every refresh.
- Use `ClockDep` (`lumior.core.clock`) instead of `datetime.now()` in routes, and pass `now` to
  services. Integration tests replace the clock with `FakeClock` to test expiry.

### Household-scoped routes

Every route under `/households/{id}/...` (and every later module scoped to a household, such as
budgets or lists) must use one of these dependencies from `lumior.api.deps`:

- `HouseholdAccess`: the caller is a member. Otherwise 404 `household_not_found` (unknown or
  malformed id) or 403 `not_a_member`.
- `OwnerAccess`: as above, and the caller is the owner. Otherwise 403 `owner_required`.

Reuse these three error codes: the frontend treats `household_not_found` / `not_a_member` as
"access lost" (it switches household) and `owner_required` as a permission message. Dependencies
run before body validation, so these checks always come before a 422.

Exception to the layering rule: the households repository joins `users` read-only to show
member and inviter names. It never writes to identity's tables.

### Migrations

```bash
uv run alembic revision --autogenerate -m "add households"
uv run alembic upgrade head
```

Autogenerate compares the database with `lumior.core.db.Base.metadata`, so add an import of each
new module's `models` to `alembic/env.py`.

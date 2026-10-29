# Design

## Context

See proposal.md - Why. The contract in `contracts/auth-and-households.md` is the source of truth for paths, `operationId`s, shapes, status codes, and error codes; the specs in this change restate it as testable requirements.

Relevant current state (from `project-foundation`):

- `create_app(settings)` builds the app. `operationId` is generated as `<first tag>_<route name>` (`main.generate_operation_id`).
- `core/errors.AppError` subclasses carry `status_code` + `code`, and one handler maps them to the envelope. Validation errors already produce `{"location", "reason", "type"}` details.
- `SessionDep` gives one `AsyncSession` per request that commits at the request boundary. Services never commit.
- `core/db.relationship` defaults to `lazy="raise"`. Alembic uses `Base.metadata` with a naming convention.
- `Settings.secret_key` exists as a placeholder (`"change-me"`).
- CORS already allows credentials, echoes request headers, and rejects `*`.
- Integration tests run against PostgreSQL in testcontainers; each test runs inside one rolled-back transaction, so `now()` in SQL is the same for the whole test.

## Goals / Non-Goals

**Goals:**
- Match the contract byte-for-byte where the frontend can observe it (paths, `operationId`s, field names, codes, cookie attributes).
- Make the household access check a single reusable dependency, so later modules get `household_not_found` / `not_a_member` / `owner_required` for free.
- Make time controllable in tests (token expiry, grace window, invite expiry).

**Non-Goals:**
- Refresh-token reuse detection (revoking a whole session when an old token is replayed after the grace window). Can be added later without changing the contract.
- Revoking already-issued access tokens. They live at most 15 minutes.
- Rate limiting / brute-force protection on login (separate change).
- Cross-site deployment (`SameSite=None` + CSRF), see contract §8.

## Decisions

### 1. Two modules: `identity` and `households`

```
src/lumior/modules/
  identity/     models (User, RefreshToken), schemas, repository, service,
                tokens.py (access token encode/decode, refresh token gen/hash),
                passwords.py (hashing), router.py (auth_router, me_router)
  households/   models (Household, HouseholdMember, HouseholdInvite), schemas,
                repository, service, router.py (households_router, invites_router)
src/lumior/api/deps.py   CurrentUser, CurrentSession, HouseholdAccess dependencies
src/lumior/core/clock.py Clock + get_clock dependency
```

Tags drive `operationId`: `auth` (register/login/refresh/logout), `identity` (get_me/update_me/change_password), `households` (list/create/update/list_members/remove_member/create_invite/get_invite/accept_invite). The `/invites` router also uses the `households` tag because the contract names them `households_get_invite` / `households_accept_invite`. Route names are set explicitly with `name=` (e.g. `name="list"`) so the Python function names can differ.

Households never writes to identity's tables. It reads member names/emails and the inviter's name by joining `users` in its own repository queries (one query instead of N service calls). This read-only join is an accepted exception to the "modules talk through services" rule and is noted in the README.

*Alternative:* one `auth` module containing everything. Rejected: households is the tenancy boundary every later module depends on, and should not drag in auth internals.

### 2. Access token: signed JWT (HS256, `SECRET_KEY`)

Claims: `sub` (user id), `sid` (sign-in session id), `iat`, `exp`, `typ: "access"`. Lifetime from settings (default 900 s). The frontend treats it as opaque, so the format can change later.

Verification is done in the `CurrentUser` dependency: parse `Authorization: Bearer`, verify signature, check `exp` against the injected clock (not wall time), then load the user. Any failure raises `UnauthorizedError` (401 `unauthorized`). FastAPI's `HTTPBearer` is used only with `auto_error=False` so it appears in OpenAPI as a security scheme, but never emits its own 403.

The `sid` claim exists because the refresh cookie (`Path=/api/v1/auth`) is **not** sent to `POST /api/v1/me/password`; the password change identifies "the session it was made from" through `sid`.

*Alternative:* opaque random access tokens looked up in the DB. Simpler revocation but adds a table and a lookup per request; with a 15-minute lifetime, JWT is enough. Library: `PyJWT`.

### 3. Refresh tokens: random, hashed, grouped by session

Table `refresh_tokens`: `id`, `user_id` FK, `session_id` (UUID, one per login/register), `token_hash` (SHA-256 hex, unique), `created_at`, `expires_at`, `replaced_at` (nullable), `revoked_at` (nullable).

- Token value: `secrets.token_urlsafe(32)`. Only the hash is stored.
- **Issue** (register/login): new `session_id`, new row, `expires_at = now + 30 d`.
- **Refresh**: `SELECT ... FOR UPDATE` the row by hash. Reject (401 `invalid_refresh_token`) if missing, revoked, expired, or `replaced_at` older than the grace window. Otherwise, if it was not yet replaced, set `replaced_at = now`. In both cases insert a new token in the same `session_id` with `expires_at = now + 30 d` (sliding) and return a new `Session` + cookie. The row lock serializes two tabs refreshing with the same cookie; the second one sees `replaced_at` within the grace window and still succeeds.
- **Logout**: revoke every non-revoked token of that `session_id` (a grace-window sibling may exist), always 204, clear cookie.
- **Password change**: revoke all of the user's tokens where `session_id != sid`.

Cookie set via `Response.set_cookie(name, value, max_age, path="/api/v1/auth", httponly=True, samesite="lax", secure=...)`; cleared with `delete_cookie` using the same path/flags. `secure` is false only for `ENVIRONMENT` in `{development, test}`: `test` is needed because the integration test client talks plain `http://test`, and is never a deployed environment.

*Alternative:* storing the refresh token as a JWT. Rejected: revocation and rotation need server state anyway.

### 4. Passwords: Argon2id via `argon2-cffi`

Default `PasswordHasher` parameters. Hashing/verification runs in a worker thread (`anyio.to_thread.run_sync`) so it does not block the event loop. For an unknown email, login still verifies against a fixed dummy hash, so response time does not reveal whether the email exists. If `check_needs_rehash` is true after a successful login, the hash is updated.

Validation limits are enforced in Pydantic schemas: names use `StringConstraints(strip_whitespace=True, min_length=1, max_length=100)`; passwords `min_length=8, max_length=128` (no stripping); email uses `EmailStr` (adds `email-validator`) and is lower-cased before storage and lookup. The `users.email` column has a unique constraint; register catches the `IntegrityError` from a concurrent duplicate (after `flush`) and maps it to `email_taken`.

### 5. Household access as a dependency, evaluated before the body

`HouseholdAccess` depends on `CurrentUser`, reads `id` from the path **as a string**, and:
1. parses it as UUID → failure is `household_not_found` (a FastAPI `UUID` path type would return 422, which the contract does not allow);
2. loads the household → missing is `household_not_found`;
3. loads the caller's membership → missing is `not_a_member`;
4. returns `(household, membership)`.

`OwnerAccess` wraps it and raises `owner_required` when `role != "owner"`. FastAPI resolves dependencies before validating the body, so 401 → 404/403 → 422 is the natural order. Tests pin this order (spec: "Non-member sends an invalid body"). Later household-scoped modules reuse these dependencies.

`remove_member` uses `HouseholdAccess` (not `OwnerAccess`) because members may remove themselves. Order inside the service: self-target → owner gets `owner_cannot_leave`, member is removed; other target → non-owner gets `owner_required`; then parse/lookup target → `member_not_found`.

### 6. Household data model

- `households`: `id` UUID PK, `name`, `created_at`.
- `household_members`: PK `(household_id, user_id)`, `role` text with `CHECK (role IN ('owner','member'))`, `joined_at`. A partial unique index on `household_id WHERE role = 'owner'` guarantees one owner.
- `household_invites`: `id`, `household_id` FK, `code` unique, `created_by` FK users, `created_at`, `expires_at`, `used_at`, `used_by`.

`member_count` is computed with a count subquery in the repository queries that return households. Lists order by `joined_at, household_id` (members: `joined_at, user_id`) for a stable order.

All UUIDs are generated in Python (`uuid4`), so no extension is needed.

### 7. Invites

Code: `secrets.token_urlsafe(16)` (22 URL-safe characters, 128 bits). Stored in plain text because preview must look it up and the code is single-use and short-lived. TTL 7 days (setting). Accept runs in one transaction: `SELECT ... FOR UPDATE` the invite → `invite_not_found` / `invite_used` / `invite_expired` (used checked before expired) → if the caller is already a member, raise `already_member` without touching the invite → insert membership as `member`, set `used_at`/`used_by`. The row lock makes concurrent accepts serialize; the loser sees `used_at` and gets `invite_used`. The membership PK is a second guard.

### 8. Time via an injectable clock

`core/clock.py` defines `Clock` (a callable returning an aware UTC `datetime`) and `get_clock` reading `app.state.clock` (default system clock). Services receive `now` from the router instead of calling `datetime.now()` or SQL `now()`. Tests replace `app.state.clock` with a controllable clock to cross the 15-minute, 30-second, 30-day, and 7-day boundaries. This also fixes ordering tests, because SQL `now()` is constant inside the test transaction.

### 9. Errors

New `AppError` subclasses in `core/errors.py` (shared, since later modules reuse the household codes): `InvalidCredentialsError` (401), `InvalidRefreshTokenError` (401), `InvalidCurrentPasswordError` (400), `EmailTakenError` (409), `HouseholdNotFoundError` (404), `NotAMemberError` (403), `OwnerRequiredError` (403), `MemberNotFoundError` (404), `OwnerCannotLeaveError` (409), `AlreadyMemberError` (409), `InviteNotFoundError` (404), `InviteExpiredError` (410), `InviteUsedError` (410). Routes declare their error responses with `responses={...: {"model": ErrorResponse}}` so the OpenAPI document lists them for the frontend's generated client. `410` is added to `HTTP_STATUS_CODES`.

### 10. Settings

New fields: `access_token_ttl_seconds=900`, `refresh_token_ttl_days=30`, `refresh_grace_seconds=30`, `invite_ttl_days=7`, `refresh_cookie_name="lumior_refresh"`. `secret_key` validation: in `staging`/`production` it must not be the placeholder and must be at least 32 characters, so a misconfigured deploy fails at startup.

### 11. Contract artifacts and drift guard

A small script (`scripts/export_openapi.py`) writes `app.openapi()` to `contracts/openapi.json` (sorted keys, trailing newline). A unit test checks (a) every `(method, path, operationId)` from the contract table is present and (b) the committed `contracts/openapi.json` equals the generated document, so the backend cannot drift from what the frontend consumes without a visible diff.

## Risks / Trade-offs

- [Access tokens of other sessions stay valid up to 15 minutes after a password change or logout] → short lifetime; accepted by the contract, which only requires revoking refresh tokens.
- [A stolen refresh cookie can be used until rotation by the legitimate client] → `HttpOnly` + `SameSite=Lax` + short grace window; reuse detection listed as a follow-up.
- [Argon2 is CPU-heavy, so login/register are slower and can be abused] → offloaded to threads; rate limiting is a follow-up change.
- [Grace window leaves two valid tokens in a session for a moment] → both belong to the same `session_id`, so logout and password change still revoke them together.
- [Plain-text invite codes in the DB] → codes are single-use, expire in 7 days, and only grant `member`; hashing can be added later without API change.
- [Dependency-before-body ordering is a FastAPI behavior, not a guarantee in our code] → pinned by integration tests.
- [`contracts/openapi.json` drift test fails on any API change] → intentional; regenerate with the script and let the frontend see the diff.

## Migration Plan

1. One Alembic revision creating `users`, `refresh_tokens`, `households`, `household_members`, `household_invites` with indexes and constraints. No data to migrate.
2. Set `SECRET_KEY` (≥32 chars) in every non-development environment before deploying; the app refuses to start otherwise.
3. Ensure the frontend origin is in `CORS_ALLOWED_ORIGINS` and the frontend and API are on the same site.

Rollback: revert the commit and `alembic downgrade -1` (drops the new tables; only auth data is lost).

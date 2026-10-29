# Tasks

## 1. Dependencies, settings, clock, and errors

- [x] 1.1 Add runtime dependencies `pyjwt`, `argon2-cffi`, and `email-validator` with `uv add`; verify `uv sync` resolves and `uv.lock` is updated
- [x] 1.2 Add settings `access_token_ttl_seconds`, `refresh_token_ttl_days`, `refresh_grace_seconds`, `invite_ttl_days`, `refresh_cookie_name` and the `secret_key` rule for `staging`/`production` (not the placeholder, ≥32 chars) per design Decision 10; update `.env.example`; verify with unit tests in `tests/unit/test_config.py` (defaults, production with placeholder fails, development with placeholder loads)
- [x] 1.3 Implement `core/clock.py` (`Clock`, system clock on `app.state.clock`, `get_clock` dependency) per design Decision 8; verify with a unit test that a replaced clock is returned by the dependency
- [x] 1.4 Add the 13 error classes from design Decision 9 to `core/errors.py` and `410` to `HTTP_STATUS_CODES`; verify with unit tests in `tests/unit/test_errors.py` that each maps to the contract's status and `code` (contract §7)
- [x] 1.5 Add integration test helpers in `tests/integration/conftest.py`: a controllable clock installed on the app, and helpers to register a user and return its access token and cookie-carrying client; verify a smoke test using them passes

## 2. Identity data model and token primitives

- [x] 2.1 Create `modules/identity/models.py` (`User` with lower-cased unique `email`, `RefreshToken` per design Decision 3) and an Alembic revision for `users` and `refresh_tokens`; verify `uv run alembic upgrade head` and `downgrade -1` succeed on the docker-compose DB and the integration suite still passes
- [x] 2.2 Implement `modules/identity/passwords.py` (Argon2id hash/verify off the event loop, dummy-hash verify for unknown users, rehash check) per design Decision 4; verify with unit tests (correct/incorrect password, rehash flag)
- [x] 2.3 Implement `modules/identity/tokens.py`: access-token encode/decode with `sub`, `sid`, `iat`, `exp`, `typ` and clock-based expiry; refresh token generation and SHA-256 hashing; verify with unit tests (round trip, expired, wrong signature, wrong `typ`, tampered payload)

## 3. Authentication endpoints (specs/user-auth)

- [x] 3.1 Implement identity schemas (`User`, `Session`, register/login bodies with the contract §4 limits) and the repository/service for register and login, including `email_taken` from a unique-constraint race and identical `invalid_credentials` for unknown email and wrong password; verify with integration tests for every register/login scenario and the password-limit scenarios in specs/user-auth
- [x] 3.2 Implement `api/deps.py` `CurrentUser` / `CurrentSession` (Bearer parsing, `HTTPBearer(auto_error=False)` for OpenAPI, 401 `unauthorized` for every failure, user must exist) per design Decision 2; verify with integration tests for missing, malformed, expired, and deleted-user tokens
- [x] 3.3 Implement the refresh cookie helpers (set/clear, `Secure` except `development`/`test`) and `POST /auth/register` + `POST /auth/login` setting the cookie; verify with tests asserting the exact `Set-Cookie` attributes in `production` and `development` settings
- [x] 3.4 Implement `POST /auth/refresh` with row-locked rotation, sliding expiry, and the 30-second grace window per design Decision 3; verify with integration tests for success without `Authorization`, missing/unknown/expired/revoked cookies, reuse within the grace window, and reuse after it (using the controllable clock)
- [x] 3.5 Implement `POST /auth/logout` (revoke the whole session, clear cookie with the same path, always 204); verify with integration tests for valid, missing, and invalid cookies and that refresh afterwards returns `invalid_refresh_token`
- [x] 3.6 Register `auth_router` in `api/v1.py` with tag `auth` and explicit route names; verify `tests/unit/test_openapi.py` finds `auth_register`, `auth_login`, `auth_refresh`, `auth_logout` with their documented error responses

## 4. Current user endpoints (specs/user-account)

- [x] 4.1 Implement `GET /me` and `PATCH /me` (trimmed name, 1–100) under tag `identity`; verify with integration tests for read, rename, blank and too-long names, and 401 without a token
- [x] 4.2 Implement `POST /me/password`: 400 `invalid_current_password`, 422 for `new_password` limits, 204 on success, revoke refresh tokens of other sessions using the access token's `sid`; verify with integration tests that the calling session can still refresh, a second session cannot, and only the new password logs in
- [x] 4.3 Verify `identity_get_me`, `identity_update_me`, `identity_change_password` appear in `/api/v1/openapi.json` via the OpenAPI unit test

## 5. Households and membership (specs/households)

- [x] 5.1 Create `modules/households/models.py` (`Household`, `HouseholdMember` with role check and one-owner partial unique index, `HouseholdInvite`) and an Alembic revision for the three tables; verify upgrade/downgrade on the docker-compose DB and that inserting a second owner fails in an integration test
- [x] 5.2 Implement the households repository/service: list ordered by `joined_at` with `member_count` and caller `role`, create (caller becomes owner), rename, list members ordered by join time; verify with integration tests for the list, create, and rename scenarios
- [x] 5.3 Implement `HouseholdAccess` and `OwnerAccess` dependencies in `api/deps.py` (path id parsed as string, malformed → `household_not_found`) per design Decision 5; verify with integration tests for unknown id, malformed id, non-member, member on owner-only route, and that a non-member with an invalid body gets 403 not 422
- [x] 5.4 Implement the households router (`households_list`, `households_create`, `households_update`, `households_list_members`, `households_remove_member`) including the remove/leave rules (`owner_cannot_leave`, `owner_required`, `member_not_found`); verify with integration tests for every scenario in specs/households
- [x] 5.5 Document the household access dependencies and the error-code reuse rule for later modules in `README.md`, plus the read-only `users` join exception from design Decision 1; verify the README section names `HouseholdAccess`, `OwnerAccess`, and the three codes

## 6. Invites (specs/household-invites)

- [x] 6.1 Implement `POST /households/{id}/invites` (owner only, `token_urlsafe(16)` code, `expires_at` now + 7 days in UTC); verify with integration tests for owner success, member `owner_required`, two distinct codes, and the UTC `Z`-style timestamp in the response
- [x] 6.2 Implement `GET /invites/{code}` with `invited_by` and `already_member`, and the shared invite state checks (`invite_not_found`, `invite_used` before `invite_expired`); verify with integration tests for every preview and state-error scenario, using the clock for expiry
- [x] 6.3 Implement `POST /invites/{code}/accept` with a row lock, `already_member` without consuming, and the joined household returned with `role` `member`; verify with integration tests for success (household appears last in the list), second accept, already-member then another user accepts, and two concurrent accepts on separate connections yielding one member and one `invite_used`

## 7. Contract conformance and integration checks

- [x] 7.1 Add a unit test asserting every `(method, path, operationId)` from contract §3 exists in the generated OpenAPI document and no extra operations under `/api/v1/auth`, `/me`, `/households`, `/invites` exist; verify it passes
- [x] 7.2 Add `scripts/export_openapi.py` writing `contracts/openapi.json` (sorted keys, trailing newline), generate the file, and add a unit test that fails when the committed file differs from the generated document; verify `uv run python scripts/export_openapi.py && git diff --exit-code contracts/openapi.json` is clean
- [x] 7.3 Add one end-to-end integration test following the frontend flow: register → create household → create invite → second user registers, previews, accepts → owner lists members → member leaves → refresh → logout; verify it passes
- [x] 7.4 Run the full CI suite locally (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest`); verify all pass

## Workflow follow-up

- Tell the frontend that `contracts/openapi.json` is available and that the cookie name is `lumior_refresh` (the contract leaves the name to the backend).
- Archive the change after review with `/opsx:archive`.

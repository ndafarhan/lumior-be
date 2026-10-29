# Proposal

## Why

Every later Lumior module (budgets, expenses, lists, shopping) is scoped to a household and needs to know who is calling. The foundation left authentication and tenancy out on purpose. The frontend (`lumior-fe`, change `auth-and-households`) is already being built against mocks of the contract in `contracts/auth-and-households.md`, so the backend must now implement that contract exactly, including paths, `operationId`s, status codes, error codes, and cookie behavior.

## What Changes

- User registration, login, refresh, and logout under `/api/v1/auth`, returning a `Session` (`access_token`, `token_type`, `expires_in`, `user`).
- Short-lived bearer access tokens (15 minutes) for every authenticated endpoint. A missing, invalid, or expired token is 401 `unauthorized`, raised before any work is done.
- Refresh tokens delivered only as an `HttpOnly` cookie scoped to `Path=/api/v1/auth`, with a 30-day sliding lifetime, rotation on every refresh, a 30-second grace window for the just-replaced token, and revocation on logout.
- Current-user endpoints: `GET /me`, `PATCH /me` (name), `POST /me/password` (keeps the calling session, revokes the user's other refresh tokens).
- Households: list (ordered by join date), create (caller becomes `owner`), rename (owner only), list members, remove member / leave (`owner_cannot_leave` for the owner).
- Single-use invites with an expiry: owner creates, any signed-in user previews (`already_member` flag) and accepts.
- A shared membership check for every `/households/{id}/...` route with distinct `household_not_found` (404), `not_a_member` (403), and `owner_required` (403) codes, reusable by later household-scoped modules.
- Validation limits identical to the frontend's (trimmed names 1–100, passwords 8–128, case-insensitive unique email).
- New database tables and an Alembic migration for users, refresh tokens, households, memberships, and invites.
- New settings: token lifetimes, refresh cookie name, and real use of `SECRET_KEY` (rejecting the placeholder outside development and test).
- Export the generated OpenAPI document to `contracts/openapi.json`, as the contract says, so the frontend can generate types from it.

## Capabilities

### New Capabilities
- `user-auth`: registration, login, access-token authentication of requests, refresh-token cookie lifecycle (rotation, grace window, logout).
- `user-account`: the signed-in user's own profile and password.
- `households`: households, membership, roles, and the authorization rules for household-scoped routes.
- `household-invites`: creating, previewing, and accepting single-use invite codes.

### Modified Capabilities
None. The existing `api-conventions` requirements (base path, error envelope, 422 details, CORS with credentials, OpenAPI `operationId`s) already cover what the contract relies on and do not change.

## Impact

- **Code:** new modules `src/lumior/modules/identity` (users, auth, me) and `src/lumior/modules/households` (households, members, invites); shared auth dependencies in `src/lumior/api`; new error classes in `core/errors.py`; new settings in `core/config.py`; routers registered in `api/v1.py`.
- **Database:** new migration adding `users`, `refresh_tokens`, `households`, `household_members`, `household_invites`.
- **Dependencies:** a password hashing library (Argon2) and a JWT library for access tokens; `email-validator` for email validation.
- **API:** 15 new operations under `/api/v1` matching the contract's `operationId`s; `contracts/openapi.json` added.
- **Deployment:** `SECRET_KEY` becomes required in staging and production. Frontend and API must be same-site (see contract §8); cross-site deployment is out of scope.
- **Out of scope (per contract §9):** email verification, password reset, deleting households, ownership transfer, extra roles, revoking invites, social sign-in, rate limiting.

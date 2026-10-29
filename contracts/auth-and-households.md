# Auth and households: proposed API contract

Status: **draft for `lumior-be`**. Proposed by the frontend change `openspec/changes/auth-and-households` in `lumior-fe`.

The frontend is being built against this contract using mocks. Please treat it as the input to the backend `auth-and-households` change. If the backend needs something different, change this document (or tell the frontend) before implementing, so both sides stay on one contract. A machine-readable version will live next to this file as `contracts/openapi.json`.

## 1. Conventions (unchanged from `project-foundation`)

- All endpoints are under `/api/v1` and are described in `/api/v1/openapi.json` with the `operationId`s below.
- Every non-2xx response uses the existing envelope `{"error": {"code", "message", "details", "request_id"}}`. The frontend branches on `error.code`, so the codes below are part of the contract.
- Validation failures are HTTP 422 `validation_error`, with one `details` entry per field (`{"location": ["body", "<field>"], "reason", "type"}`).
- Authenticated requests send `Authorization: Bearer <access_token>`. A missing, invalid, or expired access token is HTTP 401 `unauthorized`.

## 2. Data shapes

```jsonc
// User
{ "id": "uuid", "email": "rina@example.com", "name": "Rina" }

// Session (returned by register, login, refresh)
{ "access_token": "opaque string", "token_type": "bearer", "expires_in": 900, "user": User }

// Household (always from the current user's point of view)
{ "id": "uuid", "name": "Rumah Bandung", "role": "owner" | "member", "member_count": 3 }

// Member
{ "user_id": "uuid", "name": "Budi", "email": "budi@example.com", "role": "owner" | "member" }

// Invite (as created by the owner)
{ "code": "url-safe string", "expires_at": "2026-11-04T10:00:00Z" }

// Invite preview (as seen by the person opening the link)
{ "household_id": "uuid", "household_name": "Kos Jakarta", "invited_by": "Rina",
  "expires_at": "2026-11-04T10:00:00Z", "already_member": false }
```

The frontend treats `access_token` as opaque. It does not decode it or read its expiry. `expires_in` is in seconds and informational only. Timestamps are ISO 8601 in UTC.

## 3. Endpoints

### Auth

| Method & path                | operationId     | Body                      | Success                                            | Errors                                 |
| ---------------------------- | --------------- | ------------------------- | -------------------------------------------------- | -------------------------------------- |
| `POST /api/v1/auth/register` | `auth_register` | `{name, email, password}` | **201** `Session` + sets refresh cookie            | 409 `email_taken`, 422                 |
| `POST /api/v1/auth/login`    | `auth_login`    | `{email, password}`       | **200** `Session` + sets refresh cookie            | 401 `invalid_credentials`              |
| `POST /api/v1/auth/refresh`  | `auth_refresh`  | none (cookie only)        | **200** `Session` + rotates refresh cookie         | 401 `invalid_refresh_token`            |
| `POST /api/v1/auth/logout`   | `auth_logout`   | none (cookie only)        | **204**, clears cookie, revokes that refresh token | none (204 even without a valid cookie) |

- Registration signs the user in. The frontend does not call login afterwards.
- `invalid_credentials` must be the same for an unknown email and a wrong password.
- Refresh and logout must not require an `Authorization` header. Refresh is what the frontend calls on every page load to find out whether the user is signed in.

### Current user

| Method & path              | operationId                | Body                               | Success        | Errors                              |
| -------------------------- | -------------------------- | ---------------------------------- | -------------- | ----------------------------------- |
| `GET /api/v1/me`           | `identity_get_me`          |                                    | **200** `User` | 401                                 |
| `PATCH /api/v1/me`         | `identity_update_me`       | `{name}`                           | **200** `User` | 422                                 |
| `POST /api/v1/me/password` | `identity_change_password` | `{current_password, new_password}` | **204**        | 400 `invalid_current_password`, 422 |

Changing the password must keep the session it was made from working: the current access token and refresh cookie stay valid. Revoking the user's _other_ refresh tokens is recommended.

### Households

| Method & path                                      | operationId                | Body     | Success                            | Errors                                                                                                                |
| -------------------------------------------------- | -------------------------- | -------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `GET /api/v1/households`                           | `households_list`          |          | **200** `Household[]`              |                                                                                                                       |
| `POST /api/v1/households`                          | `households_create`        | `{name}` | **201** `Household` (role `owner`) | 422                                                                                                                   |
| `PATCH /api/v1/households/{id}`                    | `households_update`        | `{name}` | **200** `Household`                | 403 `owner_required`, 403 `not_a_member`, 404 `household_not_found`, 422                                              |
| `GET /api/v1/households/{id}/members`              | `households_list_members`  |          | **200** `Member[]`                 | 403 `not_a_member`, 404 `household_not_found`                                                                         |
| `DELETE /api/v1/households/{id}/members/{user_id}` | `households_remove_member` |          | **204**                            | 403 `owner_required`, 403 `not_a_member`, 404 `household_not_found`, 404 `member_not_found`, 409 `owner_cannot_leave` |
| `POST /api/v1/households/{id}/invites`             | `households_create_invite` |          | **201** `Invite`                   | 403 `owner_required`, 403 `not_a_member`, 404 `household_not_found`                                                   |

- `GET /households` returns only the households the user belongs to, ordered by when the user joined (oldest first). The frontend falls back to the first item.
- Leaving a household is `DELETE /households/{id}/members/{own user_id}`. A member may do this, and the owner gets 409 `owner_cannot_leave`.
- Removing another member requires the owner. The owner removing themselves is also `owner_cannot_leave`.

### Invites

| Method & path                        | operationId                | Body | Success                             | Errors                                                                                |
| ------------------------------------ | -------------------------- | ---- | ----------------------------------- | ------------------------------------------------------------------------------------- |
| `GET /api/v1/invites/{code}`         | `households_get_invite`    |      | **200** invite preview              | 404 `invite_not_found`, 410 `invite_expired`, 410 `invite_used`                       |
| `POST /api/v1/invites/{code}/accept` | `households_accept_invite` |      | **200** `Household` (role `member`) | 404 `invite_not_found`, 410 `invite_expired`, 410 `invite_used`, 409 `already_member` |

- Both require a signed-in user.
- An invite is single use: after one accept it returns `invite_used`.
- `already_member` in the preview lets the frontend offer "switch to this household" instead of "Join". The accept endpoint still returns 409 `already_member` in that case, and the invite is not consumed.
- The frontend builds the link itself as `<frontend origin>/invite/<code>`, so the backend never needs to know the frontend URL.

## 4. Validation rules

The frontend checks these before sending, so the backend should enforce exactly the same limits:

| Field                      | Rule                                                     |
| -------------------------- | -------------------------------------------------------- |
| `name` (user)              | 1–100 characters after trimming whitespace               |
| `email`                    | valid email address, compared case-insensitively, unique |
| `password`, `new_password` | 8–128 characters                                         |
| `name` (household)         | 1–100 characters after trimming whitespace               |

Store trimmed names. Return 422 with field details if a rule fails.

## 5. Session and cookie behavior

- **Access token:** short-lived (suggested 15 minutes). The frontend keeps it in memory only. On any 401 from a request that carried a token, it calls `/auth/refresh` once and repeats the request once, including POST/PATCH/DELETE. So a 401 must mean "rejected before doing anything".
- **Refresh token:** sent only as a cookie, never in a response body.

  ```
  Set-Cookie: <name>=<token>; HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth; Max-Age=<lifetime>
  ```

  `Secure` may be omitted only in local development (`ENVIRONMENT=development`, plain `http://localhost`). A suggested lifetime is 30 days, sliding with each refresh.

- **Rotation:** every successful refresh issues a new refresh token and invalidates the old one.
- **Grace period for rotation (requested):** accept the just-replaced refresh token for a short window (suggested 30 s) and return a valid session for it. Two tabs loading at the same moment both call refresh with the same cookie. Without a grace period, one of them is signed out.
- **Logout:** revoke the refresh token from the cookie and clear the cookie with the same `Path`.

## 6. Authorization rules

- Every `/households/{id}/...` request checks membership first. If the household does not exist, return 404 `household_not_found`. If it exists but the user is not a member, return 403 `not_a_member`. The frontend treats both as "access to this household was lost" and switches the user to another household.
- Owner-only actions (rename, remove another member, create invite): 403 `owner_required` for a member. The frontend shows a permission message and does not switch households. **Please keep `owner_required` distinct from `not_a_member`.**
- Later household-scoped modules (budgets, expenses, lists, …) should reuse these two codes so the same frontend handling applies.

## 7. Error codes used by the frontend

| HTTP | `code`                     | Where                                                  |
| ---- | -------------------------- | ------------------------------------------------------ |
| 400  | `invalid_current_password` | change password                                        |
| 401  | `unauthorized`             | any authenticated endpoint                             |
| 401  | `invalid_credentials`      | login                                                  |
| 401  | `invalid_refresh_token`    | refresh (missing, unknown, expired, or revoked cookie) |
| 403  | `not_a_member`             | any `/households/{id}/...`                             |
| 403  | `owner_required`           | owner-only household actions                           |
| 404  | `household_not_found`      | any `/households/{id}/...`                             |
| 404  | `member_not_found`         | remove member                                          |
| 404  | `invite_not_found`         | invites                                                |
| 409  | `email_taken`              | register                                               |
| 409  | `owner_cannot_leave`       | remove member (owner targeting themselves)             |
| 409  | `already_member`           | accept invite                                          |
| 410  | `invite_expired`           | invites                                                |
| 410  | `invite_used`              | invites                                                |
| 422  | `validation_error`         | any body with invalid fields                           |

## 8. Deployment requirements

- **CORS:** the existing credentialed CORS setup is sufficient. The frontend origin must be in `CORS_ALLOWED_ORIGINS`, and `Authorization` must be an allowed request header (the foundation already echoes request headers).
- **Same site:** with `SameSite=Lax`, the refresh cookie is sent only if the frontend and backend are on the same site. `localhost:5173` and `localhost:8000` qualify. In production, use subdomains of one domain (for example `app.lumior.example` and `api.lumior.example`).
- **If they must be on different sites:** the cookie needs `SameSite=None; Secure`, and `/auth/refresh` and `/auth/logout` then need CSRF protection. Agree on that with the frontend first, because it changes this contract.

## 9. Out of scope for this contract

Email verification, password reset, deleting a household, transferring ownership, roles other than `owner` and `member`, revoking invites, and social sign-in. These can be added later without breaking anything here.

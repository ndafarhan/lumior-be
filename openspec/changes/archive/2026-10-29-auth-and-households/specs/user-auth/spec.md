# Spec Delta

## Purpose

Lets people create an account, sign in, and stay signed in across page loads, and lets every other endpoint know which user is calling, following the contract agreed with the frontend.

## ADDED Requirements

### Requirement: Session response shape
Register, login, and refresh SHALL return a `Session` body `{"access_token", "token_type": "bearer", "expires_in", "user": {"id", "email", "name"}}`, where `expires_in` is the access token lifetime in seconds. The refresh token SHALL NOT appear in any response body.

#### Scenario: Session body on login
- **WHEN** a user logs in successfully
- **THEN** the body contains a non-empty `access_token`, `token_type` equal to `bearer`, `expires_in` equal to the configured lifetime in seconds (900 by default), and the user's `id`, `email`, and `name`
- **AND** the body contains no refresh token

### Requirement: Registration signs the user in
`POST /api/v1/auth/register` (`auth_register`) with `{name, email, password}` SHALL create the user, respond 201 with a `Session`, and set the refresh cookie. Email SHALL be stored and compared case-insensitively; the name SHALL be stored trimmed.

#### Scenario: Successful registration
- **WHEN** a client registers with name `"  Rina "`, email `Rina@Example.com`, and a valid password
- **THEN** the response is 201 with a `Session` whose `user.name` is `Rina` and `user.email` is `rina@example.com`
- **AND** the response sets the refresh cookie

#### Scenario: Email already registered
- **WHEN** a client registers with `RINA@example.com` while `rina@example.com` already exists
- **THEN** the response is 409 with `error.code` equal to `email_taken`

#### Scenario: Invalid registration fields
- **WHEN** a client registers with a password of 7 characters, a name that is only whitespace, or a malformed email
- **THEN** the response is 422 `validation_error` with one `details` entry per invalid field, located at `["body", "<field>"]`

### Requirement: Login with email and password
`POST /api/v1/auth/login` (`auth_login`) with `{email, password}` SHALL respond 200 with a `Session` and set the refresh cookie when the credentials match. Failures SHALL be 401 `invalid_credentials`, identical for an unknown email and a wrong password.

#### Scenario: Correct credentials
- **WHEN** a registered user logs in with their email in any letter case and correct password
- **THEN** the response is 200 with a `Session` and sets the refresh cookie

#### Scenario: Wrong password
- **WHEN** a client logs in with a registered email and a wrong password
- **THEN** the response is 401 with `error.code` equal to `invalid_credentials`

#### Scenario: Unknown email
- **WHEN** a client logs in with an email that is not registered
- **THEN** the response is 401 with `error.code` `invalid_credentials` and the same message as for a wrong password

### Requirement: Password validation limits
Passwords on register and `new_password` on password change SHALL be 8 to 128 characters; otherwise the system SHALL respond 422 `validation_error` with a details entry for that field.

#### Scenario: Password too long
- **WHEN** a client registers with a 129-character password
- **THEN** the response is 422 with a `details` entry located at `["body", "password"]`

#### Scenario: Password at the limits
- **WHEN** a client registers with an 8-character password, and another with a 128-character password
- **THEN** both registrations succeed with 201

### Requirement: Bearer access-token authentication
Authenticated endpoints SHALL require `Authorization: Bearer <access_token>`. A missing, malformed, invalid, or expired token, or a token for a user that no longer exists, SHALL yield 401 `unauthorized` before the endpoint performs any change.

#### Scenario: Missing token
- **WHEN** a client calls `GET /api/v1/me` without an `Authorization` header
- **THEN** the response is 401 with `error.code` equal to `unauthorized`

#### Scenario: Expired token
- **WHEN** a client calls an authenticated endpoint with an access token older than its lifetime
- **THEN** the response is 401 `unauthorized`

#### Scenario: Rejected write has no effect
- **WHEN** a client sends `POST /api/v1/households` with an invalid access token
- **THEN** the response is 401 `unauthorized` and no household is created

### Requirement: Refresh token cookie
Successful register, login, and refresh SHALL set the refresh token as a cookie with `HttpOnly`, `SameSite=Lax`, `Path=/api/v1/auth`, and `Max-Age` equal to the refresh lifetime (30 days by default). `Secure` SHALL be set in every environment except `development` and `test`.

#### Scenario: Cookie attributes in production
- **WHEN** a user logs in with the service running in `production`
- **THEN** the `Set-Cookie` header has `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/api/v1/auth`, and `Max-Age=2592000`

#### Scenario: Cookie in development
- **WHEN** a user logs in with the service running in `development`
- **THEN** the `Set-Cookie` header has `HttpOnly`, `SameSite=Lax`, and `Path=/api/v1/auth`, without `Secure`

### Requirement: Refresh rotates the token
`POST /api/v1/auth/refresh` (`auth_refresh`) SHALL authenticate only by the refresh cookie, without an `Authorization` header. On success it SHALL respond 200 with a new `Session`, issue a new refresh cookie with a renewed lifetime, and invalidate the presented token.

#### Scenario: Successful refresh
- **WHEN** a client calls refresh with a valid refresh cookie and no `Authorization` header
- **THEN** the response is 200 with a `Session` and sets a refresh cookie with a different value

#### Scenario: Missing or unknown cookie
- **WHEN** a client calls refresh without a cookie, or with a value that was never issued
- **THEN** the response is 401 with `error.code` equal to `invalid_refresh_token`

#### Scenario: Expired or revoked cookie
- **WHEN** a client calls refresh with a refresh token past its lifetime, or one revoked by logout or a password change
- **THEN** the response is 401 `invalid_refresh_token`

### Requirement: Rotation grace window
A refresh token replaced by rotation SHALL still be accepted for 30 seconds after it was replaced, returning 200 with a valid `Session` and a refresh cookie, so concurrent tabs are not signed out. After the window it SHALL be rejected with 401 `invalid_refresh_token`.

#### Scenario: Two tabs refresh at once
- **WHEN** two refresh requests carry the same refresh cookie and the second arrives within 30 seconds of the first succeeding
- **THEN** both respond 200 with a valid `Session` and each sets a usable refresh cookie

#### Scenario: Old token reused after the window
- **WHEN** a client calls refresh with a token that was rotated more than 30 seconds ago
- **THEN** the response is 401 `invalid_refresh_token`

### Requirement: Logout revokes the refresh token
`POST /api/v1/auth/logout` (`auth_logout`) SHALL authenticate only by the refresh cookie, revoke that refresh token if it is valid, clear the cookie using the same `Path`, and always respond 204.

#### Scenario: Logout with a valid cookie
- **WHEN** a client calls logout with a valid refresh cookie
- **THEN** the response is 204, the `Set-Cookie` header clears the cookie with `Path=/api/v1/auth`, and a later refresh with that token returns 401 `invalid_refresh_token`

#### Scenario: Logout without a cookie
- **WHEN** a client calls logout without a refresh cookie or with an invalid one
- **THEN** the response is 204

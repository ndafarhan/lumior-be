# Spec Delta

## Purpose

Lets a signed-in user read and update their own profile and change their password without losing the session they are using.

## ADDED Requirements

### Requirement: Read the current user
`GET /api/v1/me` (`identity_get_me`) SHALL respond 200 with the authenticated user as `{"id", "email", "name"}`.

#### Scenario: Signed-in user
- **WHEN** a client calls `GET /api/v1/me` with a valid access token
- **THEN** the response is 200 with that user's `id`, `email`, and `name`

#### Scenario: Not signed in
- **WHEN** a client calls `GET /api/v1/me` without a valid access token
- **THEN** the response is 401 `unauthorized`

### Requirement: Update the current user's name
`PATCH /api/v1/me` (`identity_update_me`) with `{name}` SHALL store the trimmed name and respond 200 with the updated user. A name that is empty after trimming or longer than 100 characters SHALL be 422 `validation_error`.

#### Scenario: Rename
- **WHEN** a signed-in user sends `PATCH /api/v1/me` with name `"  Rina S. "`
- **THEN** the response is 200 with `name` equal to `Rina S.` and a later `GET /api/v1/me` returns the same name

#### Scenario: Blank name
- **WHEN** a signed-in user sends a name containing only spaces
- **THEN** the response is 422 with a `details` entry located at `["body", "name"]`

### Requirement: Change password
`POST /api/v1/me/password` (`identity_change_password`) with `{current_password, new_password}` SHALL replace the password and respond 204 when `current_password` is correct. A wrong `current_password` SHALL be 400 `invalid_current_password` with no change.

#### Scenario: Correct current password
- **WHEN** a signed-in user changes their password with the correct current password and a valid new password
- **THEN** the response is 204, login with the new password succeeds, and login with the old password returns 401 `invalid_credentials`

#### Scenario: Wrong current password
- **WHEN** a signed-in user sends a wrong `current_password`
- **THEN** the response is 400 with `error.code` equal to `invalid_current_password` and the old password still works

#### Scenario: New password too short
- **WHEN** a signed-in user sends a `new_password` of 7 characters
- **THEN** the response is 422 with a `details` entry located at `["body", "new_password"]`

### Requirement: Password change keeps the current session only
After a password change, the access token used for the request and the refresh token of the same sign-in session SHALL remain valid, and every other refresh token of that user SHALL be revoked. The session is identified from the access token, because the refresh cookie is not sent to this path.

#### Scenario: Calling session survives
- **WHEN** a user changes their password from a session and then calls refresh with that session's cookie
- **THEN** refresh responds 200 with a `Session`

#### Scenario: Other sessions are signed out
- **WHEN** a user has signed in on two devices and changes their password from the first
- **THEN** a refresh with the second device's refresh cookie returns 401 `invalid_refresh_token`

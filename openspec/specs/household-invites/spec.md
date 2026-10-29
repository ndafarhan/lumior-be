# household-invites Specification

## Purpose

Lets a household owner invite people with a shareable single-use code, and lets the invited person preview and accept it to join the household.

## Requirements

### Requirement: Create an invite
`POST /api/v1/households/{id}/invites` (`households_create_invite`) SHALL let the owner create an invite and respond 201 with `{"code", "expires_at"}`. The code SHALL be URL-safe, unguessable, and unique; `expires_at` SHALL be an ISO 8601 UTC timestamp 7 days after creation. The household access check and owner check apply.

#### Scenario: Owner creates an invite
- **WHEN** the owner creates an invite
- **THEN** the response is 201 with a `code` containing only URL-safe characters and an `expires_at` 7 days in the future, in UTC

#### Scenario: Member tries to create an invite
- **WHEN** a member (not owner) creates an invite
- **THEN** the response is 403 `owner_required`

#### Scenario: Several open invites
- **WHEN** the owner creates two invites
- **THEN** the codes differ and both can be used

### Requirement: Invite state errors
For any invite endpoint, an unknown code SHALL be 404 `invite_not_found`, an already-accepted invite SHALL be 410 `invite_used`, and an invite past `expires_at` SHALL be 410 `invite_expired`. When an invite is both used and expired, `invite_used` SHALL win.

#### Scenario: Unknown code
- **WHEN** a signed-in user previews or accepts a code that was never issued
- **THEN** the response is 404 with `error.code` equal to `invite_not_found`

#### Scenario: Expired invite
- **WHEN** a signed-in user previews or accepts an invite after its `expires_at`
- **THEN** the response is 410 with `error.code` equal to `invite_expired`

#### Scenario: Used invite
- **WHEN** a signed-in user previews or accepts an invite that was already accepted
- **THEN** the response is 410 with `error.code` equal to `invite_used`

### Requirement: Preview an invite
`GET /api/v1/invites/{code}` (`households_get_invite`) SHALL require a signed-in user and respond 200 with `{"household_id", "household_name", "invited_by", "expires_at", "already_member"}`, where `invited_by` is the name of the user who created the invite and `already_member` tells whether the caller already belongs to the household.

#### Scenario: Preview by a new user
- **WHEN** a signed-in user who is not in the household previews a valid invite created by Rina for `Kos Jakarta`
- **THEN** the response is 200 with `household_name` `Kos Jakarta`, `invited_by` `Rina`, and `already_member` false

#### Scenario: Preview by an existing member
- **WHEN** a member of the household previews a valid invite for it
- **THEN** the response is 200 with `already_member` true

#### Scenario: Preview without signing in
- **WHEN** a client previews an invite without a valid access token
- **THEN** the response is 401 `unauthorized`

### Requirement: Accept an invite
`POST /api/v1/invites/{code}/accept` (`households_accept_invite`) SHALL add the caller to the household as `member`, mark the invite used, and respond 200 with the household from the caller's view (`role` `member`). An invite SHALL be accepted at most once, even under concurrent requests.

#### Scenario: Successful accept
- **WHEN** a signed-in user who is not in the household accepts a valid invite
- **THEN** the response is 200 with the household, `role` `member`, and the household appears last in their `GET /api/v1/households`

#### Scenario: Second accept
- **WHEN** another user accepts the same invite afterwards
- **THEN** the response is 410 `invite_used`

#### Scenario: Concurrent accepts
- **WHEN** two different users accept the same valid invite at the same time
- **THEN** exactly one becomes a member and the other receives 410 `invite_used`

### Requirement: Accept by an existing member
When the caller already belongs to the invite's household, accept SHALL respond 409 `already_member` and SHALL NOT consume the invite.

#### Scenario: Member accepts their own household's invite
- **WHEN** a member accepts a valid invite for a household they already belong to
- **THEN** the response is 409 with `error.code` equal to `already_member`, and another user can still accept that invite

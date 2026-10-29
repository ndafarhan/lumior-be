# households Specification

## Purpose

Groups users into households with an `owner` and `member`s, and defines the access rules that every household-scoped endpoint, now and in later modules, applies.

## Requirements

### Requirement: Household representation
A household SHALL be returned from the caller's point of view as `{"id", "name", "role", "member_count"}`, where `role` is the caller's role (`owner` or `member`) and `member_count` is the current number of members including the owner.

#### Scenario: Owner's view
- **WHEN** the owner of a household with three members reads it
- **THEN** the household has `role` equal to `owner` and `member_count` equal to 3

### Requirement: List the caller's households
`GET /api/v1/households` (`households_list`) SHALL respond 200 with only the households the caller belongs to, ordered by when the caller joined each one, oldest first.

#### Scenario: Ordered by join time
- **WHEN** a user created household A, then joined household B by invite
- **THEN** the list is `[A, B]` with roles `owner` and `member`

#### Scenario: Other households hidden
- **WHEN** a user lists households while other households exist that they do not belong to
- **THEN** those households are not in the list

#### Scenario: No households
- **WHEN** a user who belongs to no household lists households
- **THEN** the response is 200 with an empty list

### Requirement: Create a household
`POST /api/v1/households` (`households_create`) with `{name}` SHALL create a household with the trimmed name, make the caller its `owner`, and respond 201 with the household (`role` `owner`, `member_count` 1). Names empty after trimming or over 100 characters SHALL be 422.

#### Scenario: Create
- **WHEN** a signed-in user creates a household named `" Rumah Bandung "`
- **THEN** the response is 201 with `name` `Rumah Bandung`, `role` `owner`, and `member_count` 1

#### Scenario: Name too long
- **WHEN** a signed-in user creates a household with a 101-character name
- **THEN** the response is 422 with a `details` entry located at `["body", "name"]`

### Requirement: Household access check
Every `/api/v1/households/{id}/...` request and `PATCH /api/v1/households/{id}` SHALL first check access: 404 `household_not_found` if the household does not exist (including a malformed id), and 403 `not_a_member` if the caller is not a member. These checks SHALL run before owner checks or body validation.

#### Scenario: Unknown household
- **WHEN** a signed-in user calls `GET /api/v1/households/{id}/members` with an id that matches no household
- **THEN** the response is 404 with `error.code` equal to `household_not_found`

#### Scenario: Not a member
- **WHEN** a signed-in user calls `GET /api/v1/households/{id}/members` for an existing household they do not belong to
- **THEN** the response is 403 with `error.code` equal to `not_a_member`

#### Scenario: Non-member sends an invalid body
- **WHEN** a non-member sends `PATCH /api/v1/households/{id}` with a blank name
- **THEN** the response is 403 `not_a_member`, not 422

### Requirement: Owner-only actions
Renaming a household, removing another member, and creating an invite SHALL be allowed only for the owner. A member SHALL receive 403 `owner_required`, which is distinct from `not_a_member`.

#### Scenario: Member tries to rename
- **WHEN** a member (not owner) sends `PATCH /api/v1/households/{id}` with a valid name
- **THEN** the response is 403 with `error.code` equal to `owner_required` and the name is unchanged

### Requirement: Rename a household
`PATCH /api/v1/households/{id}` (`households_update`) with `{name}` SHALL let the owner store the trimmed name and respond 200 with the household. Invalid names SHALL be 422.

#### Scenario: Owner renames
- **WHEN** the owner renames the household to `Kos Jakarta`
- **THEN** the response is 200 with `name` `Kos Jakarta` and every member sees the new name in their list

### Requirement: List members
`GET /api/v1/households/{id}/members` (`households_list_members`) SHALL respond 200 to any member with every member as `{"user_id", "name", "email", "role"}`, ordered by join time, oldest first.

#### Scenario: Member lists members
- **WHEN** a member lists the members of a household with an owner and two members
- **THEN** the response is 200 with three entries, the owner's having `role` `owner`

### Requirement: Remove a member or leave
`DELETE /api/v1/households/{id}/members/{user_id}` (`households_remove_member`) SHALL respond 204 when a member removes themselves (leaving) or when the owner removes another member. The removed user SHALL lose access to the household immediately.

#### Scenario: Member leaves
- **WHEN** a member deletes their own membership
- **THEN** the response is 204 and their next request to that household returns 403 `not_a_member`

#### Scenario: Owner removes a member
- **WHEN** the owner deletes another member's membership
- **THEN** the response is 204 and the household's `member_count` decreases by one

#### Scenario: Member removes someone else
- **WHEN** a member deletes another member's membership
- **THEN** the response is 403 `owner_required` and nobody is removed

### Requirement: Owner cannot leave
When the target of a member removal is the owner, the system SHALL respond 409 `owner_cannot_leave` and keep the membership.

#### Scenario: Owner targets themselves
- **WHEN** the owner deletes their own membership
- **THEN** the response is 409 with `error.code` equal to `owner_cannot_leave`

### Requirement: Unknown member
When the target `user_id` is not a member of the household (or is malformed), the system SHALL respond 404 `member_not_found`, after the access check passes. For a non-owner caller targeting someone else, `owner_required` SHALL take precedence.

#### Scenario: Owner removes a non-member
- **WHEN** the owner deletes a membership for a user who does not belong to the household
- **THEN** the response is 404 with `error.code` equal to `member_not_found`

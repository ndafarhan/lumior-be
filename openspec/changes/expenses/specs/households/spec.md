# Spec Delta

## MODIFIED Requirements

### Requirement: Household representation
A household SHALL be returned from the caller's point of view as `{"id", "name", "role", "member_count", "currency"}`, where `role` is the caller's role (`owner` or `member`), `member_count` is the current number of members including the owner, and `currency` is the household's ISO 4217 currency code. Every endpoint that returns a household (list, create, rename, accept invite) SHALL include `currency`.

#### Scenario: Owner's view
- **WHEN** the owner of a household with three members reads it
- **THEN** the household has `role` equal to `owner` and `member_count` equal to 3

#### Scenario: Currency on every household response
- **WHEN** a user lists their households, creates one, renames one, or accepts an invite to one
- **THEN** each returned household includes its `currency`

#### Scenario: Existing households after the upgrade
- **WHEN** a household created before currencies existed is read after the upgrade
- **THEN** its `currency` is `IDR`

### Requirement: Create a household
`POST /api/v1/households` (`households_create`) with `{name, currency?}` SHALL create a household with the trimmed name and the given currency (default `IDR`), make the caller its `owner`, and respond 201 with the household (`role` `owner`, `member_count` 1). Names empty after trimming or over 100 characters SHALL be 422. A `currency` that is not a supported ISO 4217 code SHALL be 422 with a `details` entry located at `["body", "currency"]`.

#### Scenario: Create
- **WHEN** a signed-in user creates a household named `" Rumah Bandung "`
- **THEN** the response is 201 with `name` `Rumah Bandung`, `role` `owner`, `member_count` 1, and `currency` `IDR`

#### Scenario: Name too long
- **WHEN** a signed-in user creates a household with a 101-character name
- **THEN** the response is 422 with a `details` entry located at `["body", "name"]`

#### Scenario: Create with a currency
- **WHEN** a signed-in user creates a household with `currency` `JPY`
- **THEN** the response is 201 with `currency` `JPY`

#### Scenario: Unsupported currency
- **WHEN** a signed-in user creates a household with `currency` `XYZ`
- **THEN** the response is 422 with a `details` entry located at `["body", "currency"]` and no household is created

### Requirement: Rename a household
`PATCH /api/v1/households/{id}` (`households_update`) with `{name}` SHALL let the owner store the trimmed name and respond 200 with the household. Invalid names SHALL be 422. The household's currency SHALL NOT change through this endpoint or any other.

#### Scenario: Owner renames
- **WHEN** the owner renames the household to `Kos Jakarta`
- **THEN** the response is 200 with `name` `Kos Jakarta` and every member sees the new name in their list

#### Scenario: Currency cannot be changed
- **WHEN** the owner of an `IDR` household sends `PATCH /api/v1/households/{id}` with `{"name": "Kos Jakarta", "currency": "USD"}`
- **THEN** the response is 200 with `name` `Kos Jakarta` and `currency` still `IDR`

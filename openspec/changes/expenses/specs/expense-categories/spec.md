# Spec Delta

## Purpose

Gives each household its own set of spending categories, starting from a default set, with names unique within the household and archiving instead of deletion, so past expenses always keep a valid category.

## ADDED Requirements

### Requirement: Category representation
A category SHALL be returned as `{"id", "name", "archived"}`. Any member of the household (owner or member) SHALL be able to call every category endpoint, after the household access check.

#### Scenario: Member reads categories
- **WHEN** a household member who is not the owner lists the categories
- **THEN** the response is 200 and each entry has exactly `id`, `name`, and `archived`

#### Scenario: Non-member
- **WHEN** a signed-in user who is not a member calls `GET /api/v1/households/{id}/expense-categories`
- **THEN** the response is 403 `not_a_member`

### Requirement: Default categories
Every new household SHALL be created with nine active categories, in the same transaction as the household: `Groceries`, `Dining out`, `Transport`, `Utilities`, `Housing`, `Health`, `Education`, `Entertainment`, `Other`. Households that existed before this capability SHALL receive the same nine categories on upgrade.

#### Scenario: New household
- **WHEN** a user creates a household and lists its categories
- **THEN** the list has exactly the nine default categories, none archived

#### Scenario: Existing household after the upgrade
- **WHEN** a household created before categories existed lists its categories after the upgrade
- **THEN** the list has exactly the nine default categories

### Requirement: List categories
`GET /api/v1/households/{household_id}/expense-categories` (`expenses_list_categories`) SHALL respond 200 with all of the household's categories, active and archived, ordered by name case-insensitively.

#### Scenario: Ordered by name, archived included
- **WHEN** a household has categories `groceries`, `Dining out`, and an archived `Books`
- **THEN** the list is `Books`, `Dining out`, `groceries`, with `Books` having `archived` true

#### Scenario: Other households' categories hidden
- **WHEN** a member lists categories while another household has its own categories
- **THEN** only this household's categories are returned

### Requirement: Create a category
`POST /api/v1/households/{household_id}/expense-categories` (`expenses_create_category`) with `{name}` SHALL create an active category with the trimmed name and respond 201 with it. A name that is empty after trimming or longer than 50 characters SHALL be 422 with a `details` entry located at `["body", "name"]`.

#### Scenario: Create
- **WHEN** a member creates a category named `" Pets "`
- **THEN** the response is 201 with `name` `Pets` and `archived` false, and it appears in the list

#### Scenario: Name too long
- **WHEN** a member creates a category with a 51-character name
- **THEN** the response is 422 with a `details` entry located at `["body", "name"]`

### Requirement: Category names are unique within a household
A category name SHALL be unique within its household, ignoring case and including archived categories. Creating or renaming to a name that is taken SHALL respond 409 `category_name_taken` with a `details` entry located at `["body", "name"]`. The same name SHALL be allowed in different households.

#### Scenario: Duplicate ignoring case
- **WHEN** a member creates a category named `groceries` in a household that has `Groceries`
- **THEN** the response is 409 with `error.code` equal to `category_name_taken` and a `details` entry located at `["body", "name"]`

#### Scenario: Name of an archived category
- **WHEN** a member renames a category to the name of an archived category in the same household
- **THEN** the response is 409 `category_name_taken`

#### Scenario: Same name in another household
- **WHEN** a member creates a category named `Pets` while another household already has `Pets`
- **THEN** the response is 201

#### Scenario: Renaming to its own name
- **WHEN** a member renames `Groceries` to `groceries`
- **THEN** the response is 200 with `name` `groceries`

### Requirement: Update a category
`PATCH /api/v1/households/{household_id}/expense-categories/{category_id}` (`expenses_update_category`) with `{name?, archived?}` SHALL apply the given fields and respond 200 with the category. Omitted fields SHALL stay unchanged. `{"archived": true}` archives the category and `{"archived": false}` restores it, and neither SHALL change existing expenses.

#### Scenario: Rename
- **WHEN** a member sends `{"name": "Food"}` for `Groceries`
- **THEN** the response is 200 with `name` `Food` and `archived` unchanged

#### Scenario: Archive and restore
- **WHEN** a member archives a category that has expenses, then restores it
- **THEN** both responses are 200 with `archived` true and then false, and the expenses still have that `category_id`

### Requirement: Unknown category
A `category_id` in the path that does not exist, is malformed, or belongs to another household SHALL respond 404 `category_not_found`, after the household access check.

#### Scenario: Another household's category
- **WHEN** a member updates a category id that belongs to a different household
- **THEN** the response is 404 with `error.code` equal to `category_not_found` and that category is unchanged

### Requirement: Categories cannot be deleted
The API SHALL NOT offer a way to delete a category. Archiving SHALL be the only way to retire one.

#### Scenario: Delete is not available
- **WHEN** a member sends `DELETE /api/v1/households/{household_id}/expense-categories/{category_id}`
- **THEN** the response is 405 and the category still exists

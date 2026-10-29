# Spec Delta

## Purpose

Lets household members record, correct, and remove what they spend, browse it month by month, and see each month's total and spending per category, in the household's currency and without rounding drift.

## ADDED Requirements

### Requirement: Expense representation
An expense SHALL be returned as `{"id", "amount", "spent_on", "category_id", "note", "created_at", "updated_at"}`. `amount` is a money object `{"amount", "currency"}` whose amount is a decimal string with exactly the currency's number of decimal places. `spent_on` is `YYYY-MM-DD`, `note` is a string or null, and the timestamps are ISO 8601 in UTC. Any member of the household SHALL be able to call every expense endpoint.

#### Scenario: Two-decimal currency
- **WHEN** a member of an `IDR` household creates an expense with amount `"45000"`
- **THEN** the returned `amount` is `{"amount": "45000.00", "currency": "IDR"}`

#### Scenario: Zero-decimal currency
- **WHEN** a member of a `JPY` household creates an expense with amount `"1200"`
- **THEN** the returned `amount` is `{"amount": "1200", "currency": "JPY"}`

#### Scenario: Member who is not the owner
- **WHEN** a member who is not the owner creates, updates, lists, and deletes expenses
- **THEN** every request succeeds

### Requirement: Create an expense
`POST /api/v1/households/{household_id}/expenses` (`expenses_create`) with `{amount, spent_on, category_id, note?}` SHALL store the expense in the household and respond 201 with it, with `created_at` equal to `updated_at`.

#### Scenario: Create
- **WHEN** a member creates an expense of `{"amount": "45000.00", "currency": "IDR"}` on `2026-10-03` in `Groceries` with note `Weekly market`
- **THEN** the response is 201 with those values and it appears in the list for `2026-10`

#### Scenario: Missing required field
- **WHEN** a member creates an expense without `spent_on`
- **THEN** the response is 422 `validation_error` with a `details` entry located at `["body", "spent_on"]`

### Requirement: Amount validation
`amount.amount` SHALL be a decimal string greater than 0, with at most the household currency's number of decimal places and at most 12 digits before the decimal point. Otherwise the response SHALL be 422 `validation_error` with a `details` entry located at `["body", "amount", "amount"]`. Amounts SHALL be rejected, not rounded.

#### Scenario: Zero
- **WHEN** a member creates an expense with amount `"0"`
- **THEN** the response is 422 with a `details` entry located at `["body", "amount", "amount"]`

#### Scenario: Too many decimals
- **WHEN** a member of an `IDR` household creates an expense with amount `"10.005"`, or a member of a `JPY` household with amount `"10.5"`
- **THEN** the response is 422 with a `details` entry located at `["body", "amount", "amount"]` and nothing is stored

#### Scenario: Too many digits
- **WHEN** a member creates an expense with amount `"1000000000000"` (13 digits)
- **THEN** the response is 422 with a `details` entry located at `["body", "amount", "amount"]`

#### Scenario: Largest amount
- **WHEN** a member of an `IDR` household creates an expense with amount `"999999999999.99"`
- **THEN** the response is 201 with that amount

#### Scenario: JSON number
- **WHEN** a member sends the amount as the JSON number `45000`
- **THEN** the response is 422 with a `details` entry located at `["body", "amount", "amount"]`

### Requirement: Currency must match the household
`amount.currency` SHALL equal the household's currency. Otherwise the response SHALL be 422 with `error.code` `currency_mismatch` and a `details` entry located at `["body", "amount", "currency"]`.

#### Scenario: Wrong currency
- **WHEN** a member of an `IDR` household creates an expense in `USD`
- **THEN** the response is 422 with `error.code` equal to `currency_mismatch` and a `details` entry located at `["body", "amount", "currency"]`

### Requirement: Spending date range
`spent_on` SHALL be a valid date, not before `2000-01-01`, and not later than one day after the server's current UTC date. Otherwise the response SHALL be 422 `validation_error` with a `details` entry located at `["body", "spent_on"]`.

#### Scenario: Tomorrow in UTC
- **WHEN** the server's UTC date is `2026-10-29` and a member creates an expense on `2026-10-30`
- **THEN** the response is 201

#### Scenario: Two days ahead
- **WHEN** the server's UTC date is `2026-10-29` and a member creates an expense on `2026-10-31`
- **THEN** the response is 422 with a `details` entry located at `["body", "spent_on"]`

#### Scenario: Before 2000
- **WHEN** a member creates an expense on `1999-12-31`
- **THEN** the response is 422 with a `details` entry located at `["body", "spent_on"]`

#### Scenario: Not a date
- **WHEN** a member creates an expense on `2026-02-30`
- **THEN** the response is 422 with a `details` entry located at `["body", "spent_on"]`

### Requirement: Expense category
`category_id` SHALL be one of the household's categories; otherwise the response SHALL be 422 with `error.code` `category_not_found`. An archived category SHALL be rejected with 422 `category_archived` when an expense is created with it or an update changes `category_id` to it. Both codes SHALL include a `details` entry located at `["body", "category_id"]`.

#### Scenario: Another household's category
- **WHEN** a member creates an expense with a `category_id` from a different household
- **THEN** the response is 422 with `error.code` equal to `category_not_found` and a `details` entry located at `["body", "category_id"]`

#### Scenario: Archived category on create
- **WHEN** a member creates an expense in an archived category
- **THEN** the response is 422 with `error.code` equal to `category_archived`

#### Scenario: Moving an expense to an archived category
- **WHEN** a member updates an expense's `category_id` to a different, archived category
- **THEN** the response is 422 `category_archived` and the expense is unchanged

#### Scenario: Editing an expense whose category was archived later
- **WHEN** an expense's category is archived, and a member then updates the expense's note, repeating the same `category_id`
- **THEN** the response is 200 with the new note and the same `category_id`

### Requirement: Note
`note` SHALL be optional and stored trimmed. A note that is empty or only whitespace SHALL be stored as null. A note longer than 500 characters after trimming SHALL be 422 `validation_error` with a `details` entry located at `["body", "note"]`.

#### Scenario: Whitespace-only note
- **WHEN** a member creates an expense with note `"   "`
- **THEN** the returned `note` is null

#### Scenario: Trimmed note
- **WHEN** a member creates an expense with note `" Weekly market "`
- **THEN** the returned `note` is `Weekly market`

#### Scenario: Note too long
- **WHEN** a member creates an expense with a 501-character note
- **THEN** the response is 422 with a `details` entry located at `["body", "note"]`

### Requirement: Update an expense
`PATCH /api/v1/households/{household_id}/expenses/{expense_id}` (`expenses_update`) with any subset of the create fields SHALL apply them, keep omitted fields unchanged, set `updated_at` to the current time, and respond 200 with the expense. `"note": null` SHALL clear the note. The validation rules for create SHALL apply to every field that is sent.

#### Scenario: Partial update
- **WHEN** a member sends `{"amount": {"amount": "50000.00", "currency": "IDR"}}` for an expense
- **THEN** the response is 200 with the new amount, the other fields unchanged, and `updated_at` later than `created_at`

#### Scenario: Clear the note
- **WHEN** a member sends `{"note": null}` for an expense with a note
- **THEN** the response is 200 with `note` null

### Requirement: Delete an expense
`DELETE /api/v1/households/{household_id}/expenses/{expense_id}` (`expenses_delete`) SHALL delete the expense and respond 204.

#### Scenario: Delete
- **WHEN** a member deletes an expense
- **THEN** the response is 204, it no longer appears in the list, and deleting it again is 404 `expense_not_found`

### Requirement: Unknown expense
An `expense_id` that does not exist, is malformed, or belongs to another household SHALL respond 404 `expense_not_found` on update and delete, after the household access check.

#### Scenario: Another household's expense
- **WHEN** a member of household A deletes an expense of household B
- **THEN** the response is 404 with `error.code` equal to `expense_not_found` and the expense still exists

### Requirement: List expenses by month
`GET /api/v1/households/{household_id}/expenses` (`expenses_list`) SHALL respond 200 with `{"items", "next_cursor"}` containing the household's expenses whose `spent_on` falls in the required `month` query parameter (`YYYY-MM`, month 01–12), ordered by `spent_on` descending, then `created_at` descending, then `id`. A missing or invalid `month` SHALL be 422 with a `details` entry located at `["query", "month"]`.

#### Scenario: Month and order
- **WHEN** a household has expenses on `2026-09-30`, `2026-10-01`, and two on `2026-10-03`, and a member lists `2026-10`
- **THEN** the items are the two `2026-10-03` expenses, newest `created_at` first, then the `2026-10-01` expense

#### Scenario: Invalid month
- **WHEN** a member lists expenses with `month` equal to `2026-13`
- **THEN** the response is 422 with a `details` entry located at `["query", "month"]`

#### Scenario: Empty month
- **WHEN** a member lists a month without expenses
- **THEN** the response is 200 with `items` empty and `next_cursor` null

### Requirement: Category filter
The list SHALL accept an optional `category_id` query parameter that keeps only expenses in that category. A `category_id` that is not one of the household's categories SHALL return an empty page, not an error.

#### Scenario: Filter by category
- **WHEN** a member lists `2026-10` with the `category_id` of `Transport`
- **THEN** only the month's `Transport` expenses are returned

#### Scenario: Unknown category filter
- **WHEN** a member lists with a `category_id` from another household
- **THEN** the response is 200 with `items` empty and `next_cursor` null

### Requirement: Cursor pagination
The list SHALL return at most `limit` items (1–100, default 50). `next_cursor` SHALL be an opaque string when more items follow and null on the last page. Passing it as `cursor` SHALL return the next items in the same order, without gaps or repeats. An invalid `cursor` or a `limit` out of range SHALL be 422 with a `details` entry located at `["query", "cursor"]` or `["query", "limit"]`.

#### Scenario: Walk all pages
- **WHEN** a month has 5 expenses and a member lists it with `limit` 2, following `next_cursor` until it is null
- **THEN** the pages have 2, 2, and 1 items, together exactly the 5 expenses in list order

#### Scenario: Default limit
- **WHEN** a month has 51 expenses and a member lists it without `limit`
- **THEN** the page has 50 items and a non-null `next_cursor`

#### Scenario: Tampered cursor
- **WHEN** a member lists with `cursor` equal to `not-a-cursor`
- **THEN** the response is 422 with a `details` entry located at `["query", "cursor"]`

#### Scenario: Limit out of range
- **WHEN** a member lists with `limit` 101
- **THEN** the response is 422 with a `details` entry located at `["query", "limit"]`

### Requirement: Monthly summary
`GET /api/v1/households/{household_id}/expense-summary` (`expenses_get_summary`) with the required `month` SHALL respond 200 with `{"month", "total", "categories"}`. `total` is the exact sum of the month's expenses in the household currency. `categories` has one `{"category_id", "total", "count"}` per category with at least one expense that month, active or archived, ordered by `total` descending.

#### Scenario: Summary
- **WHEN** an `IDR` household has, in `2026-10`, two `Groceries` expenses of `45000.00` and `30000.00` and one `Transport` expense of `20000.00`, and a member reads the summary for `2026-10`
- **THEN** `total` is `{"amount": "95000.00", "currency": "IDR"}` and `categories` is `Groceries` (`75000.00`, count 2) then `Transport` (`20000.00`, count 1)

#### Scenario: Empty month
- **WHEN** a member of an `IDR` household reads the summary for a month without expenses
- **THEN** `total` is `{"amount": "0.00", "currency": "IDR"}` and `categories` is empty

#### Scenario: Archived category still counted
- **WHEN** a category with expenses in the month is archived
- **THEN** the summary still includes that category's entry

#### Scenario: No rounding drift
- **WHEN** a month has three expenses of `0.10`
- **THEN** `total` is exactly `0.30`

#### Scenario: Invalid month
- **WHEN** a member reads the summary without `month`
- **THEN** the response is 422 with a `details` entry located at `["query", "month"]`

### Requirement: Field-specific error codes
When a 422 has a specific code (`currency_mismatch`, `category_not_found`, `category_archived`), the envelope's `error.code` SHALL be that code and `details` SHALL contain an entry for the field. A request that also fails schema validation SHALL be reported as `validation_error` with the schema errors only.

#### Scenario: Schema error reported first
- **WHEN** a member creates an expense with a `USD` amount and no `spent_on`
- **THEN** the response is 422 `validation_error` with a `details` entry located at `["body", "spent_on"]`

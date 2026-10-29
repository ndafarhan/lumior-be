# Tasks

## 1. Money input, errors, and month helpers

- [x] 1.1 Add `MoneyInput` to `core/money.py` per design Decision 3 (amount > 0, at most the currency's decimals, at most 12 integer digits, rejected rather than rounded; JSON numbers rejected) and a helper that formats a `Decimal` with exactly the currency's decimals; verify with unit tests in `tests/unit/test_money.py` for `"0"`, `"10.005"` in IDR, `"10.5"` in JPY, 13 digits, `"999999999999.99"`, a JSON number, and `"1200"` → `"1200"` (JPY) / `"45000"` → `"45000.00"` (IDR)
- [x] 1.2 Add `CategoryNotFoundError` (404), `ExpenseNotFoundError` (404), `CategoryNameTakenError` (409), and the 422 classes `CategoryNotFoundInBodyError`, `CategoryArchivedError`, `CurrencyMismatchError` to `core/errors.py` per design Decision 4; verify with unit tests in `tests/unit/test_errors.py` that each produces the contract's status, `code`, and `details` location (contract §6)
- [x] 1.3 Add the `Month` query type (`YYYY-MM`, month 01–12) and a function returning its half-open date range per design Decision 8; verify with unit tests for `2026-10`, `2026-12` (the range ends in January), `2026-13`, and `2026-1`

## 2. Data model and migration

- [x] 2.1 Add `Household.currency` and create `modules/expenses/models.py` (`ExpenseCategory` with a unique `(household_id, lower(name))` index, `Expense` with `NUMERIC(14,2)` amount and the list index) per design Decision 2; verify `uv run alembic check` reports the models match after 2.2
- [x] 2.2 Write one Alembic revision on top of `de50fb9d0bec`: add `households.currency` (filled with `IDR`, then the server default is dropped), create both tables, and seed the nine default categories for existing households with its own copy of the list; verify `uv run alembic upgrade head`, `downgrade -1`, and `upgrade head` succeed on the docker-compose database, and an integration test in `tests/integration/expenses/test_migration.py` shows a pre-existing household gets `IDR` and exactly the nine categories

## 3. Household currency and default categories (specs/households)

- [x] 3.1 Add `expenses/defaults.py` (`DEFAULT_CATEGORY_NAMES`, `add_default_categories`) and call it from `HouseholdService.create` per design Decision 1; verify with an integration test that a new household lists exactly the nine categories, none archived
- [x] 3.2 Add optional `currency` (default `IDR`, validated against `CURRENCY_PRECISION`) to the create request, and `currency` to `HouseholdView`/`HouseholdOut`, keeping `PATCH` name-only; verify with integration tests in `tests/integration/households/` for create with and without a currency, `XYZ` → 422 at `["body", "currency"]`, `currency` on list, rename, and accept-invite responses, and a rename that sends `currency` leaving it unchanged
- [x] 3.3 Update existing households tests and the frontend-flow test that compare whole household bodies; verify `uv run pytest tests/integration/households tests/integration/test_frontend_flow.py` passes

## 4. Expense categories (specs/expense-categories)

- [x] 4.1 Create the expenses repository, service, and schemas for categories, with the `expenses`-tagged router mounted under `/households` and registered in `api/v1.py`, implementing list (case-insensitive name order, archived included), create, and update (`name?`, `archived?`, omitted fields unchanged, explicit `null` → 422); verify with integration tests in `tests/integration/expenses/test_categories.py` for every scenario in specs/expense-categories except uniqueness
- [x] 4.2 Implement name uniqueness: a pre-check, plus a savepoint and `IntegrityError` → 409 `category_name_taken` with `details` at `["body", "name"]`, and renaming to its own name in another case allowed; verify with integration tests for the duplicate, archived-name, other-household, and same-name scenarios, and a concurrent-create test that gets one 201 and one 409
- [x] 4.3 Verify the access rules on category routes: 404 `household_not_found`, 403 `not_a_member` before body validation, 404 `category_not_found` for a malformed, unknown, or other household's `category_id`, and 405 for `DELETE`; covered by tests in `test_categories.py`

## 5. Expenses create, update, delete (specs/expenses)

- [x] 5.1 Implement `ExpenseOut` (amount formatted to the household currency) and the create and update request schemas (`note` trimmed, empty → `null`, max 500; PATCH distinguishes omitted from `null` via `model_fields_set`) per design Decision 5; verify with unit tests for the note normalization and the omitted-versus-`null` handling
- [x] 5.2 Implement `POST /expenses` with the service checks in the order of design Decision 4 (currency, then `spent_on` range against the clock, then category exists and is not archived); verify with integration tests in `tests/integration/expenses/test_expenses.py` for the create, amount, currency, date-range (with `FakeClock`), category, note, and "schema error reported first" scenarios
- [x] 5.3 Implement `PATCH /expenses/{expense_id}` (partial update, `updated_at` from the clock, `category_archived` only when `category_id` changes) and `DELETE /expenses/{expense_id}` (204); verify with integration tests for partial update, clearing the note, moving to an archived category, editing an expense whose category was archived later, delete then delete again, and 404 `expense_not_found` for a malformed, unknown, or other household's id

## 6. List and summary (specs/expenses)

- [x] 6.1 Implement the cursor encode/decode (URL-safe base64 JSON of `[spent_on, created_at, id]`, every decoding failure → 422 at `["query", "cursor"]`) per design Decision 6; verify with unit tests for round trip, garbage, wrong shape, and bad values
- [x] 6.2 Implement `GET /expenses` (month range, optional `category_id` filter with an unknown or malformed id → empty page, keyset seek, `limit + 1` fetch, `limit` 1–100 with default 50); verify with integration tests in `tests/integration/expenses/test_list.py` for month and order, invalid month, empty month, category filter, unknown filter, walking all pages with `limit` 2, the default limit with 51 expenses, a tampered cursor, `limit` 101, and an expense added between pages not causing a repeat
- [x] 6.3 Implement `GET /expense-summary` (grouped `SUM`/`COUNT`, ordered by total descending then `category_id`, `Decimal` grand total, zero total formatted to the currency) per design Decision 7; verify with integration tests in `tests/integration/expenses/test_summary.py` for the summary, empty month (IDR `"0.00"` and JPY `"0"`), archived category, no rounding drift, and invalid month scenarios

## 7. Contract and integration checks

- [x] 7.1 Regenerate `contracts/openapi.json` with `scripts/export_openapi.py` and extend `tests/unit/test_contract.py` with a parametrized check of every `expenses_*` operation (method, path, success status, documented error codes from contract §4 and §6) and `currency` on the household schema; verify `uv run pytest tests/unit/test_contract.py` passes
- [x] 7.2 Change the status line of `contracts/expenses.md` from draft to agreed, and add a short note on the choices from design.md's Open Questions so the frontend can confirm them; verify the document still matches the generated OpenAPI paths and `operationId`s
- [x] 7.3 Extend `tests/integration/test_frontend_flow.py` with the frontend's main path (create a household, list categories, add expenses, page through the month, read the summary, archive a category, edit an expense in it); verify it passes
- [x] 7.4 Run the full checks; verify `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, and `uv run pytest` all pass
- [x] 7.5 Align `contracts/openapi.json` with the frontend's draft so its generated types keep working, per design Decision 10 (schema names, `Role`, `ErrorDetail`, `{household_id}`, a single `Money`, no FastAPI default 422, no `null` for PATCH fields that refuse it); verify paths, `operationId`s, status codes, parameters, and schema names match `lumior-fe/contracts/openapi.json`, and that the frontend type-checks and its tests pass with types generated from the backend document

## Workflow follow-up

- Confirm the Open Questions in design.md with the frontend before or during review.
- Archive the change with `/opsx:archive expenses` after the PR is merged.

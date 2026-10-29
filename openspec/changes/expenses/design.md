# Design

## Context

The API contract is `contracts/expenses.md`, written by the frontend (see proposal.md, Why). The specs in this change restate it as testable requirements. Existing code this design builds on:

- **Household access:** `HouseholdAccess` (`src/lumior/api/deps.py`) already gives every `/households/{id}/...` route the 404 `household_not_found` / 403 `not_a_member` checks, and dependencies run before body validation. The new routes reuse it unchanged. The path parameter is named `household_id` for every household route (see Decision 10).
- **Money:** `src/lumior/core/money.py` had a `Money` dataclass, `CURRENCY_PRECISION`, `DecimalString` (rejects JSON numbers), and a `MoneySchema` API model. Storage is `NUMERIC(14,2)`, which matches the contract's 12 digits before the point. `MoneySchema` **rounded** to the currency's precision, but the contract requires extra decimals to be **rejected**.
- **Errors:** `AppError` subclasses carry `status_code`, `code`, and `details`, and `error_responses()` documents them in OpenAPI. Pydantic failures become 422 `validation_error` with `details` locations.
- **Transactions:** one session per request, committed before the response is sent. Unique-violation races are handled with a savepoint and `IntegrityError` (see `UserRepository.add`).
- **Time:** `ClockDep` gives an injectable UTC clock, and `FakeClock` in integration tests.
- **Operation IDs:** `<first tag>_<route name>`, so an `expenses`-tagged router with route names `list_categories`, `create`, `get_summary`, … yields the contract's `operationId`s.
- **Contract file:** `contracts/openapi.json` is generated from the app (`lumior.contract.render_openapi`, `scripts/export_openapi.py`), and a unit test checks it is current. The frontend's note says the machine-readable contract "is added" to it, but it has no expense paths yet. The backend regenerates it once the routes exist.

## Goals / Non-Goals

**Goals:**
- Match `contracts/expenses.md` exactly: paths, `operationId`s, shapes, status codes, and error codes.
- Exact money arithmetic end to end: `NUMERIC` in the database, `Decimal` in Python, strings in JSON.
- Stable pagination that does not skip or repeat rows when expenses are added between pages.

**Non-Goals:**
- Everything in the contract's "Out of scope" section (budgets, payer, receipts, recurring expenses, splitting, search, export, deleting categories, changing currency).
- Recording who created or edited an expense. The contract does not expose it, so no column is added now.
- Currencies with more than 2 decimal places (storage is `NUMERIC(14,2)`, and `CURRENCY_PRECISION` has none).

## Decisions

### 1. A new `expenses` module, with category seeding outside its service
`src/lumior/modules/expenses/` follows the households layout: `models.py`, `repository.py`, `service.py`, `schemas.py`, `router.py`, with one router tagged `expenses` mounted under `/households`. Category and expense logic live in one module because expenses validate against categories on every write.

Households must create the default categories in its own transaction, but the expenses service imports the households access context, so a call from households into the expenses service would create an import cycle. **Decision:** `expenses/defaults.py` holds `DEFAULT_CATEGORY_NAMES` and `add_default_categories(session, household_id)`, which depend only on `expenses/models.py`. `HouseholdService.create` calls it. The migration copies the list rather than importing it, so later edits to the list do not change an old migration.

*Alternative:* an event or hook that the expenses module registers on household creation. It is more indirect for a single caller.

### 2. Data model
- `households.currency`: `VARCHAR(3) NOT NULL`. The migration adds it with `server_default 'IDR'` to fill existing rows, then drops the server default, so the application always sets it explicitly.
- `expense_categories`: `id`, `household_id` (FK, `ON DELETE CASCADE`), `name VARCHAR(50)`, `archived BOOLEAN NOT NULL DEFAULT false`, `created_at`. Unique index on `(household_id, lower(name))` for case-insensitive uniqueness, which also covers archived rows.
- `expenses`: `id`, `household_id` (FK cascade), `category_id` (FK to `expense_categories`, `ON DELETE RESTRICT`, since categories are never deleted), `amount NUMERIC(14,2)`, `spent_on DATE`, `note VARCHAR(500) NULL`, `created_at`, `updated_at`. Index on `(household_id, spent_on, created_at, id)` to serve the month list and the cursor seek. All columns sort the same way, so PostgreSQL scans it backward for the descending order.
- The expense stores no currency. Its currency is always the household's, which cannot change, so a per-row copy could only disagree with it. Responses build `Money` from the household's currency.

*Alternative:* a composite FK `(household_id, category_id)` so the database guarantees an expense's category belongs to its household. The service already checks this on every write, and the extra unique constraint is not worth it now.

### 3. One strict `Money` model instead of rounding
The `Money` dataclass, `MoneySchema`, and the input model are one pydantic `Money` in `core/money.py`, because the frontend's generated types use a single `Money` schema for requests and responses. Parsed from a request, it **rejects** instead of rounding when the amount has more decimals than `currency_precision(currency)`, is `<= 0`, or has more than 12 integer digits, and writes an accepted amount with exactly the currency's decimals (`"12500"` → `"12500.00"`). Each failure is a Pydantic error on `amount.amount`, so the location is `["body", "amount", "amount"]` as the spec requires. The precision is checked against the request's own currency: when it differs from the household's, the request fails with `currency_mismatch` anyway. Values the server computes, such as a zero total, are built with `Money.of`, which rounds half-up and skips the request rules.

Output formats the amount with exactly the currency's decimals (`round_half_up(value, precision)` of a value that is already exact), so `JPY` gives `"1200"` and `IDR` gives `"45000.00"`, even though `NUMERIC(14,2)` returns `1200.00`.

### 4. Validation that needs the household, the clock, or the database
Pydantic covers types, lengths, trimming, `note` normalization (empty → `null`), the `month` pattern, `limit` 1–100, and the money rules above. The service then checks, in this order, and stops at the first failure:
1. `amount.currency` equals the household's currency → else 422 `currency_mismatch` (`["body", "amount", "currency"]`).
2. `spent_on` between `2000-01-01` and the clock's UTC date plus one day → else 422 `validation_error` (`["body", "spent_on"]`). The lower bound could be a Pydantic rule, but both bounds are kept together. The upper bound needs `ClockDep`.
3. `category_id` belongs to the household → else 422 `category_not_found`; and, if the expense is new or the category changes, it is not archived → else 422 `category_archived` (`["body", "category_id"]`).

New `AppError` subclasses: `CategoryNotFoundError` (404), `ExpenseNotFoundError` (404), `CategoryNameTakenError` (409), and `CategoryNotFoundInBodyError`, `CategoryArchivedError`, `CurrencyMismatchError` (422), each raised with its `details` entry. The 404 and 422 `category_not_found` share a code but need different status codes, so they are two classes.

Schema errors always win over service errors, because FastAPI validates the body before the handler runs. That is the behavior the spec's "Field-specific error codes" requirement records. The contract does not define an order for several service errors, so the order above is a backend choice.

`category_id` in the body is a `UUID` field, so a malformed one is 422 `validation_error`, while a well-formed one that is not the household's is `category_not_found`. Path ids (`category_id`, `expense_id`) are strings, as `household_id` already is, so a malformed path id is 404, not 422. A malformed `category_id` **query filter** returns an empty page, matching the contract's "not an error" rule for unknown filters.

### 5. PATCH semantics
`ExpenseUpdateRequest` and `CategoryUpdateRequest` use fields with defaults and read `model_fields_set`, so "omitted" and "explicit `null`" are distinguished: `"note": null` clears the note. An explicit `null` for `amount`, `spent_on`, `category_id`, `name`, or `archived` is 422, since those fields cannot be empty. `updated_at` is set from the clock on every successful expense PATCH, even when no value changes. An empty body `{}` is a 200 that still bumps `updated_at`, which keeps the rule simple.

Category rename uniqueness compares `lower(name)` with other categories only, so renaming `Groceries` to `groceries` works. A concurrent create or rename that loses the unique index race becomes 409 `category_name_taken` through a savepoint and `IntegrityError`, the same pattern as `email_taken`.

### 6. Cursor pagination
Keyset pagination on `(spent_on, created_at, id)` in descending order. `next_cursor` is URL-safe base64 of a compact JSON `[spent_on, created_at, id]` taken from the last item, and it is produced only when a row beyond `limit` exists, by fetching `limit + 1` rows. The seek uses a row-value comparison, `(spent_on, created_at, id) < (:s, :c, :i)`, which PostgreSQL can serve from the index. A cursor that does not decode, has the wrong shape, or has unparsable values is 422 `validation_error` at `["query", "cursor"]`.

The cursor is not signed. It holds only sort-key values, and the query is always scoped to the caller's household and month, so a crafted cursor can only move within data the caller can already see.

*Alternative:* offset pagination. It is simpler, but it repeats or skips rows when expenses are added or deleted while the user scrolls.

### 7. Summary
One grouped query over the month's expenses for the household: `SUM(amount)` and `COUNT(*)` per `category_id`, ordered by `SUM(amount) DESC, category_id`. The grand total is the sum of the per-category `Decimal` totals in Python, and `Decimal(0)` for an empty month. The tie-break on `category_id` is a backend choice for deterministic output, since the contract orders only by total.

### 8. Month handling
`month` is validated as `^\d{4}-(0[1-9]|1[0-2])$` and turned into a half-open range `[first day, first day of next month)`, so list and summary queries use `spent_on >= :start AND spent_on < :end` on the index.

### 9. Contract and OpenAPI
Routes declare their error codes with `error_responses(...)` as the households routes do. After implementation, `contracts/openapi.json` is regenerated with `scripts/export_openapi.py`, and `tests/unit/test_contract.py` gains a parametrized check of every `expenses_*` operation (method, path, success status, documented error codes) plus `currency` on `Household`. `contracts/expenses.md` is committed as is, with its status changed from draft to agreed.

### 10. OpenAPI names follow the frontend's generated types
The frontend generates TypeScript types from `contracts/openapi.json` with `openapi-typescript` and calls routes through `openapi-fetch`, so schema names and path parameter names are part of the contract, not only paths and `operationId`s. The backend therefore uses the frontend's names:
- Schema classes are named after the frontend's components (`Household`, `Member`, `Invite`, `InvitePreview`, `CreateHouseholdRequest`, `User`, `Session`, `Expense`, `ExpenseCategory`, `ExpenseCategoryTotal`, `ExpensePage`, `ExpenseSummary`, `CreateExpenseRequest`, `UpdateExpenseRequest`, `CreateExpenseCategoryRequest`, `UpdateExpenseCategoryRequest`, `Money`). Pydantic names a component after its class (a `title` does not change it), so routers import ORM models through their module (`models.Expense`) where names would clash.
- `Role` is its own component (the households `Role` enum), and `ErrorBody.details` is a required list of `ErrorDetail`.
- Every household route takes `{household_id}`, not `{id}`.
- FastAPI's default 422 entries (`HTTPValidationError`) are removed from the document, because every 422 uses the error envelope and each route that can return one declares it.
- PATCH fields that may be omitted but not `null` are documented without `null`, and `CreateHouseholdRequest.currency` without a `default` (a generator would otherwise make it required). Validation is unchanged.

`tests/unit/test_contract.py` pins the component names. Remaining differences from the frontend's draft are annotations only (`format: uuid`, `format: email`, `maxLength`, `pattern`), which do not change the generated types.

## Risks / Trade-offs

- [Seed list drift between `defaults.py` and the migration] → The migration keeps its own copy on purpose. An integration test checks that new households get exactly `DEFAULT_CATEGORY_NAMES`, and another checks the migrated database.
- [`lower(name)` uniqueness is not full Unicode case folding] → Fine for the names the frontend expects. It can move to `casefold()` plus a stored normalized column if needed.
- [Summary and list scan a month per request] → Covered by the `(household_id, spent_on, …)` index. Household-month volumes are small.
- [Contract drift with the frontend] → Every point where this design chose something the contract leaves open (service error order, the summary tie-break, a malformed body `category_id` as `validation_error`) is listed below for the frontend to confirm. None of them changes a documented success response.

## Migration Plan

1. One Alembic revision (down revision `de50fb9d0bec`): add `households.currency`, create `expense_categories` and `expenses`, then seed the nine categories for every existing household with `INSERT ... SELECT` over `households`, using `gen_random_uuid()` and the migration time as `created_at`.
2. Deploy the backend, then switch the frontend from its fake backend.
3. Rollback: the downgrade drops `expenses` and `expense_categories` and the `currency` column. All expense data is lost on downgrade, which is acceptable before the frontend goes live.

## Open Questions

To confirm with the frontend. None of these changes the specs' success paths or the task breakdown:
- Is the order of service-level 422 errors (currency, then date, then category) acceptable when several are wrong at once?
- Should a malformed `category_id` in a request body be `category_not_found` instead of `validation_error`?
- Is `category_id` a good tie-break for categories with equal totals in the summary, or would they prefer name order?

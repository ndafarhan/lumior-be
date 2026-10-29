# Proposal

## Why

The frontend `expenses` change (in `lumior-fe`) is being built against a fake backend that follows `contracts/expenses.md`. Households can sign in and share a space, but there is nowhere to record what they spend. This change implements that contract in `lumior-be` so the frontend can switch from the fake backend to the real API without changes.

## What Changes

- Households gain a fixed `currency` (ISO 4217, default `IDR`), chosen at creation and returned on every `Household`. Existing households are migrated to `IDR`.
- New household-scoped expense categories: list (active and archived), create, rename, archive, and restore. There is no delete. Every new household starts with nine default categories, and existing households are seeded with them by the migration.
- New household-scoped expenses: create, update (partial), delete, and a month-filtered, cursor-paginated list with an optional category filter.
- New monthly expense summary: the month total plus one total and count per category with spending, computed with `Decimal`.
- New error codes the frontend branches on: `category_not_found` (404 and 422), `expense_not_found`, `category_name_taken`, `category_archived`, `currency_mismatch`. For a 422 with one of these codes, the envelope `code` is that code and `details` points at the field.
- `contracts/openapi.json` is regenerated so it describes the new operations (`expenses_*`) and the `currency` field. The draft `contracts/expenses.md` from the frontend is committed as the agreed contract.

No breaking changes: `currency` is an added response field and an optional request field.

## Capabilities

### New Capabilities

- `expense-categories`: a household's categories for spending, including the default set, case-insensitive unique names, and archiving instead of deletion.
- `expenses`: recording, editing, deleting, and listing a household's expenses by month, plus the monthly summary by category, with the validation rules and error codes from the contract.

### Modified Capabilities

- `households`: the household representation gains `currency`; creating a household accepts an optional `currency` (default `IDR`) and also creates the default expense categories; renaming cannot change the currency.

## Impact

- **API:** new routes under `/api/v1/households/{household_id}/` (`expense-categories`, `expenses`, `expense-summary`); `POST /api/v1/households` accepts `currency`; every `Household` response gains `currency`.
- **Code:** new `src/lumior/modules/expenses/` module (models, repository, service, schemas, router), registered in `src/lumior/api/v1.py`; changes to the households module (model, schema, create) and new error classes in `src/lumior/core/errors.py`; a strict money input type, since the current `MoneySchema` rounds instead of rejecting extra decimals.
- **Database:** one Alembic migration adding `households.currency`, `expense_categories`, and `expenses`, and seeding default categories for existing households.
- **Contracts and tests:** regenerated `contracts/openapi.json`, `tests/unit/test_contract.py` extended for the new operations, and new integration tests under `tests/integration/expenses/`.
- **Frontend:** none beyond switching to the real backend. Any place where this plan departs from `contracts/expenses.md` is listed in `design.md` so it can be agreed with the frontend first.

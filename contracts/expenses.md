# Expenses: proposed API contract

Status: **agreed, implemented in `lumior-be`** by the backend change `openspec/changes/expenses`. Proposed by the frontend change `openspec/changes/expenses` in `lumior-fe`. Section 8 lists the choices the backend made where this document is silent.

The frontend is being built against this contract using its fake backend. Please treat it as the input to the backend `expenses` change. If the backend needs something different, change this document (or tell the frontend) before implementing, so both sides stay on one contract. The machine-readable version is added to `contracts/openapi.json`.

This contract builds on `contracts/auth-and-households.md`. Everything there still applies.

## 1. Conventions (unchanged)

- All endpoints are under `/api/v1`, require `Authorization: Bearer <access_token>`, and are described in `/api/v1/openapi.json` with the `operationId`s below (module `expenses`).
- Every non-2xx response uses the envelope `{"error": {"code", "message", "details", "request_id"}}`. The frontend branches on `error.code`, so the codes below are part of the contract.
- Validation failures are HTTP 422, with one `details` entry per field (`{"location": ["body", "<field>"] | ["query", "<param>"], "reason", "type"}`). The `code` is `validation_error` unless a more specific code is listed below.
- Money is `{"amount": "<decimal string>", "currency": "<ISO 4217>"}`, with the amount as a JSON string, rounded to the currency's precision (`CURRENCY_PRECISION`). Never a JSON number.
- Dates without a time (`spent_on`) are `YYYY-MM-DD`. Months are `YYYY-MM`. Timestamps are ISO 8601 in UTC.

## 2. Change to households: currency

`Household` gains a required `currency` field:

```jsonc
{ "id": "uuid", "name": "Rumah Bandung", "role": "owner", "member_count": 3, "currency": "IDR" }
```

| Method & path             | operationId         | Body                | Success             | Errors |
| ------------------------- | ------------------- | ------------------- | ------------------- | ------ |
| `POST /api/v1/households` | `households_create` | `{name, currency?}` | **201** `Household` | 422    |

- `currency` is optional and defaults to `IDR`. It must be a key of `CURRENCY_PRECISION`. Otherwise return 422 with a detail for `currency`.
- The currency cannot be changed afterwards. `PATCH /api/v1/households/{id}` keeps accepting only `{name}`.
- Every endpoint that returns a `Household` (list, create, update, accept invite) includes `currency`.
- **Migration:** existing households get `IDR`.

## 3. Data shapes

```jsonc
// ExpenseCategory
{ "id": "uuid", "name": "Groceries", "archived": false }

// Expense
{
  "id": "uuid",
  "amount": { "amount": "45000.00", "currency": "IDR" },
  "spent_on": "2026-10-03",
  "category_id": "uuid",
  "note": "Weekly market",            // string or null
  "created_at": "2026-10-03T08:15:00Z",
  "updated_at": "2026-10-03T08:15:00Z"
}

// ExpensePage
{ "items": [Expense], "next_cursor": "opaque string" }   // next_cursor is null on the last page

// ExpenseSummary
{
  "month": "2026-10",
  "total": { "amount": "95000.00", "currency": "IDR" },
  "categories": [
    { "category_id": "uuid", "total": { "amount": "75000.00", "currency": "IDR" }, "count": 2 }
  ]
}
```

- An expense returns only `category_id`. The frontend looks up the name in the categories list, which includes archived categories.
- `note` is stored trimmed. An empty or whitespace-only note is stored as `null`.

## 4. Endpoints

All paths below are relative to `/api/v1/households/{household_id}`. Any member of the household (owner or member) may call every one of them.

### Categories

| Method & path                             | operationId                | Body                 | Success                     | Errors                                                   |
| ----------------------------------------- | -------------------------- | -------------------- | --------------------------- | -------------------------------------------------------- |
| `GET /expense-categories`                 | `expenses_list_categories` |                      | **200** `ExpenseCategory[]` |                                                          |
| `POST /expense-categories`                | `expenses_create_category` | `{name}`             | **201** `ExpenseCategory`   | 409 `category_name_taken`, 422                           |
| `PATCH /expense-categories/{category_id}` | `expenses_update_category` | `{name?, archived?}` | **200** `ExpenseCategory`   | 404 `category_not_found`, 409 `category_name_taken`, 422 |

- The list contains active **and** archived categories, ordered by name, case-insensitively.
- Archiving (`{"archived": true}`) and restoring (`{"archived": false}`) leave existing expenses unchanged.
- There is no delete endpoint. Archiving is the only way to retire a category.
- **Default categories:** every new household is created with these nine categories, in one transaction with the household: `Groceries`, `Dining out`, `Transport`, `Utilities`, `Housing`, `Health`, `Education`, `Entertainment`, `Other`. **Migration:** seed them for every existing household.

### Expenses

| Method & path                   | operationId       | Body / query                                                   | Success               | Errors                       |
| ------------------------------- | ----------------- | -------------------------------------------------------------- | --------------------- | ---------------------------- |
| `GET /expenses`                 | `expenses_list`   | query: `month` (required), `category_id?`, `cursor?`, `limit?` | **200** `ExpensePage` | 422                          |
| `POST /expenses`                | `expenses_create` | `{amount, spent_on, category_id, note?}`                       | **201** `Expense`     | 422 (see section 6)          |
| `PATCH /expenses/{expense_id}`  | `expenses_update` | any subset of the create fields                                | **200** `Expense`     | 404 `expense_not_found`, 422 |
| `DELETE /expenses/{expense_id}` | `expenses_delete` |                                                                | **204**               | 404 `expense_not_found`      |

- `GET /expenses` returns the expenses whose `spent_on` falls in `month`, optionally only those with `category_id`. The order is `spent_on` descending, then `created_at` descending, then `id`, so it is stable across pages.
- `limit` is 1–100 and defaults to 50. `cursor` is the `next_cursor` of the previous page. The frontend treats it as opaque. An invalid cursor is 422 with a detail for `cursor`.
- A `category_id` filter that is not one of the household's categories returns an empty page, not an error.
- `PATCH` with `"note": null` clears the note. Omitted fields stay unchanged.
- An `expense_id` that does not exist **or belongs to another household** is 404 `expense_not_found`.

### Summary

| Method & path          | operationId            | Query              | Success                  | Errors |
| ---------------------- | ---------------------- | ------------------ | ------------------------ | ------ |
| `GET /expense-summary` | `expenses_get_summary` | `month` (required) | **200** `ExpenseSummary` | 422    |

- `total` is the sum of all expenses of the month, in the household currency, `"0.00"` (or `"0"` for zero-decimal currencies) when there are none.
- `categories` has one entry per category with at least one expense in the month, active or archived, ordered by `total` descending. Categories without expenses are left out.
- The sums are computed with `Decimal`. The frontend does no arithmetic on money and shows these values as they are.
- The path is `/expense-summary`, not `/expenses/summary`, so it never collides with `/expenses/{expense_id}`.

## 5. Validation rules

The frontend checks the starred rules before sending. The backend must enforce all of them.

| Field                | Rule                                                                                                                                                                          |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name` (category) \* | 1–50 characters after trimming. Unique within the household, ignoring case, including archived categories: 409 `category_name_taken`                                          |
| `amount.amount` \*   | decimal string, greater than 0, at most the currency's decimal places, at most 12 digits before the decimal point                                                             |
| `amount.currency`    | must equal the household's currency: 422 `currency_mismatch` (location `["body", "amount", "currency"]`)                                                                      |
| `spent_on` \*        | valid date, not before `2000-01-01`, not more than **one day after** the server's current UTC date (the user's local "today" may be ahead of UTC)                             |
| `category_id` \*     | one of the household's categories: otherwise 422 `category_not_found`. Must not be archived: 422 `category_archived`, unless it is the expense's current category (see below) |
| `note` \*            | optional, at most 500 characters after trimming                                                                                                                               |
| `month` (query)      | `YYYY-MM` with month 01–12                                                                                                                                                    |

`category_archived` applies only when a create sets an archived category, or an update **changes** `category_id` to an archived one. Updating other fields of an expense whose category was archived later must succeed, including when the request repeats the same `category_id`.

## 6. Error codes used by the frontend

In addition to those in `contracts/auth-and-households.md` (`unauthorized`, `not_a_member`, `household_not_found`, `validation_error`):

| HTTP | `code`                | Where                                       | Field (`details.location`)       |
| ---- | --------------------- | ------------------------------------------- | -------------------------------- |
| 404  | `category_not_found`  | `PATCH /expense-categories/{category_id}`   |                                  |
| 404  | `expense_not_found`   | `PATCH` and `DELETE /expenses/{expense_id}` |                                  |
| 409  | `category_name_taken` | create and rename category                  | `["body", "name"]`               |
| 422  | `category_not_found`  | create and update expense                   | `["body", "category_id"]`        |
| 422  | `category_archived`   | create and update expense                   | `["body", "category_id"]`        |
| 422  | `currency_mismatch`   | create and update expense                   | `["body", "amount", "currency"]` |

- Every path under `/households/{household_id}/` checks membership first: 404 `household_not_found` if the household does not exist, 403 `not_a_member` if the user is not a member. The frontend relies on this to switch households when access is lost, so please use exactly these codes here too.
- For a 422 with a specific code, put the same code in the envelope's `code` and include the field in `details`, so the frontend can show the message next to the field.

## 7. Out of scope for this contract

Budgets and spending limits, who paid for an expense, stores and merchants, receipts and attachments, recurring expenses, splitting an expense, searching notes, export, deleting categories, and changing a household's currency. These can be added later without breaking anything here.

## 8. Backend choices to confirm

The backend follows everything above. Where this document leaves something open, it chose the following. None of them changes a success response. Please say if the frontend needs something different.

- **Several invalid fields at once.** Schema errors (types, required fields, lengths, amount format) are reported first, all together, as `validation_error`. Only when the schema is valid are the remaining rules checked, in this order, stopping at the first failure: `currency_mismatch`, then the `spent_on` range (`validation_error` at `["body", "spent_on"]`), then `category_not_found` / `category_archived`.
- **Malformed `category_id` in a body.** A value that is not a UUID is `validation_error` at `["body", "category_id"]`. A well-formed UUID that is not one of the household's categories is `category_not_found`. In the list's `category_id` query filter, both give an empty page.
- **Summary ties.** Categories with equal totals are ordered by `category_id`.
- **PATCH with `null`.** Only `note` may be `null` (it clears the note). An explicit `null` for any other field is `validation_error` for that field. An empty PATCH body `{}` is a 200 that leaves the values unchanged and updates `updated_at`.

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from lumior.api.deps import ExpenseServiceDep, HouseholdAccess
from lumior.core.clock import ClockDep
from lumior.core.errors import (
    CategoryArchivedError,
    CategoryNameTakenError,
    CategoryNotFoundError,
    CategoryNotFoundInBodyError,
    CurrencyMismatchError,
    ExpenseNotFoundError,
    HouseholdNotFoundError,
    NotAMemberError,
    UnauthorizedError,
    ValidationError,
    error_responses,
)
from lumior.core.money import Money
from lumior.core.validation import Month
from lumior.modules.expenses import models
from lumior.modules.expenses.schemas import (
    CreateExpenseCategoryRequest,
    CreateExpenseRequest,
    Expense,
    ExpenseCategory,
    ExpenseCategoryTotal,
    ExpensePage,
    ExpenseSummary,
    UpdateExpenseCategoryRequest,
    UpdateExpenseRequest,
)
from lumior.modules.expenses.service import ExpenseChanges

ACCESS_ERRORS = (NotAMemberError, HouseholdNotFoundError)
EXPENSE_BODY_ERRORS = (
    ValidationError,
    CurrencyMismatchError,
    CategoryNotFoundInBodyError,
    CategoryArchivedError,
)

# Mounted under /households: every route is household-scoped and any member may call it.
expenses_router = APIRouter(
    prefix="/households",
    tags=["expenses"],
    responses=error_responses(UnauthorizedError),
)


def category_out(category: models.ExpenseCategory) -> ExpenseCategory:
    return ExpenseCategory(id=category.id, name=category.name, archived=category.archived)


def expense_out(expense: models.Expense, currency: str) -> Expense:
    return Expense(
        id=expense.id,
        amount=Money.of(expense.amount, currency),
        spent_on=expense.spent_on,
        category_id=expense.category_id,
        note=expense.note,
        created_at=expense.created_at,
        updated_at=expense.updated_at,
    )


@expenses_router.get(
    "/{household_id}/expense-categories",
    name="list_categories",
    description="All categories, active and archived, ordered by name (case-insensitive).",
    responses=error_responses(*ACCESS_ERRORS),
)
async def list_categories(
    access: HouseholdAccess, service: ExpenseServiceDep
) -> list[ExpenseCategory]:
    return [category_out(c) for c in await service.list_categories(access)]


@expenses_router.post(
    "/{household_id}/expense-categories",
    name="create_category",
    status_code=status.HTTP_201_CREATED,
    description="Create a category. Names are unique in the household, ignoring case.",
    responses=error_responses(*ACCESS_ERRORS, CategoryNameTakenError, ValidationError),
)
async def create_category(
    body: CreateExpenseCategoryRequest,
    access: HouseholdAccess,
    service: ExpenseServiceDep,
    clock: ClockDep,
) -> ExpenseCategory:
    return category_out(await service.create_category(access, body.name, now=clock()))


@expenses_router.patch(
    "/{household_id}/expense-categories/{category_id}",
    name="update_category",
    description=(
        "Rename, archive (`archived: true`), or restore (`archived: false`) a category. "
        "Existing expenses are unchanged. Categories cannot be deleted."
    ),
    responses=error_responses(
        *ACCESS_ERRORS, CategoryNotFoundError, CategoryNameTakenError, ValidationError
    ),
)
async def update_category(
    category_id: str,
    body: UpdateExpenseCategoryRequest,
    access: HouseholdAccess,
    service: ExpenseServiceDep,
) -> ExpenseCategory:
    category = await service.update_category(
        access, category_id, name=body.name, archived=body.archived
    )
    return category_out(category)


MonthQuery = Annotated[Month, Query(description="`YYYY-MM`.", examples=["2026-10"])]


@expenses_router.get(
    "/{household_id}/expenses",
    name="list",
    description=(
        "Expenses whose `spent_on` is in `month`, ordered by `spent_on`, then `created_at`, "
        "newest first. A `category_id` that is not one of the household's gives an empty page."
    ),
    responses=error_responses(*ACCESS_ERRORS, ValidationError),
)
async def list_expenses(
    month: MonthQuery,
    access: HouseholdAccess,
    service: ExpenseServiceDep,
    category_id: str | None = None,
    cursor: Annotated[str | None, Query(description="`next_cursor` of the previous page.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ExpensePage:
    page = await service.list_expenses(
        access, month, category_id=category_id, cursor=cursor, limit=limit
    )
    currency = access.household.currency
    return ExpensePage(
        items=[expense_out(e, currency) for e in page.items], next_cursor=page.next_cursor
    )


@expenses_router.post(
    "/{household_id}/expenses",
    name="create",
    status_code=status.HTTP_201_CREATED,
    description="Record an expense in the household's currency.",
    responses=error_responses(*ACCESS_ERRORS, *EXPENSE_BODY_ERRORS),
)
async def create_expense(
    body: CreateExpenseRequest, access: HouseholdAccess, service: ExpenseServiceDep, clock: ClockDep
) -> Expense:
    expense = await service.create_expense(
        access,
        amount=body.amount,
        spent_on=body.spent_on,
        category_id=body.category_id,
        note=body.note,
        now=clock(),
    )
    return expense_out(expense, access.household.currency)


@expenses_router.patch(
    "/{household_id}/expenses/{expense_id}",
    name="update",
    description="Change any of the expense's fields. `note: null` clears the note.",
    responses=error_responses(*ACCESS_ERRORS, ExpenseNotFoundError, *EXPENSE_BODY_ERRORS),
)
async def update_expense(
    expense_id: str,
    body: UpdateExpenseRequest,
    access: HouseholdAccess,
    service: ExpenseServiceDep,
    clock: ClockDep,
) -> Expense:
    changes = ExpenseChanges(
        amount=body.amount,
        spent_on=body.spent_on,
        category_id=body.category_id,
        note=body.note,
        note_sent="note" in body.model_fields_set,
    )
    expense = await service.update_expense(access, expense_id, changes, now=clock())
    return expense_out(expense, access.household.currency)


@expenses_router.delete(
    "/{household_id}/expenses/{expense_id}",
    name="delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(*ACCESS_ERRORS, ExpenseNotFoundError),
)
async def delete_expense(
    expense_id: str, access: HouseholdAccess, service: ExpenseServiceDep
) -> Response:
    await service.delete_expense(access, expense_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Not /expenses/summary, so it never collides with /expenses/{expense_id}.
@expenses_router.get(
    "/{household_id}/expense-summary",
    name="get_summary",
    description="The month's total and, per category with spending, its total and count.",
    responses=error_responses(*ACCESS_ERRORS, ValidationError),
)
async def get_summary(
    month: MonthQuery, access: HouseholdAccess, service: ExpenseServiceDep
) -> ExpenseSummary:
    summary = await service.summarize(access, month)
    currency = access.household.currency
    return ExpenseSummary(
        month=month,
        total=Money.of(summary.total, currency),
        categories=[
            ExpenseCategoryTotal(
                category_id=c.category_id, total=Money.of(c.total, currency), count=c.count
            )
            for c in summary.categories
        ],
    )

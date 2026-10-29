import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from lumior.core.money import Money
from lumior.modules.expenses.models import CATEGORY_NAME_MAX_LENGTH, NOTE_MAX_LENGTH

CategoryName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=CATEGORY_NAME_MAX_LENGTH),
]


def reject_null(value: Any) -> Any:
    """For PATCH fields that may be omitted but not cleared. Pydantic does not validate
    defaults, so this only runs on values the client sent."""
    if value is None:
        raise ValueError("may be omitted but not null")
    return value


def not_nullable_in_schema(*fields: str) -> ConfigDict:
    """Document `fields` without `null`, since `reject_null` refuses it.

    They stay `T | None` at runtime: pydantic treats that as an optional field and reports
    errors at the field, while a union with a schema-skipped `None` would report one error
    location per union member."""

    def drop_null(schema: dict[str, Any]) -> None:
        for name in fields:
            prop = schema["properties"][name]
            (kept,) = [s for s in prop.pop("anyOf") if s != {"type": "null"}]
            prop.update(kept)

    return ConfigDict(json_schema_extra=drop_null)


class ExpenseCategory(BaseModel):
    id: uuid.UUID
    name: str
    archived: bool


class CreateExpenseCategoryRequest(BaseModel):
    name: CategoryName


class UpdateExpenseCategoryRequest(BaseModel):
    model_config = not_nullable_in_schema("name", "archived")

    name: CategoryName | None = None
    archived: bool | None = None

    _not_null = field_validator("name", "archived")(reject_null)


def _normalize_note(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) > NOTE_MAX_LENGTH:
        raise ValueError(f"note must be at most {NOTE_MAX_LENGTH} characters after trimming")
    return value or None


Note = Annotated[
    str | None,
    AfterValidator(_normalize_note),
    Field(description=f"Stored trimmed; empty becomes null. At most {NOTE_MAX_LENGTH} characters."),
]


class Expense(BaseModel):
    id: uuid.UUID
    amount: Money
    spent_on: date
    category_id: uuid.UUID
    note: str | None
    created_at: datetime
    updated_at: datetime


class CreateExpenseRequest(BaseModel):
    amount: Money
    spent_on: date
    category_id: uuid.UUID
    note: Note = None


class UpdateExpenseRequest(BaseModel):
    """Omitted fields stay unchanged. Only `note` may be `null`, which clears it."""

    model_config = not_nullable_in_schema("amount", "spent_on", "category_id")

    amount: Money | None = None
    spent_on: date | None = None
    category_id: uuid.UUID | None = None
    note: Note = None

    _not_null = field_validator("amount", "spent_on", "category_id")(reject_null)


class ExpensePage(BaseModel):
    items: list[Expense]
    next_cursor: str | None = Field(
        description="Pass as `cursor` for the next page. `null` on the last page. Opaque."
    )


class ExpenseCategoryTotal(BaseModel):
    category_id: uuid.UUID
    total: Money
    count: int


class ExpenseSummary(BaseModel):
    month: str
    total: Money
    categories: list[ExpenseCategoryTotal] = Field(
        description="Categories with spending in the month, active or archived, largest first."
    )

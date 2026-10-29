import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lumior.core.money import CurrencyCode
from lumior.core.validation import Name
from lumior.modules.households.models import DEFAULT_CURRENCY, Role


class HouseholdNameRequest(BaseModel):
    name: Name


def _omit_currency_default(schema: dict[str, Any]) -> None:
    # Type generators such as openapi-typescript treat a field with a `default` as always
    # present, which would make clients send `currency`. It is optional; the description
    # names the default.
    schema["properties"]["currency"].pop("default")


class CreateHouseholdRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra=_omit_currency_default)

    name: Name
    currency: CurrencyCode = Field(
        DEFAULT_CURRENCY,
        description=f"ISO 4217, `{DEFAULT_CURRENCY}` when omitted. Fixed for the life of the "
        "household.",
    )


class Household(BaseModel):
    """A household from the current user's point of view."""

    id: uuid.UUID
    name: str
    role: Role = Field(description="The current user's role in this household.")
    member_count: int
    currency: str = Field(description="ISO 4217. Every amount in the household uses it.")


class Member(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: Role


class Invite(BaseModel):
    code: str = Field(description="URL-safe. The frontend links to `/invite/<code>`.")
    expires_at: datetime


class InvitePreview(BaseModel):
    household_id: uuid.UUID
    household_name: str
    invited_by: str = Field(description="Name of the user who created the invite.")
    expires_at: datetime
    already_member: bool

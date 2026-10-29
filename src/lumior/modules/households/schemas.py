import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from lumior.core.validation import Name

RoleName = Literal["owner", "member"]


class HouseholdNameRequest(BaseModel):
    name: Name


class HouseholdOut(BaseModel):
    """A household from the current user's point of view."""

    id: uuid.UUID
    name: str
    role: RoleName = Field(description="The current user's role in this household.")
    member_count: int


class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: RoleName


class InviteOut(BaseModel):
    code: str = Field(description="URL-safe. The frontend links to `/invite/<code>`.")
    expires_at: datetime


class InvitePreviewOut(BaseModel):
    household_id: uuid.UUID
    household_name: str
    invited_by: str = Field(description="Name of the user who created the invite.")
    expires_at: datetime
    already_member: bool

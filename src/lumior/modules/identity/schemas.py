import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from lumior.core.validation import Name

Password = Annotated[str, Field(min_length=8, max_length=128)]
Email = Annotated[EmailStr, Field(max_length=320), AfterValidator(str.lower)]


class RegisterRequest(BaseModel):
    name: Name
    email: Email
    password: Password


class LoginRequest(BaseModel):
    # Not validated beyond being a string: any mismatch is `invalid_credentials`.
    email: str
    password: str


class UpdateMeRequest(BaseModel):
    name: Name


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: Password


class User(BaseModel):
    id: uuid.UUID
    email: str
    name: str


class Session(BaseModel):
    access_token: str = Field(description="Opaque bearer token for the `Authorization` header.")
    token_type: Literal["bearer"]
    expires_in: int = Field(description="Access token lifetime in seconds (informational).")
    user: User

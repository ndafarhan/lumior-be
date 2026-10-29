"""Application settings loaded from environment variables and `.env`."""

from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

SECRET_KEY_PLACEHOLDER = "change-me"  # noqa: S105 - rejected outside development/test
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Environment = "development"
    database_url: str = Field(min_length=1)
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    log_level: LogLevel = "INFO"
    # Signs access tokens. The placeholder is accepted only in development and test.
    secret_key: SecretStr = SecretStr(SECRET_KEY_PLACEHOLDER)
    access_token_ttl_seconds: int = Field(default=900, gt=0)
    refresh_token_ttl_days: int = Field(default=30, gt=0)
    refresh_grace_seconds: int = Field(default=30, ge=0)
    invite_ttl_days: int = Field(default=7, gt=0)
    refresh_cookie_name: str = Field(default="lumior_refresh", min_length=1)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def _reject_wildcard(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("wildcard origin is not allowed because credentials are enabled")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _require_real_secret_key(self) -> Self:
        if self.environment in ("staging", "production"):
            key = self.secret_key.get_secret_value()
            if key == SECRET_KEY_PLACEHOLDER or len(key) < MIN_SECRET_KEY_LENGTH:
                raise ValueError(
                    f"secret_key must be set to at least {MIN_SECRET_KEY_LENGTH} characters "
                    f"in {self.environment}"
                )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def secure_cookies(self) -> bool:
        # Local development and tests talk plain http, where browsers drop Secure cookies.
        return self.environment not in ("development", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()

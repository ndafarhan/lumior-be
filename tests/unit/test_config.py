import pytest
from pydantic import ValidationError

from lumior.core.config import Settings

ENV_VARS = (
    "ENVIRONMENT",
    "DATABASE_URL",
    "CORS_ALLOWED_ORIGINS",
    "LOG_LEVEL",
    "SECRET_KEY",
    "ACCESS_TOKEN_TTL_SECONDS",
    "REFRESH_TOKEN_TTL_DAYS",
    "REFRESH_GRACE_SECONDS",
    "INVITE_TTL_DAYS",
    "REFRESH_COOKIE_NAME",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")

    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.database_url == "postgresql+asyncpg://u:p@localhost/db"
    assert settings.cors_allowed_origins == []
    assert settings.log_level == "INFO"
    assert settings.secret_key.get_secret_value()
    assert not settings.is_production


def test_missing_database_url_fails() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_comma_separated_origins_are_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, https://app.example ,")

    settings = Settings(_env_file=None)

    assert settings.cors_allowed_origins == ["http://localhost:3000", "https://app.example"]


def test_wildcard_origin_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ValidationError, match="wildcard"):
        Settings(_env_file=None)


def test_invalid_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("ENVIRONMENT", "prod")

    with pytest.raises(ValidationError, match="environment"):
        Settings(_env_file=None)


def test_auth_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")

    settings = Settings(_env_file=None)

    assert settings.access_token_ttl_seconds == 900
    assert settings.refresh_token_ttl_days == 30
    assert settings.refresh_grace_seconds == 30
    assert settings.invite_ttl_days == 7
    assert settings.refresh_cookie_name == "lumior_refresh"


@pytest.mark.parametrize("environment", ["development", "test"])
def test_placeholder_secret_key_allowed_locally(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("ENVIRONMENT", environment)

    settings = Settings(_env_file=None)

    assert settings.secret_key.get_secret_value() == "change-me"
    assert not settings.secure_cookies


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("secret_key", [None, "change-me", "x" * 31])
def test_weak_secret_key_rejected_when_deployed(
    monkeypatch: pytest.MonkeyPatch, environment: str, secret_key: str | None
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("ENVIRONMENT", environment)
    if secret_key is not None:
        monkeypatch.setenv("SECRET_KEY", secret_key)

    with pytest.raises(ValidationError, match="secret_key"):
        Settings(_env_file=None)


def test_strong_secret_key_accepted_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)

    settings = Settings(_env_file=None)

    assert settings.is_production
    assert settings.secure_cookies

from __future__ import annotations

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AthenaSettings(BaseSettings):
    """Environment-only configuration for a registered athenahealth app."""

    model_config = SettingsConfigDict(env_prefix="ATHENA_", case_sensitive=False)

    practice_id: str
    client_id: str
    client_secret: SecretStr
    base_url: str = "https://api.preview.platform.athenahealth.com/v1"
    token_path: str = "token"
    scope: str | None = None
    timeout_seconds: float = 20.0

    @field_validator("practice_id", "client_id")
    @classmethod
    def required_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("token_path")
    @classmethod
    def normalize_token_path(cls, value: str) -> str:
        return value.strip("/")

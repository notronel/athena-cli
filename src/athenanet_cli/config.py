from __future__ import annotations

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AthenaSettings(BaseSettings):
    """Environment-only configuration for a FHIR R4 SMART v2 service app."""

    model_config = SettingsConfigDict(env_prefix="ATHENA_", case_sensitive=False, env_file=".env", env_file_encoding="utf-8", extra="ignore")

    client_id: str
    client_secret: SecretStr
    fhir_base_url: str = "https://api.preview.platform.athenahealth.com/fhir/r4"
    token_url: str | None = None
    scope: str = "system/Patient.rs system/DocumentReference.rs"
    timeout_seconds: float = 20.0

    @field_validator("client_id")
    @classmethod
    def required_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("fhir_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def smart_configuration_url(self) -> str:
        return f"{self.fhir_base_url}/.well-known/smart-configuration"

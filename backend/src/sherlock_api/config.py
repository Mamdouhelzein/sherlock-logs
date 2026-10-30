"""Validated configuration. Authentication remains disabled until configured."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    supabase_url: str = ""
    supabase_publishable_key: SecretStr = SecretStr("")

    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "*" in parsed.hostname
            or any(character.isspace() for character in parsed.hostname)
            or not (
                parsed.scheme == "https"
                or (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"})
            )
        ):
            raise ValueError(
                "SUPABASE_URL must be an HTTPS origin (HTTP allowed only on localhost)"
            )
        _ = parsed.port
        return value

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, value: str) -> str:
        origins = [origin.strip().rstrip("/") for origin in value.split(",")]
        if not origins or any(not origin for origin in origins):
            raise ValueError("ALLOWED_ORIGINS must contain explicit comma-separated origins")
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or "*" in parsed.hostname
                or any(character.isspace() for character in parsed.hostname)
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Each allowed origin must be an HTTP(S) origin without a path")
            # Accessing port also rejects malformed and out-of-range ports.
            _ = parsed.port
        return ",".join(dict.fromkeys(origins))

    @model_validator(mode="after")
    def require_production_https(self) -> "Settings":
        if self.environment == "production" and any(
            not origin.startswith("https://") for origin in self.origins
        ):
            raise ValueError("Production origins must use HTTPS")
        key = self.supabase_publishable_key.get_secret_value()
        if bool(self.supabase_url) != bool(key):
            raise ValueError("Set both SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY, or neither")
        if key and not key.startswith("sb_publishable_"):
            raise ValueError("Use a publishable key, never a secret or service-role key")
        if self.environment == "production" and self.supabase_url.startswith("http:"):
            raise ValueError("Production Supabase must use HTTPS")
        return self

    @property
    def auth_configured(self) -> bool:
        return bool(self.supabase_url)

    @property
    def origins(self) -> list[str]:
        return self.allowed_origins.split(",")

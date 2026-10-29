"""Validated application configuration; no database credentials are needed in Step 2."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

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
        return self

    @property
    def origins(self) -> list[str]:
        return self.allowed_origins.split(",")

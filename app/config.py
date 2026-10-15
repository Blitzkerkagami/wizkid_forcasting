from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv


load_dotenv()


class ConfigurationError(ValueError):
    """Raised when required server configuration is missing or unsafe."""


@dataclass(frozen=True, slots=True)
class Settings:
    supabase_url: str
    supabase_secret_key: str
    forecast_job_token: str
    cron_secret: str = ""
    forecast_valid_days: int = 7
    forecast_page_size: int = 500

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            supabase_url=os.getenv("SUPABASE_URL", "").strip().rstrip("/"),
            supabase_secret_key=os.getenv("SUPABASE_SECRET_KEY", "").strip(),
            forecast_job_token=os.getenv("FORECAST_JOB_TOKEN", "").strip(),
            cron_secret=os.getenv("CRON_SECRET", "").strip(),
            forecast_valid_days=_read_int("FORECAST_VALID_DAYS", 7),
            forecast_page_size=_read_int("FORECAST_PAGE_SIZE", 500),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        parsed = urlparse(self.supabase_url)
        is_local = parsed.hostname in {"localhost", "127.0.0.1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and is_local):
            raise ConfigurationError(
                "SUPABASE_URL must use HTTPS (HTTP is allowed only for localhost)."
            )
        if not parsed.netloc:
            raise ConfigurationError("SUPABASE_URL is not a valid project URL.")
        if not self.supabase_secret_key.startswith("sb_secret_"):
            raise ConfigurationError(
                "SUPABASE_SECRET_KEY must be a server-only sb_secret_ key."
            )
        if len(self.forecast_job_token) < 32:
            raise ConfigurationError(
                "FORECAST_JOB_TOKEN must contain at least 32 characters."
            )
        if self.cron_secret and len(self.cron_secret) < 32:
            raise ConfigurationError(
                "CRON_SECRET must contain at least 32 characters when configured."
            )
        if not 1 <= self.forecast_valid_days <= 30:
            raise ConfigurationError("FORECAST_VALID_DAYS must be between 1 and 30.")
        if not 1 <= self.forecast_page_size <= 1000:
            raise ConfigurationError("FORECAST_PAGE_SIZE must be between 1 and 1000.")


def _read_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc


from __future__ import annotations

import unittest

from app.config import ConfigurationError, Settings


class SettingsTests(unittest.TestCase):
    def test_accepts_secure_server_configuration(self) -> None:
        settings = Settings(
            supabase_url="https://example.supabase.co",
            supabase_secret_key="sb_secret_test_only",
            forecast_job_token="a" * 32,
        )

        settings.validate()

    def test_rejects_publishable_key_for_server(self) -> None:
        settings = Settings(
            supabase_url="https://example.supabase.co",
            supabase_secret_key="sb_publishable_not_allowed",
            forecast_job_token="a" * 32,
        )

        with self.assertRaises(ConfigurationError):
            settings.validate()

    def test_rejects_short_job_token(self) -> None:
        settings = Settings(
            supabase_url="https://example.supabase.co",
            supabase_secret_key="sb_secret_test_only",
            forecast_job_token="too-short",
        )

        with self.assertRaises(ConfigurationError):
            settings.validate()


if __name__ == "__main__":
    unittest.main()


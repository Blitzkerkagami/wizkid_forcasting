from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SECRET_KEY", "sb_secret_test_only")
os.environ.setdefault("FORECAST_JOB_TOKEN", "j" * 32)

from app.config import Settings
from app.main import create_app


class FakeRepository:
    def __init__(self) -> None:
        self.saved = []

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def iter_eligible_series(self, *, player_id: str | None = None):
        return iter(())

    def upsert_forecasts(self, forecasts) -> None:
        self.saved.extend(forecasts)


class MainApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeRepository()
        self.settings = Settings(
            supabase_url="https://example.supabase.co",
            supabase_secret_key="sb_secret_test_only",
            forecast_job_token="j" * 32,
            cron_secret="c" * 32,
        )
        app = create_app(
            self.settings,
            repository_factory=lambda _: self.repository,
        )
        self.client = TestClient(app)

    def test_cron_rejects_missing_authorization(self) -> None:
        response = self.client.get("/forecast/cron")

        self.assertEqual(response.status_code, 401)

    def test_health_reports_arima_model(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "model_version": "arima-session-v1"},
        )

    def test_cron_runs_with_vercel_bearer_secret(self) -> None:
        response = self.client.get(
            "/forecast/cron",
            headers={"Authorization": f"Bearer {self.settings.cron_secret}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"scanned": 0, "generated": 0, "skipped": 0},
        )


if __name__ == "__main__":
    unittest.main()


from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

import httpx

from app.config import Settings
from app.predictor import build_forecast
from app.supabase_repository import SupabaseForecastRepository
from tests.test_predictor import make_features


class SupabaseRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            supabase_url="https://example.supabase.co",
            supabase_secret_key="sb_secret_test_only",
            forecast_job_token="a" * 32,
            forecast_page_size=500,
        )
        self.settings.validate()

    def test_secret_is_apikey_only_and_feature_row_is_parsed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["apikey"], "sb_secret_test_only")
            self.assertNotIn("authorization", request.headers)
            self.assertEqual(request.url.params["is_forecast_eligible"], "eq.true")
            record = {
                "owner_id": "11111111-1111-4111-8111-111111111111",
                "player_id": "22222222-2222-4222-8222-222222222222",
                "skill": "alphabet-order",
                "total_attempts": 20,
                "total_sessions": 3,
                "correct_attempts": 16,
                "timed_out_attempts": 1,
                "overall_accuracy": 0.8,
                "average_response_time_ms": 2200,
                "average_difficulty": 2.4,
                "highest_level_attempted": 2,
                "recent_attempt_count": 10,
                "recent_accuracy": 0.9,
                "recent_average_response_time_ms": 1900,
                "previous_attempt_count": 10,
                "previous_accuracy": 0.7,
                "accuracy_trend_delta": 0.2,
                "observed_trend": "improving",
                "is_forecast_eligible": True,
            }
            return httpx.Response(200, json=[record])

        with SupabaseForecastRepository(
            self.settings, transport=httpx.MockTransport(handler)
        ) as repository:
            rows = list(repository.iter_eligible_features())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].skill, "alphabet-order")

    def test_upsert_uses_idempotency_columns(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(
                request.url.params["on_conflict"],
                "owner_id,player_id,skill,model_version,source_attempt_count",
            )
            self.assertEqual(
                request.headers["prefer"],
                "resolution=merge-duplicates,return=minimal",
            )
            payload = json.loads(request.content)
            self.assertEqual(len(payload), 1)
            self.assertNotIn("forecast_id", payload[0])
            return httpx.Response(201)

        forecast = build_forecast(
            make_features(),
            generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        )
        with SupabaseForecastRepository(
            self.settings, transport=httpx.MockTransport(handler)
        ) as repository:
            repository.upsert_forecasts([forecast])


if __name__ == "__main__":
    unittest.main()


from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

import httpx

from app.config import Settings
from app.predictor import build_forecast
from app.supabase_repository import SupabaseForecastRepository
from tests.test_predictor import make_series


def series_records() -> list[dict[str, object]]:
    series = make_series()
    return [
        {
            "owner_id": series.owner_id,
            "player_id": series.player_id,
            "skill": series.skill,
            "session_id": row.session_id,
            "observed_at": row.observed_at,
            "session_index": row.session_index,
            "level": row.level,
            "attempted_questions": row.attempted_questions,
            "correct_answers": row.correct_answers,
            "score_percent": row.score_percent,
            "total_sessions": series.total_sessions,
            "total_attempts": series.total_attempts,
            "total_correct_answers": series.total_correct_answers,
            "highest_level_attempted": series.highest_level_attempted,
            "is_forecast_eligible": True,
        }
        for row in series.observations
    ]


class SupabaseRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            supabase_url="https://example.supabase.co",
            supabase_secret_key="sb_secret_test_only",
            forecast_job_token="a" * 32,
            forecast_page_size=500,
        )
        self.settings.validate()

    def test_secret_is_apikey_only_and_series_is_grouped(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["apikey"], "sb_secret_test_only")
            self.assertNotIn("authorization", request.headers)
            self.assertEqual(request.url.path, "/rest/v1/learner_skill_arima_series")
            self.assertEqual(request.url.params["is_forecast_eligible"], "eq.true")
            return httpx.Response(200, json=series_records())

        with SupabaseForecastRepository(
            self.settings, transport=httpx.MockTransport(handler)
        ) as repository:
            rows = list(repository.iter_eligible_series())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].skill, "counting")
        self.assertEqual(rows[0].scores, [70.0, 76.0, 82.0, 88.0, 94.0, 100.0])

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
            self.assertEqual(payload[0]["model_version"], "arima-session-v1")
            self.assertNotIn("forecast_id", payload[0])
            return httpx.Response(201)

        forecast = build_forecast(
            make_series(),
            generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        )
        with SupabaseForecastRepository(
            self.settings, transport=httpx.MockTransport(handler)
        ) as repository:
            repository.upsert_forecasts([forecast])


if __name__ == "__main__":
    unittest.main()

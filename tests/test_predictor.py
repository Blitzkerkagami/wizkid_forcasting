from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.models import LearnerSkillSeries, SessionPerformance
from app.predictor import MODEL_VERSION, build_forecast


OWNER_ID = "11111111-1111-4111-8111-111111111111"
PLAYER_ID = "22222222-2222-4222-8222-222222222222"


def make_series(
    scores: list[float] | None = None,
    *,
    highest_level: int = 2,
) -> LearnerSkillSeries:
    values = scores or [70.0, 76.0, 82.0, 88.0, 94.0, 100.0]
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    observations: list[SessionPerformance] = []
    total_correct = 0
    for index, score in enumerate(values, start=1):
        correct = round(score / 10.0)
        total_correct += correct
        observations.append(
            SessionPerformance(
                session_id=str(UUID(int=index)),
                observed_at=(start + timedelta(days=index)).isoformat(),
                session_index=index,
                level=highest_level,
                attempted_questions=10,
                correct_answers=correct,
                score_percent=score,
            )
        )
    return LearnerSkillSeries(
        owner_id=OWNER_ID,
        player_id=PLAYER_ID,
        skill="counting",
        total_sessions=len(observations),
        total_attempts=len(observations) * 10,
        total_correct_answers=total_correct,
        highest_level_attempted=highest_level,
        observations=tuple(observations),
    )


class PredictorTests(unittest.TestCase):
    def test_improving_series_uses_arima_and_advances_level(self) -> None:
        forecast = build_forecast(
            make_series(),
            generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        )

        self.assertEqual(forecast.model_version, MODEL_VERSION)
        self.assertEqual(forecast.trend_label, "improving")
        self.assertEqual(forecast.risk_level, "low")
        self.assertEqual(forecast.recommended_level, 3)
        self.assertGreaterEqual(forecast.expected_score_percent, 85.0)
        self.assertEqual(forecast.feature_snapshot["method"], "statsmodels-arima")
        self.assertEqual(len(forecast.feature_snapshot["arima_order"]), 3)
        self.assertNotIn("owner_id", forecast.feature_snapshot)

    def test_declining_series_reduces_level(self) -> None:
        forecast = build_forecast(
            make_series([75.0, 65.0, 55.0, 45.0, 35.0, 25.0], highest_level=3),
            generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        )

        self.assertEqual(forecast.trend_label, "declining")
        self.assertEqual(forecast.risk_level, "high")
        self.assertEqual(forecast.recommended_level, 2)
        self.assertGreaterEqual(forecast.mastery_probability, 0.0)
        self.assertLessEqual(forecast.mastery_probability, 1.0)

    def test_constant_series_is_stable_and_finite(self) -> None:
        forecast = build_forecast(make_series([80.0] * 8))

        self.assertEqual(forecast.trend_label, "stable")
        self.assertAlmostEqual(forecast.expected_score_percent, 80.0, delta=1.0)
        self.assertGreaterEqual(forecast.confidence, 0.25)
        self.assertLessEqual(forecast.confidence, 0.95)

    def test_less_than_five_sessions_is_not_forecast(self) -> None:
        with self.assertRaisesRegex(ValueError, "five scored sessions"):
            build_forecast(make_series([60.0, 65.0, 70.0, 75.0]))


if __name__ == "__main__":
    unittest.main()

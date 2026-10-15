from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.models import LearnerSkillFeatures
from app.predictor import MODEL_VERSION, build_forecast


OWNER_ID = "11111111-1111-4111-8111-111111111111"
PLAYER_ID = "22222222-2222-4222-8222-222222222222"


def make_features(**overrides: object) -> LearnerSkillFeatures:
    values: dict[str, object] = {
        "owner_id": OWNER_ID,
        "player_id": PLAYER_ID,
        "skill": "alphabet-order",
        "total_attempts": 20,
        "total_sessions": 3,
        "correct_attempts": 16,
        "timed_out_attempts": 1,
        "overall_accuracy": 0.80,
        "average_response_time_ms": 2200.0,
        "average_difficulty": 2.4,
        "highest_level_attempted": 2,
        "recent_attempt_count": 10,
        "recent_accuracy": 0.90,
        "recent_average_response_time_ms": 1900.0,
        "previous_attempt_count": 10,
        "previous_accuracy": 0.70,
        "accuracy_trend_delta": 0.20,
        "observed_trend": "improving",
        "is_forecast_eligible": True,
    }
    values.update(overrides)
    return LearnerSkillFeatures(**values)  # type: ignore[arg-type]


class PredictorTests(unittest.TestCase):
    def test_strong_improving_performance_advances_level(self) -> None:
        forecast = build_forecast(
            make_features(correct_attempts=18, overall_accuracy=0.90),
            generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        )

        self.assertEqual(forecast.model_version, MODEL_VERSION)
        self.assertEqual(forecast.trend_label, "improving")
        self.assertEqual(forecast.risk_level, "low")
        self.assertEqual(forecast.recommended_level, 3)
        self.assertGreaterEqual(forecast.expected_score_percent, 85.0)
        self.assertNotIn("owner_id", forecast.feature_snapshot)

    def test_weak_declining_performance_reduces_level(self) -> None:
        forecast = build_forecast(
            make_features(
                correct_attempts=8,
                overall_accuracy=0.40,
                recent_accuracy=0.20,
                previous_accuracy=0.60,
                accuracy_trend_delta=-0.40,
                timed_out_attempts=6,
                highest_level_attempted=3,
            ),
            generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        )

        self.assertEqual(forecast.trend_label, "declining")
        self.assertEqual(forecast.risk_level, "high")
        self.assertEqual(forecast.recommended_level, 2)
        self.assertGreaterEqual(forecast.mastery_probability, 0.0)
        self.assertLessEqual(forecast.mastery_probability, 1.0)

    def test_small_sample_is_never_overconfident(self) -> None:
        forecast = build_forecast(
            make_features(
                total_attempts=10,
                total_sessions=2,
                correct_attempts=10,
                recent_attempt_count=10,
                recent_accuracy=1.0,
                overall_accuracy=1.0,
                previous_attempt_count=0,
                previous_accuracy=None,
                accuracy_trend_delta=None,
            )
        )

        self.assertLess(forecast.confidence, 0.70)
        self.assertEqual(forecast.trend_label, "stable")


if __name__ == "__main__":
    unittest.main()


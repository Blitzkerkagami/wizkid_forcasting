from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Forecast, LearnerSkillFeatures


MODEL_VERSION = "bayesian-recency-v1"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def build_forecast(
    features: LearnerSkillFeatures,
    *,
    generated_at: datetime | None = None,
    valid_days: int = 7,
) -> Forecast:
    """Create an explainable forecast from one aggregated learner-skill row."""
    features.validate()
    if not 1 <= valid_days <= 30:
        raise ValueError("valid_days must be between 1 and 30")

    now = generated_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    now = now.astimezone(timezone.utc)

    # A Beta(2, 2) prior keeps very small samples away from false certainty.
    posterior_mastery = (features.correct_attempts + 2.0) / (
        features.total_attempts + 4.0
    )
    trend_delta = _clamp(features.accuracy_trend_delta or 0.0, -0.25, 0.25)
    timeout_rate = features.timed_out_attempts / features.total_attempts

    expected_fraction = _clamp(
        0.45 * features.recent_accuracy
        + 0.35 * posterior_mastery
        + 0.20 * features.overall_accuracy
        + 0.20 * trend_delta
        - 0.08 * timeout_rate,
        0.0,
        1.0,
    )
    mastery_probability = _clamp(
        0.55 * posterior_mastery
        + 0.30 * features.recent_accuracy
        + 0.15 * features.overall_accuracy
        + 0.10 * trend_delta
        - 0.05 * timeout_rate,
        0.0,
        1.0,
    )

    sample_factor = min(1.0, features.total_attempts / 50.0)
    session_factor = min(1.0, features.total_sessions / 5.0)
    history_factor = 1.0 if features.previous_attempt_count >= 5 else 0.6
    confidence = _clamp(
        0.45
        + 0.30 * sample_factor
        + 0.15 * session_factor
        + 0.10 * history_factor,
        0.0,
        0.95,
    )

    if trend_delta >= 0.10:
        trend_label = "improving"
    elif trend_delta <= -0.10:
        trend_label = "declining"
    else:
        trend_label = "stable"

    expected_score = round(expected_fraction * 100.0, 2)
    mastery_probability = round(mastery_probability, 4)
    confidence = round(confidence, 4)

    if (
        expected_score < 60.0
        or mastery_probability < 0.55
        or (trend_label == "declining" and expected_score < 70.0)
    ):
        risk_level = "high"
    elif (
        expected_score < 75.0
        or mastery_probability < 0.70
        or confidence < 0.65
    ):
        risk_level = "medium"
    else:
        risk_level = "low"

    current_level = int(_clamp(features.highest_level_attempted, 1, 5))
    if risk_level == "high":
        recommended_level = max(1, current_level - 1)
    elif (
        expected_score >= 85.0
        and mastery_probability >= 0.80
        and confidence >= 0.65
    ):
        recommended_level = min(5, current_level + 1)
    else:
        recommended_level = current_level

    recommendation = _recommendation(
        skill=features.skill,
        risk_level=risk_level,
        trend_label=trend_label,
        current_level=current_level,
        recommended_level=recommended_level,
    )

    return Forecast(
        owner_id=features.owner_id,
        player_id=features.player_id,
        skill=features.skill,
        model_version=MODEL_VERSION,
        generated_at=now.isoformat(),
        valid_until=(now + timedelta(days=valid_days)).isoformat(),
        source_attempt_count=features.total_attempts,
        expected_score_percent=expected_score,
        mastery_probability=mastery_probability,
        confidence=confidence,
        trend_label=trend_label,
        risk_level=risk_level,
        recommended_level=recommended_level,
        recommendation=recommendation,
        feature_snapshot={
            "total_attempts": features.total_attempts,
            "total_sessions": features.total_sessions,
            "overall_accuracy": features.overall_accuracy,
            "recent_attempt_count": features.recent_attempt_count,
            "recent_accuracy": features.recent_accuracy,
            "previous_attempt_count": features.previous_attempt_count,
            "previous_accuracy": features.previous_accuracy,
            "accuracy_trend_delta": features.accuracy_trend_delta,
            "timeout_rate": round(timeout_rate, 4),
            "average_response_time_ms": features.average_response_time_ms,
            "average_difficulty": features.average_difficulty,
            "highest_level_attempted": features.highest_level_attempted,
            "posterior_mastery": round(posterior_mastery, 4),
        },
    )


def _recommendation(
    *,
    skill: str,
    risk_level: str,
    trend_label: str,
    current_level: int,
    recommended_level: int,
) -> str:
    if risk_level == "high":
        return (
            f"Review {skill} at level {recommended_level} with short guided practice "
            "before trying a harder activity."
        )
    if recommended_level > current_level:
        return (
            f"Performance in {skill} is ready for level {recommended_level}; "
            "continue monitoring accuracy after the increase."
        )
    if trend_label == "declining":
        return (
            f"Keep {skill} at level {recommended_level} and add a brief review "
            "to reverse the recent decline."
        )
    return (
        f"Continue {skill} at level {recommended_level} and gather more attempts "
        "before changing difficulty."
    )


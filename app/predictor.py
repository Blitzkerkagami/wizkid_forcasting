from __future__ import annotations

import math
import warnings
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from statsmodels.tsa.arima.model import ARIMA

from .models import Forecast, LearnerSkillSeries


MODEL_VERSION = "arima-session-v1"
MINIMUM_SESSIONS = 5
_CANDIDATE_ORDERS = ((1, 1, 0), (0, 1, 1), (1, 0, 0), (0, 1, 0))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _recent_slope(values: list[float]) -> float:
    recent = values[-min(5, len(values)) :]
    x_values = np.arange(len(recent), dtype=float)
    if len(recent) < 2:
        return 0.0
    return float(np.polyfit(x_values, np.asarray(recent, dtype=float), 1)[0])


def _fit_arima(
    values: list[float],
) -> tuple[float, float, float, tuple[int, int, int], float]:
    samples = np.asarray(values, dtype=float)
    best: tuple[float, Any, tuple[int, int, int]] | None = None

    for order in _CANDIDATE_ORDERS:
        p, d, q = order
        if len(samples) < p + d + q + 3:
            continue
        trend = "t" if d > 0 else "ct"
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = ARIMA(
                    samples,
                    order=order,
                    trend=trend,
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                ).fit()
            parameter_count = len(fitted.params)
            denominator = len(samples) - parameter_count - 1
            aicc = (
                float(fitted.aic)
                + (2.0 * parameter_count * (parameter_count + 1)) / denominator
                if denominator > 0
                else math.inf
            )
            if math.isfinite(aicc) and (best is None or aicc < best[0]):
                best = (aicc, fitted, order)
        except (ValueError, TypeError, ArithmeticError, np.linalg.LinAlgError):
            continue

    if best is None:
        raise ValueError("ARIMA could not fit this learner session series")

    aicc, fitted, selected_order = best
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        prediction = fitted.get_forecast(steps=1)
    expected = float(np.asarray(prediction.predicted_mean).reshape(-1)[0])
    interval = np.asarray(prediction.conf_int(alpha=0.20), dtype=float).reshape(-1, 2)[0]
    lower = float(interval[0])
    upper = float(interval[1])
    if not all(math.isfinite(value) for value in (expected, lower, upper)):
        raise ValueError("ARIMA returned a non-finite prediction")
    return expected, lower, upper, selected_order, aicc


def build_forecast(
    series: LearnerSkillSeries,
    *,
    generated_at: datetime | None = None,
    valid_days: int = 7,
) -> Forecast:
    """Fit ARIMA to chronological per-session scores and forecast the next score."""
    series.validate()
    if not 1 <= valid_days <= 30:
        raise ValueError("valid_days must be between 1 and 30")

    now = generated_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    now = now.astimezone(timezone.utc)

    scores = series.scores
    expected_raw, lower_raw, upper_raw, order, aicc = _fit_arima(scores)
    expected_score = round(_clamp(expected_raw, 0.0, 100.0), 2)
    lower = round(_clamp(lower_raw, 0.0, 100.0), 2)
    upper = round(_clamp(upper_raw, 0.0, 100.0), 2)

    mastery_probability = round(
        _clamp(
            (series.total_correct_answers + 2.0) / (series.total_attempts + 4.0),
            0.0,
            1.0,
        ),
        4,
    )
    interval_quality = 1.0 - _clamp((upper - lower) / 100.0, 0.0, 1.0)
    history_quality = min(1.0, series.total_sessions / 12.0)
    confidence = round(
        _clamp(0.25 + 0.40 * history_quality + 0.35 * interval_quality, 0.25, 0.95),
        4,
    )

    slope = _recent_slope(scores)
    if slope >= 2.0:
        trend_label = "improving"
    elif slope <= -2.0:
        trend_label = "declining"
    else:
        trend_label = "stable"

    if (
        expected_score < 60.0
        or mastery_probability < 0.55
        or (trend_label == "declining" and expected_score < 70.0)
    ):
        risk_level = "high"
    elif expected_score < 75.0 or mastery_probability < 0.70 or confidence < 0.60:
        risk_level = "medium"
    else:
        risk_level = "low"

    current_level = int(_clamp(series.highest_level_attempted, 1, 5))
    if risk_level == "high":
        recommended_level = max(1, current_level - 1)
    elif expected_score >= 85.0 and mastery_probability >= 0.80 and confidence >= 0.60:
        recommended_level = min(5, current_level + 1)
    else:
        recommended_level = current_level

    recommendation = _recommendation(
        skill=series.skill,
        risk_level=risk_level,
        trend_label=trend_label,
        current_level=current_level,
        recommended_level=recommended_level,
    )

    return Forecast(
        owner_id=series.owner_id,
        player_id=series.player_id,
        skill=series.skill,
        model_version=MODEL_VERSION,
        generated_at=now.isoformat(),
        valid_until=(now + timedelta(days=valid_days)).isoformat(),
        source_attempt_count=series.total_attempts,
        expected_score_percent=expected_score,
        mastery_probability=mastery_probability,
        confidence=confidence,
        trend_label=trend_label,
        risk_level=risk_level,
        recommended_level=recommended_level,
        recommendation=recommendation,
        feature_snapshot={
            "method": "statsmodels-arima",
            "arima_order": list(order),
            "aicc": round(aicc, 4),
            "session_count": series.total_sessions,
            "session_scores_percent": [round(value, 2) for value in scores],
            "prediction_interval_80_percent": [lower, upper],
            "recent_score_slope": round(slope, 4),
            "total_attempts": series.total_attempts,
            "total_correct_answers": series.total_correct_answers,
            "highest_level_attempted": series.highest_level_attempted,
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
            f"The ARIMA trend for {skill} supports trying level {recommended_level}; "
            "continue monitoring the next sessions."
        )
    if trend_label == "declining":
        return (
            f"Keep {skill} at level {recommended_level} and add a brief review "
            "to address the declining session trend."
        )
    return (
        f"Continue {skill} at level {recommended_level} and collect more sessions "
        "before changing difficulty."
    )

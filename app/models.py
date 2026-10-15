from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


def _bounded_fraction(value: Any, field_name: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return number


@dataclass(frozen=True, slots=True)
class LearnerSkillFeatures:
    owner_id: str
    player_id: str
    skill: str
    total_attempts: int
    total_sessions: int
    correct_attempts: int
    timed_out_attempts: int
    overall_accuracy: float
    average_response_time_ms: float
    average_difficulty: float
    highest_level_attempted: int
    recent_attempt_count: int
    recent_accuracy: float
    recent_average_response_time_ms: float
    previous_attempt_count: int
    previous_accuracy: float | None
    accuracy_trend_delta: float | None
    observed_trend: str
    is_forecast_eligible: bool

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "LearnerSkillFeatures":
        owner_id = str(UUID(str(record["owner_id"])))
        player_id = str(UUID(str(record["player_id"])))
        skill = " ".join(str(record["skill"]).split())
        if not 1 <= len(skill) <= 80:
            raise ValueError("skill must contain between 1 and 80 characters")

        overall_accuracy = _bounded_fraction(
            record["overall_accuracy"], "overall_accuracy"
        )
        recent_accuracy = _bounded_fraction(
            record.get("recent_accuracy", overall_accuracy), "recent_accuracy"
        )
        previous_raw = record.get("previous_accuracy")
        previous_accuracy = (
            None
            if previous_raw is None
            else _bounded_fraction(previous_raw, "previous_accuracy")
        )
        trend_raw = record.get("accuracy_trend_delta")
        trend_delta = None if trend_raw is None else float(trend_raw)

        features = cls(
            owner_id=owner_id,
            player_id=player_id,
            skill=skill,
            total_attempts=int(record["total_attempts"]),
            total_sessions=int(record["total_sessions"]),
            correct_attempts=int(record["correct_attempts"]),
            timed_out_attempts=int(record["timed_out_attempts"]),
            overall_accuracy=overall_accuracy,
            average_response_time_ms=float(record["average_response_time_ms"]),
            average_difficulty=float(record["average_difficulty"]),
            highest_level_attempted=int(record["highest_level_attempted"]),
            recent_attempt_count=int(record["recent_attempt_count"]),
            recent_accuracy=recent_accuracy,
            recent_average_response_time_ms=float(
                record["recent_average_response_time_ms"]
            ),
            previous_attempt_count=int(record["previous_attempt_count"]),
            previous_accuracy=previous_accuracy,
            accuracy_trend_delta=trend_delta,
            observed_trend=str(record.get("observed_trend", "insufficient_history")),
            is_forecast_eligible=bool(record["is_forecast_eligible"]),
        )
        features.validate()
        return features

    def validate(self) -> None:
        if self.total_attempts < 1:
            raise ValueError("total_attempts must be positive")
        if not 0 <= self.correct_attempts <= self.total_attempts:
            raise ValueError("correct_attempts is inconsistent with total_attempts")
        if not 0 <= self.timed_out_attempts <= self.total_attempts:
            raise ValueError("timed_out_attempts is inconsistent with total_attempts")
        if self.total_sessions < 1:
            raise ValueError("total_sessions must be positive")
        if not 1 <= self.highest_level_attempted <= 5:
            raise ValueError("highest_level_attempted must be between 1 and 5")
        if self.average_response_time_ms < 0 or self.recent_average_response_time_ms < 0:
            raise ValueError("response times cannot be negative")
        if not self.is_forecast_eligible:
            raise ValueError("row does not meet the forecasting eligibility rule")


@dataclass(frozen=True, slots=True)
class Forecast:
    owner_id: str
    player_id: str
    skill: str
    model_version: str
    generated_at: str
    valid_until: str
    source_attempt_count: int
    expected_score_percent: float
    mastery_probability: float
    confidence: float
    trend_label: str
    risk_level: str
    recommended_level: int
    recommendation: str
    feature_snapshot: dict[str, Any]

    def to_record(self) -> dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "player_id": self.player_id,
            "skill": self.skill,
            "model_version": self.model_version,
            "generated_at": self.generated_at,
            "valid_until": self.valid_until,
            "source_attempt_count": self.source_attempt_count,
            "expected_score_percent": self.expected_score_percent,
            "mastery_probability": self.mastery_probability,
            "confidence": self.confidence,
            "trend_label": self.trend_label,
            "risk_level": self.risk_level,
            "recommended_level": self.recommended_level,
            "recommendation": self.recommendation,
            "feature_snapshot": self.feature_snapshot,
        }


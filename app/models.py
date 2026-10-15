from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence
from uuid import UUID


def _clean_skill(value: Any) -> str:
    skill = " ".join(str(value).split())
    if not 1 <= len(skill) <= 80:
        raise ValueError("skill must contain between 1 and 80 characters")
    return skill


@dataclass(frozen=True, slots=True)
class SessionPerformance:
    session_id: str
    observed_at: str
    session_index: int
    level: int
    attempted_questions: int
    correct_answers: int
    score_percent: float

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "SessionPerformance":
        observation = cls(
            session_id=str(UUID(str(record["session_id"]))),
            observed_at=str(record["observed_at"]),
            session_index=int(record["session_index"]),
            level=int(record["level"]),
            attempted_questions=int(record["attempted_questions"]),
            correct_answers=int(record["correct_answers"]),
            score_percent=float(record["score_percent"]),
        )
        observation.validate()
        return observation

    def validate(self) -> None:
        if self.session_index < 1:
            raise ValueError("session_index must be positive")
        if not 1 <= self.level <= 5:
            raise ValueError("level must be between 1 and 5")
        if self.attempted_questions < 1:
            raise ValueError("attempted_questions must be positive")
        if not 0 <= self.correct_answers <= self.attempted_questions:
            raise ValueError("correct_answers is inconsistent with attempts")
        if not 0.0 <= self.score_percent <= 100.0:
            raise ValueError("score_percent must be between 0 and 100")
        datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))


@dataclass(frozen=True, slots=True)
class LearnerSkillSeries:
    owner_id: str
    player_id: str
    skill: str
    total_sessions: int
    total_attempts: int
    total_correct_answers: int
    highest_level_attempted: int
    observations: tuple[SessionPerformance, ...]

    @classmethod
    def from_records(
        cls, records: Sequence[dict[str, Any]]
    ) -> "LearnerSkillSeries":
        if not records:
            raise ValueError("an ARIMA series requires at least one record")

        first = records[0]
        owner_id = str(UUID(str(first["owner_id"])))
        player_id = str(UUID(str(first["player_id"])))
        skill = _clean_skill(first["skill"])
        total_sessions = int(first["total_sessions"])
        total_attempts = int(first["total_attempts"])
        total_correct_answers = int(first["total_correct_answers"])
        highest_level = int(first["highest_level_attempted"])

        observations: list[SessionPerformance] = []
        for record in records:
            if (
                str(UUID(str(record["owner_id"]))) != owner_id
                or str(UUID(str(record["player_id"]))) != player_id
                or _clean_skill(record["skill"]) != skill
            ):
                raise ValueError("ARIMA records mix different learner-skill series")
            if (
                int(record["total_sessions"]) != total_sessions
                or int(record["total_attempts"]) != total_attempts
                or int(record["total_correct_answers"]) != total_correct_answers
                or int(record["highest_level_attempted"]) != highest_level
            ):
                raise ValueError("ARIMA series metadata is inconsistent")
            if not bool(record["is_forecast_eligible"]):
                raise ValueError("row does not meet ARIMA eligibility rules")
            observations.append(SessionPerformance.from_record(record))

        observations.sort(key=lambda item: item.session_index)
        series = cls(
            owner_id=owner_id,
            player_id=player_id,
            skill=skill,
            total_sessions=total_sessions,
            total_attempts=total_attempts,
            total_correct_answers=total_correct_answers,
            highest_level_attempted=highest_level,
            observations=tuple(observations),
        )
        series.validate()
        return series

    def validate(self) -> None:
        if self.total_sessions < 5 or len(self.observations) < 5:
            raise ValueError("ARIMA forecasting requires at least five scored sessions")
        if len(self.observations) != self.total_sessions:
            raise ValueError("session rows are incomplete")
        if self.total_attempts < 10:
            raise ValueError("ARIMA forecasting requires at least ten attempts")
        if not 0 <= self.total_correct_answers <= self.total_attempts:
            raise ValueError("total correct answers are inconsistent with attempts")
        if not 1 <= self.highest_level_attempted <= 5:
            raise ValueError("highest_level_attempted must be between 1 and 5")
        expected_indexes = list(range(1, len(self.observations) + 1))
        if [row.session_index for row in self.observations] != expected_indexes:
            raise ValueError("ARIMA session indexes must be contiguous")

    @property
    def scores(self) -> list[float]:
        return [row.score_percent for row in self.observations]


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

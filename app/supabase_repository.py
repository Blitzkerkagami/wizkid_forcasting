from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import httpx

from .config import Settings
from .models import Forecast, LearnerSkillFeatures


FEATURE_COLUMNS = ",".join(
    (
        "owner_id",
        "player_id",
        "skill",
        "total_attempts",
        "total_sessions",
        "correct_attempts",
        "timed_out_attempts",
        "overall_accuracy",
        "average_response_time_ms",
        "average_difficulty",
        "highest_level_attempted",
        "recent_attempt_count",
        "recent_accuracy",
        "recent_average_response_time_ms",
        "previous_attempt_count",
        "previous_accuracy",
        "accuracy_trend_delta",
        "observed_trend",
        "is_forecast_eligible",
    )
)


class SupabaseRepositoryError(RuntimeError):
    """A sanitized Supabase Data API error that never includes credentials."""


class SupabaseForecastRepository:
    def __init__(
        self,
        settings: Settings,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._page_size = settings.forecast_page_size
        self._client = httpx.Client(
            base_url=f"{settings.supabase_url}/rest/v1/",
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                # New sb_secret_ keys are supplied only through apikey, never Bearer.
                "apikey": settings.supabase_secret_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "WizKid-Forecasting/1.0",
            },
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SupabaseForecastRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def iter_eligible_features(
        self, *, player_id: str | None = None
    ) -> Iterator[LearnerSkillFeatures]:
        offset = 0
        while True:
            params: dict[str, str | int] = {
                "select": FEATURE_COLUMNS,
                "is_forecast_eligible": "eq.true",
                "order": "owner_id.asc,player_id.asc,skill.asc",
                "limit": self._page_size,
                "offset": offset,
            }
            if player_id is not None:
                params["player_id"] = f"eq.{player_id}"

            records = self._request_json("GET", "learner_skill_features", params=params)
            if not isinstance(records, list):
                raise SupabaseRepositoryError(
                    "Supabase returned an unexpected forecasting feature response."
                )
            for record in records:
                if not isinstance(record, dict):
                    raise SupabaseRepositoryError(
                        "Supabase returned a malformed forecasting feature row."
                    )
                yield LearnerSkillFeatures.from_record(record)

            if len(records) < self._page_size:
                break
            offset += self._page_size

    def upsert_forecasts(self, forecasts: Sequence[Forecast]) -> None:
        if not forecasts:
            return
        self._request_json(
            "POST",
            "learner_forecasts",
            params={
                "on_conflict": (
                    "owner_id,player_id,skill,model_version,source_attempt_count"
                )
            },
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json=[forecast.to_record() for forecast in forecasts],
            expect_json=False,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json: Any = None,
        expect_json: bool = True,
    ) -> Any:
        try:
            response = self._client.request(
                method, path, params=params, headers=headers, json=json
            )
            response.raise_for_status()
            return response.json() if expect_json else None
        except httpx.HTTPStatusError as exc:
            raise SupabaseRepositoryError(
                f"Supabase Data API returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise SupabaseRepositoryError(
                "Supabase Data API could not be reached."
            ) from exc
        except ValueError as exc:
            raise SupabaseRepositoryError(
                "Supabase returned a response that was not valid JSON."
            ) from exc


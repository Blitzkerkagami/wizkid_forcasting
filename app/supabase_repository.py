from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import httpx

from .config import Settings
from .models import Forecast, LearnerSkillSeries


SERIES_COLUMNS = ",".join(
    (
        "owner_id",
        "player_id",
        "skill",
        "session_id",
        "observed_at",
        "session_index",
        "level",
        "attempted_questions",
        "correct_answers",
        "score_percent",
        "total_sessions",
        "total_attempts",
        "total_correct_answers",
        "highest_level_attempted",
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
                "apikey": settings.supabase_secret_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "WizKid-Forecasting/2.0",
            },
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SupabaseForecastRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def iter_eligible_series(
        self, *, player_id: str | None = None
    ) -> Iterator[LearnerSkillSeries]:
        current_key: tuple[str, str, str] | None = None
        current_records: list[dict[str, Any]] = []
        offset = 0

        while True:
            params: dict[str, str | int] = {
                "select": SERIES_COLUMNS,
                "is_forecast_eligible": "eq.true",
                "order": (
                    "owner_id.asc,player_id.asc,skill.asc,session_index.asc"
                ),
                "limit": self._page_size,
                "offset": offset,
            }
            if player_id is not None:
                params["player_id"] = f"eq.{player_id}"

            records = self._request_json(
                "GET", "learner_skill_arima_series", params=params
            )
            if not isinstance(records, list):
                raise SupabaseRepositoryError(
                    "Supabase returned an unexpected ARIMA series response."
                )

            for record in records:
                if not isinstance(record, dict):
                    raise SupabaseRepositoryError(
                        "Supabase returned a malformed ARIMA series row."
                    )
                try:
                    key = (
                        str(record["owner_id"]),
                        str(record["player_id"]),
                        str(record["skill"]),
                    )
                except KeyError as exc:
                    raise SupabaseRepositoryError(
                        "Supabase returned an incomplete ARIMA series row."
                    ) from exc

                if current_key is not None and key != current_key:
                    try:
                        yield LearnerSkillSeries.from_records(current_records)
                    except (KeyError, TypeError, ValueError) as exc:
                        raise SupabaseRepositoryError(
                            "Supabase returned an invalid ARIMA learner series."
                        ) from exc
                    current_records = []
                current_key = key
                current_records.append(record)

            if len(records) < self._page_size:
                break
            offset += self._page_size

        if current_records:
            try:
                yield LearnerSkillSeries.from_records(current_records)
            except (KeyError, TypeError, ValueError) as exc:
                raise SupabaseRepositoryError(
                    "Supabase returned an invalid ARIMA learner series."
                ) from exc

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

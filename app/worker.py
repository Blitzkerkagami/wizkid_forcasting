from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from .models import Forecast, LearnerSkillSeries
from .predictor import build_forecast


class ForecastRepository(Protocol):
    def iter_eligible_series(
        self, *, player_id: str | None = None
    ) -> Iterable[LearnerSkillSeries]: ...

    def upsert_forecasts(self, forecasts: list[Forecast]) -> None: ...


@dataclass(frozen=True, slots=True)
class RunResult:
    scanned: int
    generated: int
    skipped: int


def run_forecasts(
    repository: ForecastRepository,
    *,
    player_id: str | None = None,
    valid_days: int = 7,
    generated_at: datetime | None = None,
) -> RunResult:
    normalized_player_id = str(UUID(player_id)) if player_id else None
    run_time = generated_at or datetime.now(timezone.utc)
    forecasts: list[Forecast] = []
    scanned = 0
    skipped = 0

    series_rows = repository.iter_eligible_series(player_id=normalized_player_id)
    for series in series_rows:
        scanned += 1
        if not isinstance(series, LearnerSkillSeries):
            skipped += 1
            continue
        try:
            forecasts.append(
                build_forecast(
                    series,
                    generated_at=run_time,
                    valid_days=valid_days,
                )
            )
        except ValueError:
            skipped += 1

    repository.upsert_forecasts(forecasts)
    return RunResult(scanned=scanned, generated=len(forecasts), skipped=skipped)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate WizKid learner forecasts.")
    parser.add_argument("--player-id", help="Optional UUID for a single learner.")
    args = parser.parse_args()

    from .config import Settings
    from .supabase_repository import SupabaseForecastRepository

    settings = Settings.from_env()
    with SupabaseForecastRepository(settings) as repository:
        result = run_forecasts(
            repository,
            player_id=args.player_id,
            valid_days=settings.forecast_valid_days,
        )
    print(json.dumps(asdict(result)))


if __name__ == "__main__":
    main()


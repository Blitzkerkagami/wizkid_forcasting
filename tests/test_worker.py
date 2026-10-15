from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.models import Forecast
from app.worker import run_forecasts
from tests.test_predictor import make_series


class FakeRepository:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.saved: list[Forecast] = []
        self.requested_player_id: str | None = None

    def iter_eligible_series(self, *, player_id: str | None = None):
        self.requested_player_id = player_id
        return iter(self.rows)

    def upsert_forecasts(self, forecasts: list[Forecast]) -> None:
        self.saved.extend(forecasts)


class WorkerTests(unittest.TestCase):
    def test_generates_and_upserts_forecasts(self) -> None:
        repository = FakeRepository([make_series(), object()])

        result = run_forecasts(
            repository,
            player_id="22222222-2222-4222-8222-222222222222",
            generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        )

        self.assertEqual(result.scanned, 2)
        self.assertEqual(result.generated, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(len(repository.saved), 1)
        self.assertEqual(
            repository.requested_player_id,
            "22222222-2222-4222-8222-222222222222",
        )

    def test_empty_run_does_not_create_rows(self) -> None:
        repository = FakeRepository([])
        result = run_forecasts(repository)

        self.assertEqual(result.generated, 0)
        self.assertEqual(repository.saved, [])


if __name__ == "__main__":
    unittest.main()


from __future__ import annotations

import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from .config import Settings
from .predictor import MODEL_VERSION
from .supabase_repository import SupabaseForecastRepository, SupabaseRepositoryError
from .worker import ForecastRepository, run_forecasts


class ForecastRunRequest(BaseModel):
    player_id: UUID | None = None


RepositoryFactory = Callable[
    [Settings], AbstractContextManager[ForecastRepository]
]


def create_app(
    settings: Settings | None = None,
    repository_factory: RepositoryFactory = SupabaseForecastRepository,
) -> FastAPI:
    service_settings = settings or Settings.from_env()
    application = FastAPI(
        title="WizKid Forecasting Service",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "model_version": MODEL_VERSION}

    def execute_forecasts(player_id: str | None = None) -> dict[str, int]:
        try:
            with repository_factory(service_settings) as repository:
                result = run_forecasts(
                    repository,
                    player_id=player_id,
                    valid_days=service_settings.forecast_valid_days,
                )
        except SupabaseRepositoryError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        return asdict(result)

    @application.post("/forecast/run")
    def forecast_run(
        request: ForecastRunRequest,
        x_job_token: str = Header(default="", alias="X-Job-Token"),
    ) -> dict[str, int]:
        if not secrets.compare_digest(
            x_job_token.encode("utf-8"),
            service_settings.forecast_job_token.encode("utf-8"),
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid job token.",
            )

        return execute_forecasts(
            str(request.player_id) if request.player_id else None
        )

    @application.get("/forecast/cron")
    def forecast_cron(
        authorization: str = Header(default=""),
    ) -> dict[str, int]:
        if not service_settings.cron_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Scheduled forecasting is not configured.",
            )

        expected_authorization = f"Bearer {service_settings.cron_secret}"
        if not secrets.compare_digest(authorization, expected_authorization):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid cron authorization.",
            )
        return execute_forecasts()

    return application


app = create_app()


from __future__ import annotations

import secrets
from dataclasses import asdict
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from .config import Settings
from .predictor import MODEL_VERSION
from .supabase_repository import SupabaseForecastRepository, SupabaseRepositoryError
from .worker import run_forecasts


class ForecastRunRequest(BaseModel):
    player_id: UUID | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
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

        try:
            with SupabaseForecastRepository(service_settings) as repository:
                result = run_forecasts(
                    repository,
                    player_id=str(request.player_id) if request.player_id else None,
                    valid_days=service_settings.forecast_valid_days,
                )
        except SupabaseRepositoryError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        return asdict(result)

    return application


app = create_app()


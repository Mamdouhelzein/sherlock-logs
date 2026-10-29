"""Public foundation endpoints. Authentication and event ingestion are future milestones."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sherlock_api import __version__
from sherlock_api.config import Settings


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["sherlock-logs-api"] = "sherlock-logs-api"
    version: str = __version__


class Integration(BaseModel):
    id: Literal["authentication", "database", "detector"]
    name: str
    status: Literal["not_configured", "not_trained"]
    detail: str


class SystemResponse(BaseModel):
    service: Literal["sherlock-logs-api"] = "sherlock-logs-api"
    version: str = __version__
    status: Literal["ok"] = "ok"
    stage: Literal["foundation"] = "foundation"
    checked_at: datetime
    uptime_seconds: int = Field(ge=0)
    integrations: list[Integration]


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.started_at = time.monotonic()
        yield

    application = FastAPI(
        title="Sherlock Logs API",
        description="Foundation API for behavioral login security monitoring.",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if config.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.environment != "production" else None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )

    @application.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/healthz", response_model=HealthResponse, tags=["System"])
    async def health() -> HealthResponse:
        """Process liveness only; does not imply database or model readiness."""
        return HealthResponse()

    @application.get("/api/v1/system", response_model=SystemResponse, tags=["System"])
    async def system(request: Request) -> SystemResponse:
        return SystemResponse(
            checked_at=datetime.now(UTC),
            uptime_seconds=int(time.monotonic() - request.app.state.started_at),
            integrations=[
                Integration(
                    id="authentication",
                    name="Supabase Auth",
                    status="not_configured",
                    detail="Account registration and sign-in arrive in the next milestone.",
                ),
                Integration(
                    id="database",
                    name="PostgreSQL",
                    status="not_configured",
                    detail="No login events or investigation records are stored yet.",
                ),
                Integration(
                    id="detector",
                    name="Isolation Forest",
                    status="not_trained",
                    detail="Data generation, training, and evaluation are upcoming milestones.",
                ),
            ],
        )

    return application


app = create_app()

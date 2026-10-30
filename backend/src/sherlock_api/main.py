"""Public system endpoints and server-enforced identity boundaries."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sherlock_api import __version__
from sherlock_api.auth import router as identity_router
from sherlock_api.config import Settings
from sherlock_api.telemetry.api import router as telemetry_router


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["sherlock-logs-api"] = "sherlock-logs-api"
    version: str = __version__


class Integration(BaseModel):
    id: Literal["authentication", "database", "detector"]
    name: str
    status: Literal["not_configured", "configured", "not_trained"]
    detail: str


class SystemResponse(BaseModel):
    service: Literal["sherlock-logs-api"] = "sherlock-logs-api"
    version: str = __version__
    status: Literal["ok"] = "ok"
    stage: Literal["telemetry"] = "telemetry"
    checked_at: datetime
    uptime_seconds: int = Field(ge=0)
    integrations: list[Integration]


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.started_at = time.monotonic()
        application.state.settings = config
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            application.state.supabase = client
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
        allow_headers=["Content-Type", "Authorization"],
    )
    application.include_router(identity_router)
    application.include_router(telemetry_router)

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
                    status="configured" if config.auth_configured else "not_configured",
                    detail=(
                        "Project settings are present; this status does not probe live sign-in."
                        if config.auth_configured
                        else "Sign-in is built. Connect your Supabase project to enable it."
                    ),
                ),
                Integration(
                    id="database",
                    name="PostgreSQL",
                    status="configured" if config.events_configured else "not_configured",
                    detail=(
                        "Event database settings are present; collection coverage is not verified."
                        if config.events_configured
                        else "Event storage and collection are built. Database setup is required."
                    ),
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

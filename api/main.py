"""FastAPI application: REST API for the UI, Prometheus metrics, OpenTelemetry tracing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from api.routers import companies, filings, pipeline, qa, review
from core.config import get_settings
from core.logging import configure_logging
from core.telemetry import setup_tracing


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    configure_logging(s.log_level)
    setup_tracing("docflow-api")
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="DocFlow API",
        version="0.1.0",
        description="AI document intelligence over SEC EDGAR filings.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.api_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (
        pipeline.router,
        companies.router,
        filings.router,
        review.router,
        qa.qa_router,
        qa.eval_router,
    ):
        app.include_router(router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.mount("/metrics", make_asgi_app())
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="/metrics,/api/health")
    except ImportError:  # pragma: no cover
        pass
    return app


app = create_app()

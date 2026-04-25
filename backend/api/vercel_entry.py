"""Vercel serverless entry point for the FastAPI app.

Key difference from api/main.py:
- No background worker pool (Vercel is serverless — no persistent processes)
- Workers run separately on Railway (see railway.json)
- Redis Streams queue still works: webhooks enqueue jobs here,
  the Railway worker consumes them
"""
from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from ..telemetry import setup_telemetry
from .jobs import router as jobs_router
from .review import router as review_router
from .webhooks import router as webhooks_router

logger = structlog.get_logger(__name__)


def create_vercel_app() -> FastAPI:
    setup_telemetry()

    app = FastAPI(
        title="DevMind API",
        description="Autonomous PR code review agent — serverless API",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten to your Vercel domain in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(webhooks_router)
    app.include_router(jobs_router)
    app.include_router(review_router)

    FastAPIInstrumentor.instrument_app(app)

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": "serverless"}

    return app


# Vercel expects a module-level `app` variable
app = create_vercel_app()

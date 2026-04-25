"""FastAPI application entry point."""
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


def create_app() -> FastAPI:
    setup_telemetry()

    app = FastAPI(
        title="DevMind",
        description="Autonomous PR code review agent",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(webhooks_router)
    app.include_router(jobs_router)
    app.include_router(review_router)

    FastAPIInstrumentor.instrument_app(app)

    @app.on_event("startup")
    async def startup():
        from ..queue.worker import start_worker_pool
        app.state.worker_tasks = await start_worker_pool()
        logger.info("app.started")

    @app.on_event("shutdown")
    async def shutdown():
        for task in getattr(app.state, "worker_tasks", []):
            task.cancel()
        logger.info("app.stopped")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()

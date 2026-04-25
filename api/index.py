"""Root-level Vercel Python serverless entry point.

sys.path is set to the project root so `backend` is importable as a package.
All relative imports inside the backend (e.g. `from ..models import`) resolve
correctly because Python treats `backend` as a top-level package.
"""
from __future__ import annotations

import os
import sys

# Project root = /var/task on Vercel, or repo root locally
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.webhooks import router as webhooks_router
from backend.api.jobs import router as jobs_router
from backend.api.review import router as review_router
from backend.telemetry import setup_telemetry

setup_telemetry()

app = FastAPI(
    title="DevMind API",
    description="Autonomous PR code review agent",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhooks_router)
app.include_router(jobs_router)
app.include_router(review_router)


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "serverless"}

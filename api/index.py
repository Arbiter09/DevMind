"""Root-level Vercel Python serverless entry point.

Vercel looks for `api/index.py` and expects an `app` ASGI variable.
We add the backend package to sys.path so absolute imports work,
then re-export the FastAPI app.
"""
from __future__ import annotations

import os
import sys

# Make `backend` importable as a top-level package
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
for path in (ROOT, BACKEND):
    if path not in sys.path:
        sys.path.insert(0, path)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import individual routers with absolute paths (no relative imports)
from api.webhooks import router as webhooks_router  # noqa: E402
from api.jobs import router as jobs_router          # noqa: E402
from api.review import router as review_router      # noqa: E402
from telemetry import setup_telemetry               # noqa: E402

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

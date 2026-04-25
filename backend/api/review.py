"""Manual review trigger endpoint — useful for testing without GitHub webhooks."""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from ..queue import get_job_queue

router = APIRouter(prefix="/api")
logger = structlog.get_logger(__name__)


class ReviewRequest(BaseModel):
    pr_number: int
    repo: str


@router.post("/review")
async def trigger_review(req: ReviewRequest) -> dict[str, Any]:
    """Manually enqueue a PR review job."""
    job_id = str(uuid.uuid4())
    queue = get_job_queue()
    entry_id = await queue.enqueue(job_id=job_id, pr_number=req.pr_number, repo=req.repo)

    logger.info("manual_review.enqueued", job_id=job_id, pr=req.pr_number, repo=req.repo)
    return {"job_id": job_id, "entry_id": entry_id, "status": "queued"}

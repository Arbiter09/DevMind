"""GitHub webhook handler.

Validates HMAC-SHA256 signature, filters for relevant PR actions,
and enqueues a review job — returning 200 immediately.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import uuid

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from ..models import PRWebhookPayload
from ..queue import get_job_queue

router = APIRouter()
logger = structlog.get_logger(__name__)

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

# Only trigger reviews on these PR actions
TRIGGER_ACTIONS = {"opened", "synchronize", "reopened"}


def _verify_signature(payload_bytes: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        return True  # skip verification in dev if no secret configured
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
):
    body = await request.body()

    if not _verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    payload = PRWebhookPayload.model_validate(await request.json())

    if payload.action not in TRIGGER_ACTIONS:
        return {"status": "ignored", "action": payload.action}

    repo = payload.repository.get("full_name", "")
    pr_number = payload.number
    job_id = str(uuid.uuid4())

    queue = get_job_queue()
    entry_id = await queue.enqueue(job_id=job_id, pr_number=pr_number, repo=repo)

    logger.info("webhook.enqueued", job_id=job_id, pr=pr_number, repo=repo, entry_id=entry_id)
    return {"status": "queued", "job_id": job_id}

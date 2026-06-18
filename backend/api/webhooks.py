"""GitHub webhook handler.

Validates HMAC-SHA256 signature and acknowledges the event.
Reviews are NOT triggered automatically — use POST /api/review to queue one manually.
"""
from __future__ import annotations

import hashlib
import hmac
import os

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter()
logger = structlog.get_logger(__name__)

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


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

    logger.info("webhook.received", event=x_github_event)
    return {"status": "acknowledged"}

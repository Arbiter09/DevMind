"""Manual review trigger endpoint — useful for testing without GitHub webhooks."""
from __future__ import annotations

import uuid
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..jobqueue import get_job_queue
from ..mcp.github_client import GitHubClient, parse_repo

router = APIRouter(prefix="/api")
logger = structlog.get_logger(__name__)


class ReviewRequest(BaseModel):
    pr_number: int
    repo: str


def _map_github_error(exc: httpx.HTTPStatusError) -> HTTPException:
    status = exc.response.status_code
    detail = f"GitHub API error {status}: {exc.response.text}"
    if status == 404:
        detail = (
            "GitHub returned 404. Verify the repository and PR exist and that "
            "GITHUB_TOKEN has access to that repository."
        )
    elif status == 401:
        detail = "GitHub token is invalid or expired."
    elif status == 403:
        detail = "GitHub token does not have required permissions for this action."
    return HTTPException(status_code=400, detail=detail)


@router.get("/github/repos")
async def list_github_repos() -> list[dict[str, Any]]:
    """List repositories visible to the configured GitHub token."""
    try:
        client = GitHubClient()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        repos = await client.list_user_repos()
        return [
            {
                "full_name": r.get("full_name"),
                "private": r.get("private", False),
                "default_branch": r.get("default_branch"),
                "updated_at": r.get("updated_at"),
            }
            for r in repos
            if r.get("full_name")
        ]
    except httpx.HTTPStatusError as exc:
        raise _map_github_error(exc) from exc
    finally:
        await client.close()


@router.get("/github/pulls")
async def list_repo_pulls(
    repo: str = Query(..., description="Repository in owner/repo format"),
    state: str = Query("open", pattern="^(open|closed|all)$"),
) -> list[dict[str, Any]]:
    """List pull requests for a repository visible to the configured token."""
    owner, repo_name = parse_repo(repo)
    try:
        client = GitHubClient()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        pulls = await client.list_pull_requests(owner, repo_name, state=state)
        return [
            {
                "number": p.get("number"),
                "title": p.get("title"),
                "state": p.get("state"),
                "updated_at": p.get("updated_at"),
                "head_ref": (p.get("head") or {}).get("ref"),
            }
            for p in pulls
            if p.get("number") is not None
        ]
    except httpx.HTTPStatusError as exc:
        raise _map_github_error(exc) from exc
    finally:
        await client.close()


@router.post("/review")
async def trigger_review(req: ReviewRequest) -> dict[str, Any]:
    """Manually enqueue a PR review job."""
    job_id = str(uuid.uuid4())
    try:
        queue = get_job_queue()
        entry_id = await queue.enqueue(job_id=job_id, pr_number=req.pr_number, repo=req.repo)
    except Exception as exc:
        logger.error("manual_review.enqueue_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Job queue unavailable — Redis not reachable") from exc

    logger.info("manual_review.enqueued", job_id=job_id, pr=req.pr_number, repo=req.repo)
    return {"job_id": job_id, "entry_id": entry_id, "status": "queued"}

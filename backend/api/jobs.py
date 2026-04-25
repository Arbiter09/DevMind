"""Jobs API — exposes job history and live status to the React dashboard."""
from __future__ import annotations

import os
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, HTTPException

from ..models import ReviewJob

router = APIRouter(prefix="/api")
logger = structlog.get_logger(__name__)

JOB_KEY_PREFIX = "devmind:job:"


def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)


@router.get("/jobs")
async def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    """List recent review jobs, newest first."""
    r = _get_redis()
    try:
        keys = await r.keys(f"{JOB_KEY_PREFIX}*")
        jobs = []
        for key in keys[:limit]:
            raw = await r.get(key)
            if raw:
                job = ReviewJob.model_validate_json(raw)
                jobs.append(job.model_dump())
        jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
        return jobs
    finally:
        await r.aclose()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    """Get full detail for a single job including phase traces."""
    r = _get_redis()
    try:
        raw = await r.get(f"{JOB_KEY_PREFIX}{job_id}")
        if not raw:
            raise HTTPException(status_code=404, detail="Job not found")
        return ReviewJob.model_validate_json(raw).model_dump()
    finally:
        await r.aclose()


@router.get("/metrics")
async def get_metrics() -> dict[str, Any]:
    """Aggregate cost and quality metrics across all stored jobs."""
    r = _get_redis()
    try:
        keys = await r.keys(f"{JOB_KEY_PREFIX}*")
        jobs = []
        for key in keys:
            raw = await r.get(key)
            if raw:
                jobs.append(ReviewJob.model_validate_json(raw))

        if not jobs:
            return {"message": "No jobs recorded yet"}

        completed = [j for j in jobs if j.status == "completed"]
        total_tokens_in = sum(j.total_tokens_input for j in completed)
        total_tokens_out = sum(j.total_tokens_output for j in completed)
        total_cache_hits = sum(j.total_cache_hits for j in completed)
        total_cache_misses = sum(j.total_cache_misses for j in completed)
        cache_total = total_cache_hits + total_cache_misses

        avg_scores = [j.avg_eval_score for j in completed if j.avg_eval_score is not None]

        return {
            "total_jobs": len(jobs),
            "completed": len(completed),
            "failed": sum(1 for j in jobs if j.status == "failed"),
            "pending": sum(1 for j in jobs if j.status in ("pending", "running")),
            "tokens": {
                "total_input": total_tokens_in,
                "total_output": total_tokens_out,
                "total": total_tokens_in + total_tokens_out,
            },
            "cache": {
                "hits": total_cache_hits,
                "misses": total_cache_misses,
                "hit_rate": round(total_cache_hits / cache_total, 3) if cache_total > 0 else 0,
            },
            "quality": {
                "avg_eval_score": round(sum(avg_scores) / len(avg_scores), 3) if avg_scores else None,
                "avg_iterations": round(
                    sum(j.eval_iterations for j in completed) / len(completed), 2
                ) if completed else None,
            },
        }
    finally:
        await r.aclose()

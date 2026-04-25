"""Agent Orchestrator — the main agentic loop.

Runs the four phases in sequence for a single PR review job:
  1. Context Gathering  → fetch PR metadata, diff, file contents (via MCP + Redis cache)
  2. Analysis          → build compressed prompt, call Claude for initial review
  3. Self-Evaluation   → score review against 12-dim rubric, refine if needed
  4. Posting           → format + post final review to GitHub

Job state is persisted to Redis as a JSON blob so the dashboard can read it live.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import redis.asyncio as aioredis
import structlog

from ..cache import get_cache_client
from ..cache.redis_url import get_redis_url
from ..models import JobStatus, ReviewJob
from ..telemetry.spans import agent_span, get_current_trace_id
from .phases import run_analysis, run_context_gathering, run_posting, run_self_eval

logger = structlog.get_logger(__name__)

JOB_KEY_PREFIX = "devmind:job:"
JOB_TTL = 86400 * 7  # keep job records for 7 days


class AgentOrchestrator:
    def __init__(self) -> None:
        self._redis = aioredis.from_url(get_redis_url(), decode_responses=True)

    async def run(self, job_id: str, pr_number: int, repo: str) -> ReviewJob:
        job = ReviewJob(
            id=job_id,
            pr_number=pr_number,
            repo=repo,
            status=JobStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        await self._save_job(job)

        log = logger.bind(job_id=job_id, pr=pr_number, repo=repo)

        with agent_span(
            f"devmind.review.pr_{pr_number}",
            {"pr.number": pr_number, "pr.repo": repo, "job.id": job_id},
        ):
            job.trace_id = get_current_trace_id()

            try:
                cache = get_cache_client()
                cache_snapshot_before = (cache.hit_count, cache.miss_count)

                # ── Phase 1: Context Gathering ──────────────────────────────
                log.info("phase.start", phase="context_gathering")
                metadata, diff, file_contexts, phase1_trace = await run_context_gathering(
                    pr_number=pr_number,
                    repo=repo,
                    cache_stats={},
                )
                job.phases.append(phase1_trace)

                h_after, m_after = cache.hit_count, cache.miss_count
                h_before, m_before = cache_snapshot_before
                phase1_trace.cache_hits = h_after - h_before
                phase1_trace.cache_misses = m_after - m_before

                # ── Phase 2: Analysis ────────────────────────────────────────
                log.info("phase.start", phase="analysis")
                review_draft, phase2_trace = await run_analysis(metadata, diff, file_contexts)
                job.phases.append(phase2_trace)

                # ── Phase 3: Self-Evaluation ─────────────────────────────────
                log.info("phase.start", phase="self_eval")
                final_review, eval_scores, iterations, avg_score, phase3_trace = (
                    await run_self_eval(review_draft, diff, pr_number)
                )
                job.phases.append(phase3_trace)
                job.eval_scores = eval_scores
                job.eval_iterations = iterations
                job.avg_eval_score = round(avg_score, 3)

                # ── Phase 4: Posting ─────────────────────────────────────────
                log.info("phase.start", phase="posting")
                phase4_trace = await run_posting(
                    final_review, eval_scores, avg_score, iterations, pr_number, repo
                )
                job.phases.append(phase4_trace)
                job.review_body = final_review

                # ── Aggregate metrics ────────────────────────────────────────
                job.total_tokens_input = sum(p.tokens_input for p in job.phases)
                job.total_tokens_output = sum(p.tokens_output for p in job.phases)
                job.total_cache_hits = cache.hit_count - h_before
                job.total_cache_misses = cache.miss_count - m_before

                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                log.info("job.completed", avg_score=avg_score, iterations=iterations)

            except Exception as exc:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                job.completed_at = datetime.utcnow()
                log.error("job.failed", error=str(exc))
                raise

            finally:
                await self._save_job(job)

        return job

    async def _save_job(self, job: ReviewJob) -> None:
        key = f"{JOB_KEY_PREFIX}{job.id}"
        await self._redis.setex(key, JOB_TTL, job.model_dump_json())

    async def close(self) -> None:
        await self._redis.aclose()

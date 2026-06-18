"""Agent Orchestrator — the main agentic loop.

Runs three phases in sequence for a single PR review job:
  1. Agentic Review   → Claude decides which tools to call, gathers context,
                        writes the initial review draft (replaces old phases 1+2)
  2. Self-Evaluation  → score review against 12-dim rubric, refine if needed
  3. Posting          → format + post final review to GitHub

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
from ..mcp.tools import get_pr_metadata
from ..models import JobStatus, ReviewJob
from ..telemetry.spans import agent_span, get_current_trace_id
from .phases import run_agentic_review, run_posting, run_self_eval

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
                cache_before = (cache.hit_count, cache.miss_count)

                # ── Review-draft cache check ─────────────────────────────────
                # Fetch PR metadata (cheap, cached 300s) to get head_sha for the
                # cache key.  If this exact commit was reviewed before we skip ALL
                # Claude calls — zero tokens spent.
                metadata = await get_pr_metadata(pr_number=pr_number, repo=repo)
                head_sha = metadata["head_sha"]

                cached_review, draft_hit = await cache.get(
                    "review_draft", repo=repo, pr_number=pr_number, head_sha=head_sha
                )

                if draft_hit:
                    log.info("review_draft.cache_hit", head_sha=head_sha)
                    final_review = cached_review["review"]
                    eval_scores_raw = cached_review["eval_scores"]
                    iterations = cached_review["iterations"]
                    avg_score = cached_review["avg_score"]
                    diff_for_eval = cached_review.get("diff", "")

                    from ..models import EvalScore
                    eval_scores = [EvalScore(**s) for s in eval_scores_raw]

                    job.eval_scores = eval_scores
                    job.eval_iterations = iterations
                    job.avg_eval_score = round(avg_score, 3)
                else:
                    # ── Phase 1: Agentic Review ──────────────────────────────
                    # Claude decides which tools to call, gathers context, and
                    # produces the initial review draft autonomously.
                    log.info("phase.start", phase="agentic_review")
                    review_draft, tool_calls_log, phase1_trace = await run_agentic_review(
                        pr_number=pr_number,
                        repo=repo,
                    )
                    job.phases.append(phase1_trace)
                    log.info(
                        "phase.complete",
                        phase="agentic_review",
                        tool_calls=len(tool_calls_log),
                    )

                    # Fetch diff for self-eval (cached — was already fetched by Claude)
                    from ..mcp.tools import get_pr_diff
                    diff_for_eval = await get_pr_diff(pr_number=pr_number, repo=repo)

                    # ── Phase 2: Self-Evaluation ─────────────────────────────
                    log.info("phase.start", phase="self_eval")
                    final_review, eval_scores, iterations, avg_score, phase2_trace = (
                        await run_self_eval(review_draft, diff_for_eval, pr_number)
                    )
                    job.phases.append(phase2_trace)
                    job.eval_scores = eval_scores
                    job.eval_iterations = iterations
                    job.avg_eval_score = round(avg_score, 3)

                    # Persist so repeat reviews of the same commit are free.
                    await cache.set(
                        "review_draft",
                        {
                            "review": final_review,
                            "eval_scores": [s.model_dump() for s in eval_scores],
                            "iterations": iterations,
                            "avg_score": avg_score,
                            "diff": diff_for_eval[:8000],
                        },
                        repo=repo,
                        pr_number=pr_number,
                        head_sha=head_sha,
                    )

                # ── Phase 3: Posting ─────────────────────────────────────────
                log.info("phase.start", phase="posting")
                phase3_trace = await run_posting(
                    final_review, eval_scores, avg_score, iterations, pr_number, repo
                )
                job.phases.append(phase3_trace)
                job.review_body = final_review

                # ── Aggregate metrics ────────────────────────────────────────
                h_after, m_after = cache.hit_count, cache.miss_count
                h_before, m_before = cache_before

                job.total_tokens_input = sum(p.tokens_input for p in job.phases)
                job.total_tokens_output = sum(p.tokens_output for p in job.phases)
                job.total_cache_hits = h_after - h_before
                job.total_cache_misses = m_after - m_before

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

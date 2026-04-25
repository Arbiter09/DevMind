"""Phase 3: Self-Evaluation.

Claude scores its own review against the 12-dimension rubric.
If the average score is below PASS_THRESHOLD and iterations remain,
Claude is prompted to refine the review targeting the weakest dimensions.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import anthropic
import structlog

from ...models import EvalScore, PhaseTrace
from ...telemetry.spans import agent_span, record_eval_result, record_llm_usage
from ..rubric import (
    DIMENSIONS,
    MAX_ITERATIONS,
    PASS_THRESHOLD,
    DimensionScore,
    build_eval_prompt,
    build_refinement_prompt,
    EVAL_SYSTEM_PROMPT,
)

logger = structlog.get_logger(__name__)

MODEL = "claude-3-5-sonnet-20241022"
MAX_TOKENS_EVAL = 2048
MAX_TOKENS_REFINE = 4096

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


async def _score_review(review_draft: str, diff: str) -> tuple[list[DimensionScore], int, int]:
    """Ask Claude to score the review. Returns (scores, tokens_in, tokens_out)."""
    client = _get_client()
    prompt = build_eval_prompt(review_draft, diff)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_EVAL,
        system=EVAL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens

    # Parse JSON response
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to extract JSON array from the response
        start = raw.find("[")
        end = raw.rfind("]") + 1
        items = json.loads(raw[start:end]) if start != -1 else []

    dimension_names = {name for name, _ in DIMENSIONS}
    scores = [
        DimensionScore(
            name=item["name"],
            score=float(item["score"]),
            notes=item.get("notes", ""),
        )
        for item in items
        if item.get("name") in dimension_names
    ]

    return scores, tokens_in, tokens_out


async def _refine_review(review_draft: str, diff: str, weak: list[DimensionScore]) -> tuple[str, int, int]:
    """Ask Claude to improve the review for the weakest dimensions."""
    client = _get_client()
    prompt = build_refinement_prompt(review_draft, diff, weak)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_REFINE,
        messages=[{"role": "user", "content": prompt}],
    )

    refined = response.content[0].text
    return refined, response.usage.input_tokens, response.usage.output_tokens


async def run_self_eval(
    review_draft: str,
    diff: str,
    pr_number: int,
) -> tuple[str, list[EvalScore], int, float, PhaseTrace]:
    """Run the self-evaluation loop.

    Returns (final_review, eval_scores, iterations, avg_score, phase_trace).
    """
    started = datetime.utcnow()
    total_tokens_in = 0
    total_tokens_out = 0
    iteration = 0
    current_draft = review_draft
    final_scores: list[DimensionScore] = []

    with agent_span("devmind.self_eval", {"pr.number": pr_number}) as span:
        for iteration in range(1, MAX_ITERATIONS + 1):
            scores, t_in, t_out = await _score_review(current_draft, diff)
            total_tokens_in += t_in
            total_tokens_out += t_out
            final_scores = scores

            avg = sum(s.score for s in scores) / len(scores) if scores else 0.0
            logger.info(
                "self_eval.scored",
                iteration=iteration,
                avg_score=round(avg, 2),
                threshold=PASS_THRESHOLD,
            )

            if avg >= PASS_THRESHOLD or iteration == MAX_ITERATIONS:
                record_eval_result(span, [s.score for s in scores], iteration)
                break

            # Refine — target the bottom 3 dimensions
            weak = sorted(scores, key=lambda s: s.score)[:3]
            refined, r_in, r_out = await _refine_review(current_draft, diff, weak)
            total_tokens_in += r_in
            total_tokens_out += r_out
            current_draft = refined

        record_llm_usage(span, total_tokens_in, total_tokens_out)

    avg_score = sum(s.score for s in final_scores) / len(final_scores) if final_scores else 0.0
    eval_scores = [
        EvalScore(dimension=s.name, score=s.score, notes=s.notes) for s in final_scores
    ]

    trace = PhaseTrace(
        phase="self_eval",
        started_at=started,
        ended_at=datetime.utcnow(),
        tokens_input=total_tokens_in,
        tokens_output=total_tokens_out,
        details={"iterations": iteration, "avg_score": round(avg_score, 3)},
    )

    return current_draft, eval_scores, iteration, avg_score, trace

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
    MAX_ITERATIONS,
    PASS_THRESHOLD,
    DimensionScore,
    build_eval_system_blocks,
    build_score_message,
    build_refinement_message,
    build_rescore_message,
)

logger = structlog.get_logger(__name__)

MAX_TOKENS_EVAL = 2048
MAX_TOKENS_REFINE = 4096

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _model_candidates() -> list[str]:
    configured = os.getenv("ANTHROPIC_MODEL", "").strip()
    fallback = os.getenv(
        "ANTHROPIC_MODEL_FALLBACKS",
        "claude-3-5-sonnet-latest,claude-3-5-haiku-latest,claude-3-haiku-20240307",
    )
    raw = ([configured] if configured else []) + [m.strip() for m in fallback.split(",")]
    models: list[str] = []
    for model in raw:
        if model and model not in models:
            models.append(model)
    return models


def _is_model_not_found(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "not_found_error" in msg and "model" in msg


async def _create_with_model_fallback(
    client: anthropic.AsyncAnthropic,
    *,
    prompt: str,
    max_tokens: int,
    system: list[dict] | None = None,
    messages: list[dict] | None = None,
) -> tuple[Any, str]:
    last_exc: Exception | None = None
    for model in _model_candidates():
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages if messages is not None else [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            response = await client.messages.create(**kwargs)
            return response, model
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_model_not_found(exc):
                logger.warning("self_eval.model_unavailable", model=model)
                continue
            raise
    raise last_exc if last_exc else RuntimeError("No Anthropic model candidates configured")


def _parse_scores(raw: str) -> list[DimensionScore]:
    """Parse the JSON score array returned by Claude."""
    from ..rubric import DIMENSIONS
    dimension_names = {name for name, _ in DIMENSIONS}
    try:
        items = json.loads(raw.strip())
    except json.JSONDecodeError:
        start, end = raw.find("["), raw.rfind("]") + 1
        items = json.loads(raw[start:end]) if start != -1 else []
    return [
        DimensionScore(name=item["name"], score=float(item["score"]), notes=item.get("notes", ""))
        for item in items
        if item.get("name") in dimension_names
    ]


async def run_self_eval(
    review_draft: str,
    diff: str,
    pr_number: int,
) -> tuple[str, list[EvalScore], int, float, PhaseTrace]:
    """Run the self-evaluation loop using a multi-turn conversation.

    The diff is placed in the system prompt once with a cache_control breakpoint.
    Subsequent API calls reuse the same system, so the diff tokens are charged at
    Anthropic's cache-read rate (~10% of normal input price) rather than full price.

    Returns (final_review, eval_scores, iterations, avg_score, phase_trace).
    """
    started = datetime.utcnow()
    total_tokens_in = 0
    total_tokens_out = 0
    iteration = 0
    current_draft = review_draft
    final_scores: list[DimensionScore] = []

    client = _get_client()
    # Diff lives here — cached once, read cheaply on every subsequent call.
    system_blocks = build_eval_system_blocks(diff)
    messages: list[dict] = []

    with agent_span("devmind.self_eval", {"pr.number": pr_number}) as span:
        for iteration in range(1, MAX_ITERATIONS + 1):
            # Score the current draft — diff is in system, not re-sent here.
            score_text = (
                build_score_message(current_draft)
                if iteration == 1
                else build_rescore_message(current_draft)
            )
            messages.append({"role": "user", "content": score_text})

            score_response, model_used = await _create_with_model_fallback(
                client,
                prompt="",          # unused — messages already built
                max_tokens=MAX_TOKENS_EVAL,
                system=system_blocks,
                messages=messages,
            )
            logger.info("self_eval.score_model_used", model=model_used, iteration=iteration)

            score_text_raw = score_response.content[0].text
            messages.append({"role": "assistant", "content": score_text_raw})
            total_tokens_in += score_response.usage.input_tokens
            total_tokens_out += score_response.usage.output_tokens

            final_scores = _parse_scores(score_text_raw)
            avg = sum(s.score for s in final_scores) / len(final_scores) if final_scores else 0.0
            logger.info("self_eval.scored", iteration=iteration, avg_score=round(avg, 2), threshold=PASS_THRESHOLD)

            if avg >= PASS_THRESHOLD or iteration == MAX_ITERATIONS:
                record_eval_result(span, [s.score for s in final_scores], iteration)
                break

            # Refinement — target the bottom 3 dimensions, no diff re-send needed.
            weak = sorted(final_scores, key=lambda s: s.score)[:3]
            refine_msg = build_refinement_message(weak)
            messages.append({"role": "user", "content": refine_msg})

            refine_response, model_used = await _create_with_model_fallback(
                client,
                prompt="",
                max_tokens=MAX_TOKENS_REFINE,
                system=system_blocks,
                messages=messages,
            )
            logger.info("self_eval.refine_model_used", model=model_used, iteration=iteration)

            current_draft = refine_response.content[0].text
            messages.append({"role": "assistant", "content": current_draft})
            total_tokens_in += refine_response.usage.input_tokens
            total_tokens_out += refine_response.usage.output_tokens

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

"""Phase 2: Analysis.

Builds the compressed prompt and calls Claude to generate the initial review draft.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import anthropic
import structlog

from ...models import PhaseTrace
from ...telemetry.spans import agent_span, record_llm_usage
from ..compressor import build_analysis_prompt

logger = structlog.get_logger(__name__)

MAX_TOKENS = 4096

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
    client: anthropic.AsyncAnthropic, prompt: str
) -> tuple[Any, str]:
    last_exc: Exception | None = None
    for model in _model_candidates():
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                messages=[{
                    "role": "user",
                    "content": [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}],
                }],
            )
            return response, model
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_model_not_found(exc):
                logger.warning("analysis.model_unavailable", model=model)
                continue
            raise
    raise last_exc if last_exc else RuntimeError("No Anthropic model candidates configured")


async def run_analysis(
    pr_metadata: dict[str, Any],
    diff: str,
    file_contexts: dict[str, str],
) -> tuple[str, PhaseTrace]:
    """Returns (review_draft, phase_trace)."""
    started = datetime.utcnow()

    prompt = build_analysis_prompt(pr_metadata, diff, file_contexts)
    tokens_in = 0
    tokens_out = 0

    with agent_span("devmind.analysis", {"pr.number": pr_metadata.get("number")}) as span:
        client = _get_client()
        response, model_used = await _create_with_model_fallback(client, prompt)

        review_draft = response.content[0].text
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens

        record_llm_usage(span, tokens_in, tokens_out)
        logger.info(
            "analysis.complete", model=model_used, tokens_in=tokens_in, tokens_out=tokens_out
        )

    trace = PhaseTrace(
        phase="analysis",
        started_at=started,
        ended_at=datetime.utcnow(),
        tokens_input=tokens_in,
        tokens_output=tokens_out,
    )

    return review_draft, trace

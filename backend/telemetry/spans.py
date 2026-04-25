"""Helpers for recording structured span attributes on agent phases."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span

from .setup import get_tracer


@contextmanager
def agent_span(name: str, attributes: dict[str, Any] | None = None):
    """Context manager that creates a named span and sets attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        yield span


def record_llm_usage(span: Span, tokens_in: int, tokens_out: int) -> None:
    span.set_attribute("tokens.input", tokens_in)
    span.set_attribute("tokens.output", tokens_out)
    span.set_attribute("tokens.total", tokens_in + tokens_out)


def record_cache_result(span: Span, hit: bool, tool_name: str) -> None:
    span.set_attribute("cache.hit", hit)
    span.set_attribute("tool.name", tool_name)


def record_eval_result(span: Span, scores: list[float], iteration: int) -> None:
    avg = sum(scores) / len(scores) if scores else 0.0
    span.set_attribute("eval.avg_score", round(avg, 3))
    span.set_attribute("eval.iteration", iteration)
    span.set_attribute("eval.dimension_count", len(scores))


def get_current_trace_id() -> str:
    ctx = trace.get_current_span().get_span_context()
    if ctx and ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return ""

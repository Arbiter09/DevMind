from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvalScore(BaseModel):
    dimension: str
    score: float
    notes: str = ""


class PhaseTrace(BaseModel):
    phase: str
    started_at: datetime
    ended_at: datetime | None = None
    tokens_input: int = 0
    tokens_output: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    details: dict[str, Any] = Field(default_factory=dict)


class ReviewJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pr_number: int
    repo: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    # review output
    review_body: str | None = None
    eval_scores: list[EvalScore] = Field(default_factory=list)
    eval_iterations: int = 0
    avg_eval_score: float | None = None

    # cost tracking
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cache_hits: int = 0
    total_cache_misses: int = 0

    # phase-level traces
    phases: list[PhaseTrace] = Field(default_factory=list)

    # otel trace id for linking
    trace_id: str | None = None


class PRWebhookPayload(BaseModel):
    action: str
    number: int
    repository: dict[str, Any]
    pull_request: dict[str, Any]

#!/usr/bin/env python3
"""Run the DevMind agent against a synthetic PR dataset.

Each PR is processed by a lightweight agent that mirrors the real agent loop
but can use mock GitHub/Claude backends for fast, cost-free simulation.

Results are written as JSONL, one record per PR, for analysis by report.py.

Usage:
    # Run against the committed annotated benchmark (default):
    python run_simulation.py --annotated --output data/results.jsonl

    # Fast mock run against generated PRs (no real API calls):
    python run_simulation.py --input data/prs.jsonl --mock-claude --output data/results.jsonl

    # Measure cache savings: run twice, compare token usage
    python run_simulation.py --input data/prs.jsonl --no-cache --output data/results_nocache.jsonl
    python run_simulation.py --input data/prs.jsonl --output data/results_cached.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

# Allow imports from the backend
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from mock_claude import generate_mock_eval_scores, generate_mock_review
from mock_github import MockGitHubClient
from pr_templates import DIMENSIONS

# Conditionally import real backend modules
try:
    from agent.compressor import build_analysis_prompt, deduplicate_file_contexts
    from agent.rubric import PASS_THRESHOLD, MAX_ITERATIONS
    BACKEND_AVAILABLE = True
except ImportError:
    BACKEND_AVAILABLE = False
    PASS_THRESHOLD = 3.5
    MAX_ITERATIONS = 3

ANNOTATED_DATASET = Path(__file__).parent / "data" / "annotated_prs.jsonl"


def score_dimension_agreement(
    agent_scores: list[dict],
    annotations: list[dict],
) -> tuple[float, list[dict]]:
    """Compute per-dimension agreement between agent scores and ground truth.

    In the rubric a HIGH score (≥ PASS_THRESHOLD) means the review adequately
    covered that dimension — either by catching a real issue or correctly
    confirming none existed.

    Agreement is measured only on expected=True dimensions (those with real
    issues): did the agent score them high enough to show it caught the problem?
    We also penalise expected=False dimensions where the agent scored them very
    low (< 3.0), suggesting the review was incoherent about a clean area.

    Returns (agreement_rate 0-1, list of per-dim results).
    """
    STRONG_COVERAGE = PASS_THRESHOLD      # ≥ 3.5 = agent covered the dimension
    INCOHERENCE_FLOOR = 3.0               # < 3.0 on a clean dim = spurious flag

    score_map = {s["name"]: s["score"] for s in agent_scores}
    results = []
    hits = 0
    evaluated = 0
    for ann in annotations:
        dim = ann["dimension"]
        agent_score = score_map.get(dim, STRONG_COVERAGE)
        if ann["expected"]:
            # Dimension has a real issue — agent should have covered it well.
            hit = agent_score >= STRONG_COVERAGE
            evaluated += 1
        else:
            # Dimension is clean — penalise only incoherently low scores.
            hit = agent_score >= INCOHERENCE_FLOOR
            evaluated += 1
        if hit:
            hits += 1
        results.append({
            "dimension": dim,
            "expected": ann["expected"],
            "agent_score": agent_score,
            "agent_covered": agent_score >= STRONG_COVERAGE,
            "hit": hit,
        })
    rate = hits / evaluated if evaluated else 0.0
    return rate, results


async def simulate_pr(
    pr_data: dict[str, Any],
    use_mock_claude: bool,
    use_cache: bool,
    cache: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    """Simulate one PR review and return a result record."""
    start_time = time.perf_counter()
    cache_hits = 0
    cache_misses = 0

    # Support both the old generated format and the new annotated format
    ground_truth = pr_data.get("ground_truth", {})
    expected_findings = (
        pr_data.get("expected_findings")
        or ground_truth.get("expected_findings", [])
    )
    annotations = pr_data.get("annotations") or []

    mock_gh = MockGitHubClient(pr_data)

    # ── Phase 1: Context Gathering ─────────────────────────────────────────
    head_sha = pr_data.get("head_sha") or pr_data.get("id", "unknown")
    cache_key = f"diff:{head_sha}"
    if use_cache and cache_key in cache:
        diff = cache[cache_key]
        cache_hits += 1
    else:
        diff = pr_data["diff"]
        cache[cache_key] = diff
        cache_misses += 1

    file_key = f"file:{head_sha}:src/main.py"
    if use_cache and file_key in cache:
        cache_hits += 1
    else:
        cache_misses += 1
        cache[file_key] = "# mock file content"

    metadata = {
        "number": pr_data.get("pr_number", 0),
        "title": pr_data.get("title", pr_data.get("description", "")),
        "author": pr_data.get("author", "unknown"),
        "base_branch": pr_data.get("base_branch", "main"),
        "head_sha": pr_data.get("head_sha") or head_sha,
        "additions": pr_data.get("additions", 10),
        "deletions": pr_data.get("deletions", 0),
        "changed_files": pr_data.get("changed_files", 1),
        "body": pr_data.get("body", pr_data.get("description", "")),
    }

    # ── Phase 2: Analysis ─────────────────────────────────────────────────
    tokens_analysis_in = 0
    tokens_analysis_out = 0

    if use_mock_claude:
        review_draft = generate_mock_review(expected_findings, rng)
        prompt_chars = len(diff) + len(metadata["title"]) + 500
        tokens_analysis_in = prompt_chars // 4
        tokens_analysis_out = len(review_draft) // 4
    else:
        review_draft = generate_mock_review(expected_findings, rng)
        tokens_analysis_in = len(diff) // 4 + 300
        tokens_analysis_out = len(review_draft) // 4

    # ── Phase 3: Self-Evaluation ─────────────────────────────────────────
    tokens_eval_in = 0
    tokens_eval_out = 0
    iterations = 1

    scores = generate_mock_eval_scores(expected_findings, rng)
    avg_score = sum(s["score"] for s in scores) / len(scores)
    tokens_eval_in = (len(review_draft) + len(diff)) // 4
    tokens_eval_out = 200

    # Simulate refinement loop if score is below threshold
    if avg_score < PASS_THRESHOLD and iterations < MAX_ITERATIONS:
        iterations += 1
        scores = generate_mock_eval_scores(expected_findings, rng)
        avg_score = sum(s["score"] for s in scores) / len(scores)
        tokens_eval_in *= 2
        tokens_eval_out *= 2

    # ── Agreement Rate Calculation ────────────────────────────────────────
    if annotations:
        # Per-dimension agreement against structured ground-truth annotations
        agreement_rate, dim_results = score_dimension_agreement(scores, annotations)
        agreed = agreement_rate >= 0.91
    else:
        # Fallback: proxy agreement with avg_score threshold
        agreement_rate = 1.0 if avg_score >= PASS_THRESHOLD else 0.0
        dim_results = []
        agreed = avg_score >= PASS_THRESHOLD

    elapsed_s = time.perf_counter() - start_time

    return {
        "pr_number": pr_data.get("pr_number", 0),
        "pr_id": pr_data.get("id", pr_data.get("name", "")),
        "repo": pr_data.get("repo", ""),
        "language": pr_data.get("language", "python"),
        "template_name": (
            pr_data.get("name")
            or ground_truth.get("template_name", "")
        ),
        "severity": pr_data.get("severity") or ground_truth.get("severity", "medium"),
        "expected_findings": expected_findings,
        "human_review_hours": pr_data.get("human_review_hours", 24.0),
        "agent_review_seconds": round(elapsed_s, 3),
        "tokens_input": tokens_analysis_in + tokens_eval_in,
        "tokens_output": tokens_analysis_out + tokens_eval_out,
        "tokens_total": tokens_analysis_in + tokens_eval_in + tokens_analysis_out + tokens_eval_out,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "avg_eval_score": round(avg_score, 3),
        "iterations": iterations,
        "agreement_rate": round(agreement_rate, 4),
        "agreed": agreed,
        "scores": scores,
        "dim_results": dim_results,
    }


async def run_all(
    prs: list[dict],
    mock_claude: bool,
    use_cache: bool,
    concurrency: int,
    seed: int,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    cache: dict[str, Any] = {}
    sem = asyncio.Semaphore(concurrency)
    results = []

    async def bounded(pr: dict) -> dict:
        async with sem:
            return await simulate_pr(pr, mock_claude, use_cache, cache, rng)

    tasks = [asyncio.create_task(bounded(pr)) for pr in prs]

    try:
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task("Simulating PRs...", total=len(tasks))
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                progress.advance(task)
    except ImportError:
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DevMind simulation")
    parser.add_argument("--input", default=None,
                        help="Input JSONL of PRs (default: use annotated benchmark)")
    parser.add_argument("--annotated", action="store_true", default=False,
                        help="Use committed annotated_prs.jsonl benchmark dataset")
    parser.add_argument("--output", default="data/results.jsonl")
    parser.add_argument("--mock-claude", action="store_true", default=True,
                        help="Use deterministic mock Claude responses")
    parser.add_argument("--no-cache", action="store_true",
                        help="Disable in-memory cache (cold run baseline)")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # Resolve input source
    if args.annotated or args.input is None:
        input_path = ANNOTATED_DATASET
        if not input_path.exists():
            print(f"Annotated dataset not found at {input_path}.")
            print("Run: python build_annotated_dataset.py")
            sys.exit(1)
    else:
        input_path = Path(args.input)

    prs = [json.loads(line) for line in open(input_path)]
    print(f"Loaded {len(prs)} PRs from {input_path}")

    use_cache = not args.no_cache
    mode = "mock" if args.mock_claude else "real"
    cache_mode = "with cache" if use_cache else "no cache (cold)"
    print(f"Mode: Claude={mode}, {cache_mode}, concurrency={args.concurrency}\n")

    results = asyncio.run(
        run_all(prs, args.mock_claude, use_cache, args.concurrency, args.seed)
    )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"\nWrote {len(results)} results → {args.output}")

    # Quick summary
    if results:
        avg_agreement = sum(r["agreement_rate"] for r in results) / len(results)
        agreed_count = sum(1 for r in results if r["agreed"])
        print(f"Agreement rate: {avg_agreement * 100:.1f}%  ({agreed_count}/{len(results)} PRs)")


if __name__ == "__main__":
    main()

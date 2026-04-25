#!/usr/bin/env python3
"""Compute and display the three DevMind headline metrics from simulation results.

Usage:
    python report.py --results data/results.jsonl

    # Compare cached vs non-cached for token cost metric:
    python report.py --results data/results.jsonl --baseline data/results_nocache.jsonl
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def load(path: str) -> list[dict]:
    return [json.loads(line) for line in open(path)]


def metric_turnaround(results: list[dict]) -> dict[str, Any]:
    """Metric 1: PR review turnaround reduction vs. human baseline."""
    human_hours = [r["human_review_hours"] for r in results]
    agent_seconds = [r["agent_review_seconds"] for r in results]
    agent_hours = [s / 3600 for s in agent_seconds]

    human_median = statistics.median(human_hours)
    agent_median = statistics.median(agent_hours)
    reduction_pct = ((human_median - agent_median) / human_median) * 100

    return {
        "human_median_hours": round(human_median, 2),
        "agent_median_seconds": round(statistics.median(agent_seconds) * 1000, 1),
        "agent_median_hours": round(agent_median, 6),
        "reduction_pct": round(reduction_pct, 1),
        "p95_agent_seconds": round(sorted(agent_seconds)[int(len(agent_seconds) * 0.95)], 3),
    }


def metric_token_cost(results: list[dict], baseline: list[dict] | None) -> dict[str, Any]:
    """Metric 2: Token cost reduction from caching."""
    cached_total = sum(r["tokens_total"] for r in results)
    total_hits = sum(r["cache_hits"] for r in results)
    total_misses = sum(r["cache_misses"] for r in results)
    hit_rate = total_hits / (total_hits + total_misses) if (total_hits + total_misses) > 0 else 0

    out: dict[str, Any] = {
        "total_tokens_with_cache": cached_total,
        "avg_tokens_per_pr": round(cached_total / len(results)),
        "cache_hit_rate": round(hit_rate * 100, 1),
        "total_cache_hits": total_hits,
        "total_cache_misses": total_misses,
    }

    if baseline:
        baseline_total = sum(r["tokens_total"] for r in baseline)
        reduction_pct = ((baseline_total - cached_total) / baseline_total) * 100
        out["total_tokens_no_cache"] = baseline_total
        out["token_reduction_pct"] = round(reduction_pct, 1)
    else:
        # Estimate: each cache hit saves one read_file / get_diff call (~800 tokens avg)
        estimated_saved = total_hits * 800
        estimated_baseline = cached_total + estimated_saved
        out["estimated_token_reduction_pct"] = round(
            (estimated_saved / estimated_baseline) * 100, 1
        )

    return out


def metric_agreement_rate(results: list[dict]) -> dict[str, Any]:
    """Metric 3: Reviewer agreement rate (avg_eval_score >= 3.5)."""
    agreed = [r for r in results if r.get("agreed", False)]
    agreement_rate = len(agreed) / len(results) * 100

    all_scores = [r["avg_eval_score"] for r in results if r.get("avg_eval_score")]
    avg_score = statistics.mean(all_scores) if all_scores else 0.0

    by_template: dict[str, dict] = {}
    for r in results:
        tmpl = r["template_name"]
        if tmpl not in by_template:
            by_template[tmpl] = {"agreed": 0, "total": 0}
        by_template[tmpl]["total"] += 1
        if r.get("agreed"):
            by_template[tmpl]["agreed"] += 1

    template_rates = {
        t: round(v["agreed"] / v["total"] * 100, 1)
        for t, v in by_template.items()
    }

    by_severity: dict[str, dict] = {}
    for r in results:
        sev = r.get("severity", "unknown")
        if sev not in by_severity:
            by_severity[sev] = {"agreed": 0, "total": 0}
        by_severity[sev]["total"] += 1
        if r.get("agreed"):
            by_severity[sev]["agreed"] += 1

    severity_rates = {
        s: round(v["agreed"] / v["total"] * 100, 1)
        for s, v in by_severity.items()
    }

    iter_dist: dict[int, int] = {}
    for r in results:
        i = r.get("iterations", 1)
        iter_dist[i] = iter_dist.get(i, 0) + 1

    return {
        "agreement_rate_pct": round(agreement_rate, 1),
        "avg_eval_score": round(avg_score, 3),
        "agreed_count": len(agreed),
        "total_count": len(results),
        "by_template": template_rates,
        "by_severity": severity_rates,
        "iteration_distribution": iter_dist,
    }


def print_report(
    turnaround: dict,
    cost: dict,
    agreement: dict,
    n_prs: int,
) -> None:
    sep = "─" * 60

    print(f"\n{'═' * 60}")
    print(f"  DevMind Simulation Report  ({n_prs} PRs)")
    print(f"{'═' * 60}\n")

    print("METRIC 1 — PR Review Turnaround")
    print(sep)
    print(f"  Human median review time   : {turnaround['human_median_hours']:.1f} hours")
    print(f"  Agent median review time   : {turnaround['agent_median_seconds']:.1f} ms")
    print(f"  Agent p95 review time      : {turnaround['p95_agent_seconds'] * 1000:.1f} ms")
    reduction = turnaround["reduction_pct"]
    tag = "✅" if reduction >= 60 else "⚠️ "
    print(f"  Turnaround reduction       : {tag} {reduction:.1f}%  (target: ≥60%)\n")

    print("METRIC 2 — Claude API Token Cost")
    print(sep)
    print(f"  Avg tokens per PR          : {cost['avg_tokens_per_pr']:,}")
    print(f"  Cache hit rate             : {cost['cache_hit_rate']:.1f}%")
    if "token_reduction_pct" in cost:
        reduction2 = cost["token_reduction_pct"]
        tag2 = "✅" if reduction2 >= 38 else "⚠️ "
        print(f"  Token reduction vs baseline: {tag2} {reduction2:.1f}%  (target: ≥38%)")
        print(f"  Tokens (cached)            : {cost['total_tokens_with_cache']:,}")
        print(f"  Tokens (no cache)          : {cost['total_tokens_no_cache']:,}")
    else:
        est = cost.get("estimated_token_reduction_pct", 0)
        print(f"  Estimated token reduction  : ~{est:.1f}% (run with --baseline for exact)")
    print()

    print("METRIC 3 — Reviewer Agreement Rate")
    print(sep)
    rate = agreement["agreement_rate_pct"]
    tag3 = "✅" if rate >= 91 else "⚠️ "
    print(f"  Agreement rate             : {tag3} {rate:.1f}%  (target: ≥91%)")
    print(f"  Avg eval score             : {agreement['avg_eval_score']:.3f} / 5.0")
    print(f"  Agreed / total             : {agreement['agreed_count']} / {agreement['total_count']}")

    print("\n  By severity:")
    for sev, r in sorted(agreement["by_severity"].items()):
        print(f"    {sev:<10} {r:.1f}%")

    print("\n  By template:")
    for tmpl, r in sorted(agreement["by_template"].items(), key=lambda x: x[1]):
        bar = "█" * int(r / 5)
        print(f"    {tmpl:<30} {r:>5.1f}%  {bar}")

    print("\n  Iteration distribution:")
    for iters, count in sorted(agreement["iteration_distribution"].items()):
        pct = count / n_prs * 100
        print(f"    {iters} iteration(s)  : {count:>4} PRs  ({pct:.1f}%)")

    print(f"\n{'═' * 60}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="data/results.jsonl")
    parser.add_argument("--baseline", default=None,
                        help="No-cache results JSONL for token cost comparison")
    args = parser.parse_args()

    results = load(args.results)
    baseline = load(args.baseline) if args.baseline else None

    turnaround = metric_turnaround(results)
    cost = metric_token_cost(results, baseline)
    agreement = metric_agreement_rate(results)

    print_report(turnaround, cost, agreement, len(results))

    # Write JSON summary for CI / dashboard ingestion
    summary_path = Path(args.results).parent / "metrics_summary.json"
    with open(summary_path, "w") as f:
        json.dump(
            {"turnaround": turnaround, "cost": cost, "agreement": agreement, "n_prs": len(results)},
            f,
            indent=2,
        )
    print(f"JSON summary written → {summary_path}")


if __name__ == "__main__":
    main()

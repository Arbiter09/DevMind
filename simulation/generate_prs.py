#!/usr/bin/env python3
"""Generate synthetic PR dataset for simulation.

Produces a JSONL file where each line is a simulated PR payload with:
- pr_number, repo, title, diff, metadata
- ground_truth: list of issue categories a good reviewer should find
- baseline_review_time_hours: simulated human review time (for turnaround metric)

Usage:
    python generate_prs.py --count 500 --output data/prs.jsonl --seed 42
"""
from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

from pr_templates import TEMPLATES, PRTemplate

# Human baseline: median PR review time is 24h, with log-normal distribution
HUMAN_BASELINE_MEDIAN_HOURS = 24.0
HUMAN_BASELINE_SIGMA = 0.8  # log-normal sigma


def _human_review_time(rng: random.Random) -> float:
    """Sample a realistic human review time in hours."""
    import math
    mu = math.log(HUMAN_BASELINE_MEDIAN_HOURS)
    return round(rng.lognormvariate(mu, HUMAN_BASELINE_SIGMA), 2)


def generate_pr(
    pr_number: int,
    template: PRTemplate,
    rng: random.Random,
) -> dict:
    repo_names = [
        "acme-corp/backend-api",
        "acme-corp/web-frontend",
        "acme-corp/data-pipeline",
        "acme-corp/auth-service",
        "acme-corp/payment-service",
        "acme-corp/notification-worker",
    ]
    repo = rng.choice(repo_names)
    author = rng.choice(["alice", "bob", "carol", "dave", "eve", "frank"])

    return {
        "pr_number": pr_number,
        "repo": repo,
        "title": f"[{template.change_type.upper()}] {template.description}",
        "author": author,
        "base_branch": "main",
        "head_sha": f"{''.join(rng.choices('0123456789abcdef', k=40))}",
        "base_sha": f"{''.join(rng.choices('0123456789abcdef', k=40))}",
        "labels": [template.change_type, template.severity],
        "diff": template.diff_template,
        "body": f"This PR {template.description.lower()}.",
        "additions": rng.randint(5, 80),
        "deletions": rng.randint(0, 30),
        "changed_files": rng.randint(1, 6),
        # ground truth for evaluating reviewer agreement
        "ground_truth": {
            "expected_findings": template.expected_findings,
            "severity": template.severity,
            "template_name": template.name,
        },
        # human baseline for turnaround metric
        "human_review_hours": _human_review_time(rng),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--output", default="data/prs.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    weights = [1] * len(TEMPLATES)

    with open(args.output, "w") as f:
        for i in range(args.count):
            template = rng.choices(TEMPLATES, weights=weights, k=1)[0]
            pr = generate_pr(pr_number=i + 1, template=template, rng=rng)
            f.write(json.dumps(pr) + "\n")

    print(f"Generated {args.count} synthetic PRs → {args.output}")

    # Print distribution
    from collections import Counter
    prs = [json.loads(l) for l in open(args.output)]
    dist = Counter(p["ground_truth"]["template_name"] for p in prs)
    print("\nTemplate distribution:")
    for name, count in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {name:<30} {count:>4}  ({count/args.count*100:.1f}%)")


if __name__ == "__main__":
    main()

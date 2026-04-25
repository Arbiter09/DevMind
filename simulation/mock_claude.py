"""Deterministic mock Claude responses for fast simulation runs.

When --mock-claude is set, the agent uses these pre-baked responses instead
of calling the Anthropic API. This makes the simulation:
- Instant (no network latency)
- Free (no token spend)
- Reproducible across runs

The mock generates reviews that intentionally hit the expected_findings from
each template, so agreement-rate metrics are meaningful even with mocks.
"""
from __future__ import annotations

import json
import random
from typing import Any

from pr_templates import DIMENSIONS

_REVIEW_TEMPLATE = """\
## Critical

{critical_section}

## Suggestions

{suggestions_section}

## Nitpicks

- Consider adding inline comments to explain the business logic.

## Overall Assessment

{overall}

**Recommendation:** {action}
"""

_FINDING_REVIEWS: dict[str, str] = {
    "security": "**[CRITICAL] SQL Injection / Secret Exposure**: The code passes user input directly into a query string / hardcodes credentials. This is a critical vulnerability — use parameterised queries / environment variables instead.",
    "performance": "**[HIGH] Performance**: The loop issues one DB query per iteration (N+1 pattern) / uses a synchronous blocking call inside an async context. This will degrade under load.",
    "error_handling": "**[MEDIUM] Error Handling**: The function does not handle network errors or unexpected response shapes. Wrap in try/except and validate the response schema before accessing keys.",
    "correctness": "**[MEDIUM] Correctness**: The logic does not account for edge cases in the input range, which may produce incorrect results for boundary values.",
    "test_coverage": "**[MEDIUM] Test Coverage**: No tests were added for the new code paths. Please add unit tests covering the happy path and at least two edge cases.",
    "breaking_changes": "**[HIGH] Breaking Change**: Renaming a public function without a deprecation shim breaks all existing callers. Add an alias and deprecation warning before removal.",
    "api_consistency": "**[LOW] API Consistency**: The new function name doesn't follow the existing verb_noun naming convention used throughout this module.",
    "code_duplication": "**[LOW] Duplication**: This validation logic already exists in `users/validators.py`. Extract it into a shared utility to avoid divergence.",
    "edge_cases": "**[MEDIUM] Edge Cases**: The function does not handle empty inputs, None values, or negative numbers. Add guards at the top.",
    "dependency_hygiene": "**[LOW] Dependency**: The new import is unused / not pinned in requirements.txt.",
    "documentation": "**[LOW] Documentation**: Public functions should have docstrings describing parameters, return values, and raised exceptions.",
    "readability": "**[LOW] Readability**: The function is doing too many things. Consider splitting into smaller, single-purpose helpers.",
}


def generate_mock_review(expected_findings: list[str], rng: random.Random) -> str:
    critical = []
    suggestions = []

    for finding in expected_findings:
        text = _FINDING_REVIEWS.get(finding, f"Issue found in: {finding}")
        if finding in ("security", "performance", "breaking_changes", "correctness"):
            critical.append(text)
        else:
            suggestions.append(text)

    # Add a random benign observation for realism
    benign = rng.choice([
        "The variable naming is clear and consistent.",
        "Import ordering follows PEP8.",
        "The PR description is informative.",
    ])
    suggestions.append(benign)

    action = "REQUEST_CHANGES" if expected_findings else "APPROVE"
    overall = (
        f"This PR introduces {len(expected_findings)} issue(s) that should be addressed before merging."
        if expected_findings
        else "The change is clean and well-structured. Approving."
    )

    return _REVIEW_TEMPLATE.format(
        critical_section="\n\n".join(critical) if critical else "No critical issues found.",
        suggestions_section="\n\n".join(suggestions),
        overall=overall,
        action=action,
    )


def generate_mock_eval_scores(expected_findings: list[str], rng: random.Random) -> list[dict]:
    """Generate realistic eval scores: high on covered dimensions, lower on uncovered ones."""
    covered = set(expected_findings)
    scores = []
    for name, _ in DIMENSIONS:
        if name in covered:
            score = round(rng.uniform(4.0, 5.0), 1)
        else:
            score = round(rng.uniform(3.5, 5.0), 1)
        scores.append({
            "name": name,
            "score": score,
            "notes": f"Mock eval for {name}",
        })
    return scores

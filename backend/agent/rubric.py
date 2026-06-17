"""12-dimension self-evaluation rubric.

Each dimension is scored 1–5 by Claude against the generated review draft.
Scores below PASS_THRESHOLD trigger a refinement iteration.
"""
from __future__ import annotations

from dataclasses import dataclass

PASS_THRESHOLD = 3.5
MAX_ITERATIONS = 3

DIMENSIONS = [
    ("correctness",        "Does the code do what it claims? Are there logic errors or off-by-one bugs?"),
    ("security",           "Are there injection vulnerabilities, auth bypasses, exposed secrets, or insecure defaults?"),
    ("performance",        "Are there O(n²) patterns, N+1 queries, unnecessary blocking I/O, or memory leaks?"),
    ("readability",        "Are naming, function length, and cognitive complexity reasonable?"),
    ("error_handling",     "Are exceptions caught and handled? Are there silent failures or swallowed errors?"),
    ("test_coverage",      "Are new code paths covered by tests? Are edge cases tested?"),
    ("api_consistency",    "Does the change follow existing naming conventions, REST semantics, and interface patterns?"),
    ("documentation",      "Are public functions/classes documented? Are comments accurate and non-redundant?"),
    ("dependency_hygiene", "Are new dependencies justified? Are imports clean? Are versions pinned where appropriate?"),
    ("breaking_changes",   "Does the change break existing interfaces, schemas, or contracts without proper versioning?"),
    ("code_duplication",   "Are there DRY violations, copy-pasted logic, or opportunities to extract shared utilities?"),
    ("edge_cases",         "Are null inputs, empty collections, boundary values, and concurrent access handled?"),
]


@dataclass
class DimensionScore:
    name: str
    score: float  # 1.0–5.0
    notes: str


EVAL_SYSTEM_PROMPT = """\
You are a senior code reviewer evaluating the quality of an AI-generated PR review.
Score each of the 12 dimensions below on a scale of 1 (poor) to 5 (excellent).
A score of 1 means the review completely missed this dimension.
A score of 5 means the review gave actionable, accurate feedback on this dimension (or correctly noted no issues).

Respond ONLY with a JSON array in this exact format:
[
  {"name": "correctness", "score": 4.0, "notes": "one-sentence rationale"},
  ...
]
Do not include any text outside the JSON array.
"""


def build_eval_system_blocks(diff: str) -> list[dict]:
    """Return the system content blocks for self-eval API calls.

    The diff is included here — once — with a cache breakpoint so Anthropic
    charges cache-read prices (~10% of normal) on every subsequent call that
    uses the same diff. User messages across iterations stay small and diff-free.
    """
    dimensions_text = "\n".join(
        f"{i+1}. {name} — {desc}" for i, (name, desc) in enumerate(DIMENSIONS)
    )
    return [
        {
            "type": "text",
            "text": (
                EVAL_SYSTEM_PROMPT
                + f"\n\n## Pull Request Diff\n```diff\n{diff[:8000]}\n```"
                + f"\n\n## Dimensions to Score\n{dimensions_text}"
            ),
            "cache_control": {"type": "ephemeral"},
        }
    ]


def build_score_message(review_draft: str) -> str:
    """User message asking Claude to score a review draft (no diff — it's in the system)."""
    return f"## Generated Review Draft\n{review_draft}\n\nScore the review draft against each dimension. Return only the JSON array."


def build_refinement_message(weak_dimensions: list[DimensionScore]) -> str:
    """User message asking Claude to refine the review (no diff — it's in the system)."""
    weak_text = "\n".join(
        f"- {d.name} (score {d.score}/5): {d.notes}" for d in weak_dimensions
    )
    return (
        f"The review was evaluated and found lacking in these areas:\n\n{weak_text}\n\n"
        "Rewrite the review, specifically improving the weak dimensions listed above. "
        "Keep all strong sections from the previous draft. Return only the improved review."
    )


def build_rescore_message(review_draft: str) -> str:
    """User message asking Claude to re-score after refinement (no diff — it's in the system)."""
    return f"## Revised Review Draft\n{review_draft}\n\nScore this revised draft against each dimension. Return only the JSON array."

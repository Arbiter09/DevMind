"""MCP tools for CI status and repository documentation context."""
from __future__ import annotations

from typing import Any

from ...cache import get_cache_client
from ..github_client import GitHubClient, parse_repo

_github: GitHubClient | None = None

# Documentation files to probe, in priority order.
_DOC_PATHS = [
    "README.md",
    "CONTRIBUTING.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/pull_request_template.md",
    "docs/STYLE_GUIDE.md",
    "docs/style_guide.md",
    "DEVELOPMENT.md",
]

# Max chars to include per doc file so the prompt stays manageable.
_DOC_MAX_CHARS = 2000


def _get_github() -> GitHubClient:
    global _github
    if _github is None:
        _github = GitHubClient()
    return _github


async def get_ci_results(pr_number: int, repo: str, head_sha: str) -> dict[str, Any]:
    """Fetch GitHub Actions / Checks status for the PR's head commit.

    Returns a structured summary so the agent knows whether CI is passing,
    which jobs failed, and can surface that in the review.
    """
    cache = get_cache_client()
    cached, hit = await cache.get("get_ci_results", pr_number=pr_number, repo=repo, head_sha=head_sha)
    if hit:
        return cached

    owner, name = parse_repo(repo)
    try:
        runs = await _get_github().get_check_runs(owner, name, head_sha)
    except Exception:
        result: dict[str, Any] = {
            "available": False,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "pending": 0,
            "checks": [],
            "summary": "CI check data unavailable.",
        }
        await cache.set("get_ci_results", result, pr_number=pr_number, repo=repo, head_sha=head_sha)
        return result

    checks = []
    passed = failed = pending = 0
    for run in runs:
        status = run.get("status", "")      # queued | in_progress | completed
        conclusion = run.get("conclusion")  # success | failure | neutral | cancelled | skipped | timed_out
        checks.append({
            "name": run.get("name", ""),
            "status": status,
            "conclusion": conclusion,
            "url": run.get("html_url", ""),
        })
        if status == "completed":
            if conclusion in ("success", "neutral", "skipped"):
                passed += 1
            else:
                failed += 1
        else:
            pending += 1

    failed_names = [c["name"] for c in checks if c["conclusion"] not in ("success", "neutral", "skipped", None)]
    if failed_names:
        summary = f"{passed}/{len(checks)} checks passing. FAILING: {', '.join(failed_names[:5])}."
    elif pending:
        summary = f"{passed} checks passed, {pending} still running."
    elif checks:
        summary = f"All {passed} checks passed."
    else:
        summary = "No CI checks found for this commit."

    result = {
        "available": True,
        "total": len(checks),
        "passed": passed,
        "failed": failed,
        "pending": pending,
        "checks": checks[:20],  # cap list size in cache
        "summary": summary,
    }
    await cache.set("get_ci_results", result, pr_number=pr_number, repo=repo, head_sha=head_sha)
    return result


async def search_repo_docs(repo: str) -> dict[str, str]:
    """Fetch key documentation files (README, CONTRIBUTING, PR template).

    Gives the agent context about project conventions, style guides, and
    contribution requirements so it can validate the PR against them.
    """
    cache = get_cache_client()
    cached, hit = await cache.get("search_repo_docs", repo=repo)
    if hit:
        return cached

    owner, name = parse_repo(repo)
    docs: dict[str, str] = {}

    for path in _DOC_PATHS:
        try:
            content = await _get_github().get_repo_file(owner, name, path)
            if content:
                docs[path] = content[:_DOC_MAX_CHARS]
                if len(content) > _DOC_MAX_CHARS:
                    docs[path] += f"\n... (truncated, {len(content)} chars total)"
        except Exception:
            continue

    await cache.set("search_repo_docs", docs, repo=repo)
    return docs

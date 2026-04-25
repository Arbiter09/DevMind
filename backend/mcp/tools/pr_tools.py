"""MCP tools for PR-level operations: metadata, diff, posting reviews."""
from __future__ import annotations

from typing import Any

from ...cache import get_cache_client
from ..github_client import GitHubClient, parse_repo

_github = GitHubClient()


async def get_pr_metadata(pr_number: int, repo: str) -> dict[str, Any]:
    """Fetch PR title, author, labels, base branch, head SHA."""
    cache = get_cache_client()
    cached, hit = await cache.get("get_pr_metadata", pr_number=pr_number, repo=repo)
    if hit:
        return cached

    owner, name = parse_repo(repo)
    pr = await _github.get_pr(owner, name, pr_number)

    result = {
        "number": pr["number"],
        "title": pr["title"],
        "author": pr["user"]["login"],
        "base_branch": pr["base"]["ref"],
        "head_sha": pr["head"]["sha"],
        "base_sha": pr["base"]["sha"],
        "labels": [lbl["name"] for lbl in pr.get("labels", [])],
        "body": pr.get("body") or "",
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "changed_files": pr.get("changed_files", 0),
    }

    await cache.set("get_pr_metadata", result, pr_number=pr_number, repo=repo)
    return result


async def get_pr_diff(pr_number: int, repo: str) -> str:
    """Return a unified diff string of all changed files in the PR."""
    cache = get_cache_client()
    cached, hit = await cache.get("get_pr_diff", pr_number=pr_number, repo=repo)
    if hit:
        return cached

    owner, name = parse_repo(repo)
    files = await _github.get_pr_files(owner, name, pr_number)

    diff_parts = []
    for f in files:
        filename = f["filename"]
        status = f["status"]
        patch = f.get("patch", "")
        diff_parts.append(f"--- {filename} ({status})\n{patch}")

    result = "\n\n".join(diff_parts)
    await cache.set("get_pr_diff", result, pr_number=pr_number, repo=repo)
    return result


async def post_review_comment(pr_number: int, repo: str, body: str) -> dict[str, Any]:
    """Post a structured review comment to the PR on GitHub."""
    owner, name = parse_repo(repo)
    response = await _github.create_review(owner, name, pr_number, body)
    return {"review_id": response.get("id"), "state": response.get("state")}

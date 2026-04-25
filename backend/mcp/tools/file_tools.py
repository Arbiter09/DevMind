"""MCP tools for file-level operations: read, list changed, history."""
from __future__ import annotations

from typing import Any

from ...cache import get_cache_client
from ..github_client import GitHubClient, parse_repo

_github = GitHubClient()


async def read_file(path: str, repo: str, ref: str) -> str:
    """Read raw file content at a specific git ref (SHA or branch).

    Content at a commit SHA is immutable — cached for 24h.
    """
    cache = get_cache_client()
    cached, hit = await cache.get("read_file", path=path, repo=repo, ref=ref)
    if hit:
        return cached

    owner, name = parse_repo(repo)
    content = await _github.get_file_content(owner, name, path, ref)
    await cache.set("read_file", content, path=path, repo=repo, ref=ref)
    return content


async def list_changed_files(pr_number: int, repo: str) -> list[dict[str, Any]]:
    """List files changed in a PR with their status and stats."""
    cache = get_cache_client()
    cached, hit = await cache.get("list_changed_files", pr_number=pr_number, repo=repo)
    if hit:
        return cached

    owner, name = parse_repo(repo)
    files = await _github.get_pr_files(owner, name, pr_number)

    result = [
        {
            "filename": f["filename"],
            "status": f["status"],  # added | modified | removed | renamed
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
            "changes": f.get("changes", 0),
        }
        for f in files
    ]

    await cache.set("list_changed_files", result, pr_number=pr_number, repo=repo)
    return result


async def get_file_history(path: str, repo: str, per_page: int = 10) -> list[dict[str, Any]]:
    """Return recent commits touching a file (for context on ownership/patterns)."""
    cache = get_cache_client()
    cached, hit = await cache.get("get_file_history", path=path, repo=repo, per_page=per_page)
    if hit:
        return cached

    owner, name = parse_repo(repo)
    commits = await _github.get_file_commits(owner, name, path, per_page)

    result = [
        {
            "sha": c["sha"][:8],
            "message": c["commit"]["message"].split("\n")[0],
            "author": c["commit"]["author"]["name"],
            "date": c["commit"]["author"]["date"],
        }
        for c in commits
    ]

    await cache.set("get_file_history", result, path=path, repo=repo, per_page=per_page)
    return result

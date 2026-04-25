"""Mock GitHub client for simulation.

Intercepts MCP tool calls and serves data from the synthetic PR dataset
instead of making real GitHub API requests. This enables:
1. Fast, cost-controlled simulation runs (--mock-claude skips LLM entirely)
2. Deterministic replays with --seed
3. Cache-behaviour testing without a live GitHub token
"""
from __future__ import annotations

from typing import Any


class MockGitHubClient:
    """Drop-in replacement for GitHubClient that serves synthetic PR data."""

    def __init__(self, pr_data: dict[str, Any]) -> None:
        self._pr = pr_data

    async def get_pr(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        return {
            "number": self._pr["pr_number"],
            "title": self._pr["title"],
            "user": {"login": self._pr["author"]},
            "base": {"ref": self._pr["base_branch"], "sha": self._pr["base_sha"]},
            "head": {"sha": self._pr["head_sha"]},
            "labels": [{"name": lbl} for lbl in self._pr.get("labels", [])],
            "body": self._pr.get("body", ""),
            "additions": self._pr.get("additions", 0),
            "deletions": self._pr.get("deletions", 0),
            "changed_files": self._pr.get("changed_files", 1),
        }

    async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        return [
            {
                "filename": "src/main.py",
                "status": "modified",
                "additions": self._pr.get("additions", 10),
                "deletions": self._pr.get("deletions", 2),
                "changes": self._pr.get("additions", 10) + self._pr.get("deletions", 2),
                "patch": self._pr.get("diff", ""),
            }
        ]

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        return f"# {path}\n# Mock file content at {ref}\npass\n"

    async def get_file_commits(
        self, owner: str, repo: str, path: str, per_page: int = 10
    ) -> list[dict[str, Any]]:
        return [
            {
                "sha": "abc1234",
                "commit": {
                    "message": "Initial commit",
                    "author": {"name": "dev", "date": "2024-01-01T00:00:00Z"},
                },
            }
        ]

    async def create_review(
        self, owner: str, repo: str, pr_number: int, body: str, event: str = "COMMENT"
    ) -> dict[str, Any]:
        return {"id": 99999, "state": event}

    async def close(self) -> None:
        pass

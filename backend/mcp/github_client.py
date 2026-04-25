"""Thin async wrapper around the GitHub REST API."""
from __future__ import annotations

import os
from typing import Any

import httpx

GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.getenv("GITHUB_TOKEN", "")
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def get_pr(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        r = await self._client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        r.raise_for_status()
        return r.json()

    async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        """Returns list of changed files with patch (diff) content."""
        results = []
        page = 1
        while True:
            r = await self._client.get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            results.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return results

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        """Returns raw file content at a given ref."""
        r = await self._client.get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        r.raise_for_status()
        return r.text

    async def get_file_commits(
        self, owner: str, repo: str, path: str, per_page: int = 10
    ) -> list[dict[str, Any]]:
        r = await self._client.get(
            f"/repos/{owner}/{repo}/commits",
            params={"path": path, "per_page": per_page},
        )
        r.raise_for_status()
        return r.json()

    async def create_review(
        self, owner: str, repo: str, pr_number: int, body: str, event: str = "COMMENT"
    ) -> dict[str, Any]:
        r = await self._client.post(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            json={"body": body, "event": event},
        )
        r.raise_for_status()
        return r.json()

    async def close(self) -> None:
        await self._client.aclose()


def parse_repo(repo: str) -> tuple[str, str]:
    """Split 'owner/repo' into (owner, repo)."""
    parts = repo.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid repo format '{repo}', expected 'owner/repo'")
    return parts[0], parts[1]

"""Thin async wrapper around the GitHub REST API."""
from __future__ import annotations

import os
from typing import Any

import httpx

GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.getenv("GITHUB_TOKEN", "")
        if not self._token:
            raise RuntimeError(
                "GITHUB_TOKEN is not set. Configure it in backend/.env and restart the backend."
            )
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
            follow_redirects=True,
            transport=httpx.AsyncHTTPTransport(retries=3),
        )

    async def get_pr(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        r = await self._client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        r.raise_for_status()
        return r.json()

    async def list_user_repos(self, per_page: int = 100) -> list[dict[str, Any]]:
        """List repositories visible to the authenticated user."""
        repos: list[dict[str, Any]] = []
        page = 1
        while True:
            r = await self._client.get(
                "/user/repos",
                params={"per_page": per_page, "page": page, "sort": "updated"},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return repos

    async def list_pull_requests(
        self, owner: str, repo: str, state: str = "open", per_page: int = 100
    ) -> list[dict[str, Any]]:
        """List pull requests for a repository."""
        pulls: list[dict[str, Any]] = []
        page = 1
        while True:
            r = await self._client.get(
                f"/repos/{owner}/{repo}/pulls",
                params={"state": state, "per_page": per_page, "page": page},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            pulls.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return pulls

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

    async def list_pr_reviews(
        self, owner: str, repo: str, pr_number: int
    ) -> list[dict[str, Any]]:
        """Return all reviews for a PR, ordered oldest-first."""
        r = await self._client.get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            params={"per_page": 100},
        )
        r.raise_for_status()
        return r.json()

    async def list_closed_pulls(
        self, owner: str, repo: str, max_prs: int = 200
    ) -> list[dict[str, Any]]:
        """Return closed PRs, newest-first, up to max_prs."""
        pulls: list[dict[str, Any]] = []
        page = 1
        while len(pulls) < max_prs:
            r = await self._client.get(
                f"/repos/{owner}/{repo}/pulls",
                params={"state": "closed", "per_page": 100, "page": page, "sort": "updated", "direction": "desc"},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            pulls.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return pulls[:max_prs]

    async def create_review(
        self, owner: str, repo: str, pr_number: int, body: str, event: str = "COMMENT"
    ) -> dict[str, Any]:
        r = await self._client.post(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            json={"body": body, "event": event},
        )
        r.raise_for_status()
        return r.json()

    async def get_check_runs(
        self, owner: str, repo: str, ref: str
    ) -> list[dict[str, Any]]:
        """Return all CI check runs for a given commit SHA."""
        r = await self._client.get(
            f"/repos/{owner}/{repo}/commits/{ref}/check-runs",
            params={"per_page": 100},
        )
        r.raise_for_status()
        return r.json().get("check_runs", [])

    async def get_dependency_review(
        self, owner: str, repo: str, base_sha: str, head_sha: str
    ) -> dict[str, Any]:
        """Return dependency changes between two commits including vulnerability data.

        Returns an empty result dict if the feature is not enabled for the repo
        (GitHub Advanced Security required for private repos).
        """
        r = await self._client.get(
            f"/repos/{owner}/{repo}/dependency-graph/compare/{base_sha}...{head_sha}",
        )
        if r.status_code in (404, 403):
            return {"vulnerabilities": [], "available": False}
        r.raise_for_status()
        return r.json()

    async def get_repo_file(
        self, owner: str, repo: str, path: str, ref: str = "HEAD"
    ) -> str:
        """Return raw text content of a repository file, or empty string if not found."""
        r = await self._client.get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        if r.status_code == 404:
            return ""
        r.raise_for_status()
        return r.text

    async def close(self) -> None:
        await self._client.aclose()


def parse_repo(repo: str) -> tuple[str, str]:
    """Split 'owner/repo' into (owner, repo)."""
    parts = repo.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid repo format '{repo}', expected 'owner/repo'")
    return parts[0], parts[1]

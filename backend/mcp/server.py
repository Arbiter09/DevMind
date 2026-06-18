"""MCP server exposing GitHub tools to the agent.

Runs as a stdio-based MCP server using the `mcp` SDK.
The agent orchestrator communicates with it via subprocess stdio transport.

Tools (10 total):
  GitHub context  — get_pr_metadata, get_pr_diff, list_changed_files,
                    read_file, get_file_history, post_review_comment
  CI / checks     — get_ci_results
  Security        — scan_dependency_vulnerabilities, run_static_analysis
  Documentation   — search_repo_docs
"""
from __future__ import annotations

import asyncio

import mcp.server.stdio
from mcp.server import Server
from mcp.types import TextContent, Tool

from .tools import (
    get_ci_results,
    get_file_history,
    get_pr_diff,
    get_pr_metadata,
    list_changed_files,
    post_review_comment,
    read_file,
    run_static_analysis,
    scan_dependency_vulnerabilities,
    search_repo_docs,
)

app = Server("devmind-github")

TOOLS: list[Tool] = [
    # ── GitHub context tools ──────────────────────────────────────────────
    Tool(
        name="get_pr_metadata",
        description="Fetch PR title, author, labels, base branch, head SHA, and change stats.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "Pull request number"},
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
            },
            "required": ["pr_number", "repo"],
        },
    ),
    Tool(
        name="get_pr_diff",
        description="Get the unified diff of all files changed in a pull request.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo": {"type": "string"},
            },
            "required": ["pr_number", "repo"],
        },
    ),
    Tool(
        name="read_file",
        description="Read raw file content at a specific git ref (SHA or branch name).",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path in the repository"},
                "repo": {"type": "string"},
                "ref": {"type": "string", "description": "Git SHA or branch name"},
            },
            "required": ["path", "repo", "ref"],
        },
    ),
    Tool(
        name="list_changed_files",
        description="List all files changed in the PR with their status (added/modified/removed) and line counts.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo": {"type": "string"},
            },
            "required": ["pr_number", "repo"],
        },
    ),
    Tool(
        name="get_file_history",
        description="Get recent commit history for a file to understand ownership and change patterns.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "repo": {"type": "string"},
                "per_page": {"type": "integer", "default": 10},
            },
            "required": ["path", "repo"],
        },
    ),
    Tool(
        name="post_review_comment",
        description="Post a structured review comment to the pull request on GitHub.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo": {"type": "string"},
                "body": {"type": "string", "description": "Markdown-formatted review body"},
            },
            "required": ["pr_number", "repo", "body"],
        },
    ),
    # ── CI / checks tool ─────────────────────────────────────────────────
    Tool(
        name="get_ci_results",
        description=(
            "Fetch GitHub Actions check run results for the PR's head commit. "
            "Returns pass/fail status, check names, and a human-readable summary."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo": {"type": "string"},
                "head_sha": {"type": "string", "description": "Head commit SHA from PR metadata"},
            },
            "required": ["pr_number", "repo", "head_sha"],
        },
    ),
    # ── Security tools ───────────────────────────────────────────────────
    Tool(
        name="scan_dependency_vulnerabilities",
        description=(
            "Use the GitHub Dependency Review API to identify CVEs introduced by this PR. "
            "Returns newly added packages with known vulnerabilities, ranked by severity. "
            "Requires Dependency Graph to be enabled on the repository."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo": {"type": "string"},
                "base_sha": {"type": "string", "description": "Base commit SHA"},
                "head_sha": {"type": "string", "description": "Head commit SHA"},
            },
            "required": ["pr_number", "repo", "base_sha", "head_sha"],
        },
    ),
    Tool(
        name="run_static_analysis",
        description=(
            "Scan the PR diff for common security and quality patterns entirely in-memory: "
            "hardcoded secrets, eval/exec calls, SQL injection risks, unsafe subprocess usage, "
            "pickle deserialisation, TODO/FIXME markers, and debug prints. "
            "Returns structured findings with file, line, severity (critical/warning/info)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "diff": {"type": "string", "description": "Unified diff string from get_pr_diff"},
            },
            "required": ["diff"],
        },
    ),
    # ── Documentation tool ───────────────────────────────────────────────
    Tool(
        name="search_repo_docs",
        description=(
            "Fetch project documentation files (README, CONTRIBUTING, PR template, style guide). "
            "Gives the agent context about coding conventions, contribution requirements, "
            "and project standards to validate the PR against."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
            },
            "required": ["repo"],
        },
    ),
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # run_static_analysis is synchronous — wrap it here
    if name == "run_static_analysis":
        result = run_static_analysis(**arguments)
        return [TextContent(type="text", text=str(result))]

    dispatch = {
        "get_pr_metadata": get_pr_metadata,
        "get_pr_diff": get_pr_diff,
        "read_file": read_file,
        "list_changed_files": list_changed_files,
        "get_file_history": get_file_history,
        "post_review_comment": post_review_comment,
        "get_ci_results": get_ci_results,
        "scan_dependency_vulnerabilities": scan_dependency_vulnerabilities,
        "search_repo_docs": search_repo_docs,
    }

    handler = dispatch.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")

    result = await handler(**arguments)
    return [TextContent(type="text", text=str(result))]


def create_mcp_server() -> Server:
    return app


async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

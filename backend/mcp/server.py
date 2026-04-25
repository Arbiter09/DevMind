"""MCP server exposing GitHub tools to the agent.

Runs as a stdio-based MCP server using the `mcp` SDK.
The agent orchestrator communicates with it via subprocess stdio transport.
"""
from __future__ import annotations

import asyncio

import mcp.server.stdio
from mcp.server import Server
from mcp.types import TextContent, Tool

from .tools import (
    get_file_history,
    get_pr_diff,
    get_pr_metadata,
    list_changed_files,
    post_review_comment,
    read_file,
)

app = Server("devmind-github")

TOOLS: list[Tool] = [
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
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    dispatch = {
        "get_pr_metadata": get_pr_metadata,
        "get_pr_diff": get_pr_diff,
        "read_file": read_file,
        "list_changed_files": list_changed_files,
        "get_file_history": get_file_history,
        "post_review_comment": post_review_comment,
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

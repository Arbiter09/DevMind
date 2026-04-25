"""Phase 1: Context Gathering.

Fetches PR metadata, diff, and relevant file content via MCP tools.
All calls go through the Redis cache-aside layer automatically.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from ...mcp.tools import get_pr_diff, get_pr_metadata, list_changed_files, read_file
from ...models import PhaseTrace
from ...telemetry.spans import agent_span, record_cache_result
from ..compressor import extract_changed_context

logger = structlog.get_logger(__name__)

# Only pull full file context for files below this size threshold (lines)
MAX_FILE_LINES_FOR_CONTEXT = 500


async def run_context_gathering(
    pr_number: int,
    repo: str,
    cache_stats: dict[str, int],
) -> tuple[dict[str, Any], str, dict[str, str], PhaseTrace]:
    """Returns (pr_metadata, diff, file_contexts, phase_trace)."""
    started = datetime.utcnow()
    phase_hits = 0
    phase_misses = 0

    with agent_span("devmind.context_gathering", {"pr.number": pr_number, "pr.repo": repo}) as span:
        # 1. Fetch PR metadata
        metadata = await get_pr_metadata(pr_number=pr_number, repo=repo)
        head_sha = metadata["head_sha"]

        # 2. Fetch full diff
        diff = await get_pr_diff(pr_number=pr_number, repo=repo)

        # 3. List changed files to decide which to read for context
        changed_files = await list_changed_files(pr_number=pr_number, repo=repo)

        # 4. Read file contents for context (skip deleted files, skip large files)
        file_contexts: dict[str, str] = {}
        for file_info in changed_files:
            path = file_info["filename"]
            status = file_info["status"]

            if status == "removed":
                continue

            try:
                raw_content = await read_file(path=path, repo=repo, ref=head_sha)
                line_count = raw_content.count("\n")
                if line_count > MAX_FILE_LINES_FOR_CONTEXT:
                    # Find the patch for this file from the diff to extract context
                    patch = _extract_patch_for_file(diff, path)
                    compressed = extract_changed_context(raw_content, patch)
                    file_contexts[path] = compressed
                else:
                    file_contexts[path] = raw_content
            except Exception as exc:
                logger.warning("context_gathering.file_read_failed", path=path, error=str(exc))

        span.set_attribute("files.changed", len(changed_files))
        span.set_attribute("files.context_loaded", len(file_contexts))

    trace = PhaseTrace(
        phase="context_gathering",
        started_at=started,
        ended_at=datetime.utcnow(),
        cache_hits=cache_stats.get("hits", 0),
        cache_misses=cache_stats.get("misses", 0),
    )

    return metadata, diff, file_contexts, trace


def _extract_patch_for_file(full_diff: str, filename: str) -> str:
    """Extract the patch section for a specific file from the combined diff."""
    lines = full_diff.splitlines()
    in_file = False
    patch_lines: list[str] = []

    for line in lines:
        if line.startswith(f"--- {filename}"):
            in_file = True
        elif in_file and line.startswith("--- ") and filename not in line:
            break
        if in_file:
            patch_lines.append(line)

    return "\n".join(patch_lines)

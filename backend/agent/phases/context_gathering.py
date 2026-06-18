"""Phase 1: Context Gathering.

Fetches PR metadata, diff, file contents, CI status, dependency vulnerabilities,
static analysis findings, and repository docs via MCP tools.
All calls go through the Redis cache-aside layer automatically.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog

from ...mcp.tools import (
    get_ci_results,
    get_pr_diff,
    get_pr_metadata,
    list_changed_files,
    read_file,
    run_static_analysis,
    scan_dependency_vulnerabilities,
    search_repo_docs,
)
from ...models import PhaseTrace
from ...telemetry.spans import agent_span
from ..compressor import extract_changed_context

logger = structlog.get_logger(__name__)

# Only pull full file context for files below this size threshold (lines)
MAX_FILE_LINES_FOR_CONTEXT = 500


async def run_context_gathering(
    pr_number: int,
    repo: str,
    cache_stats: dict[str, int],
) -> tuple[dict[str, Any], str, dict[str, str], dict[str, Any], PhaseTrace]:
    """Gather all context needed for the analysis phase.

    Returns:
        (pr_metadata, diff, file_contexts, enriched_context, phase_trace)

    enriched_context contains:
        ci_results       — GitHub Actions check run status
        vuln_report      — dependency vulnerability scan (GitHub Dependency Review API)
        static_analysis  — in-memory pattern scan of diff
        repo_docs        — README / CONTRIBUTING / style guides
    """
    started = datetime.utcnow()

    with agent_span("devmind.context_gathering", {"pr.number": pr_number, "pr.repo": repo}) as span:
        # 1. Fetch PR metadata (needed first — head_sha drives all downstream calls)
        metadata = await get_pr_metadata(pr_number=pr_number, repo=repo)
        head_sha = metadata["head_sha"]
        base_sha = metadata["base_sha"]

        # 2. Fetch diff + changed-files list in parallel (both independent of each other)
        diff, changed_files = await asyncio.gather(
            get_pr_diff(pr_number=pr_number, repo=repo),
            list_changed_files(pr_number=pr_number, repo=repo),
        )

        # 3. Enrichment tools — run in parallel with file context reads
        async def _gather_enrichments() -> tuple[dict, dict, dict]:
            ci, vulns, docs = await asyncio.gather(
                get_ci_results(pr_number=pr_number, repo=repo, head_sha=head_sha),
                scan_dependency_vulnerabilities(
                    pr_number=pr_number, repo=repo,
                    base_sha=base_sha, head_sha=head_sha,
                ),
                search_repo_docs(repo=repo),
            )
            return ci, vulns, docs

        async def _gather_file_contexts() -> dict[str, str]:
            contexts: dict[str, str] = {}
            for file_info in changed_files:
                path = file_info["filename"]
                if file_info["status"] == "removed":
                    continue
                try:
                    raw_content = await read_file(path=path, repo=repo, ref=head_sha)
                    line_count = raw_content.count("\n")
                    if line_count > MAX_FILE_LINES_FOR_CONTEXT:
                        patch = _extract_patch_for_file(diff, path)
                        contexts[path] = extract_changed_context(raw_content, patch)
                    else:
                        contexts[path] = raw_content
                except Exception as exc:
                    logger.warning("context_gathering.file_read_failed", path=path, error=str(exc))
            return contexts

        # Run enrichments and file reads in parallel
        (ci_results, vuln_report, repo_docs), file_contexts = await asyncio.gather(
            _gather_enrichments(),
            _gather_file_contexts(),
        )

        # 4. Static analysis is synchronous / in-memory — no I/O, run after diff is ready
        static_analysis = run_static_analysis(diff=diff)

        enriched_context: dict[str, Any] = {
            "ci_results": ci_results,
            "vuln_report": vuln_report,
            "static_analysis": static_analysis,
            "repo_docs": repo_docs,
        }

        span.set_attribute("files.changed", len(changed_files))
        span.set_attribute("files.context_loaded", len(file_contexts))
        span.set_attribute("ci.summary", ci_results.get("summary", ""))
        span.set_attribute("static.critical_count", static_analysis.get("critical_count", 0))
        span.set_attribute("vulns.count", len(vuln_report.get("vulnerabilities", [])))

        log = logger.bind(job=pr_number, repo=repo)
        log.info(
            "context_gathering.enrichment_complete",
            ci_summary=ci_results.get("summary"),
            static_critical=static_analysis.get("critical_count", 0),
            vuln_count=len(vuln_report.get("vulnerabilities", [])),
            docs_fetched=list(repo_docs.keys()),
        )

    trace = PhaseTrace(
        phase="context_gathering",
        started_at=started,
        ended_at=datetime.utcnow(),
        cache_hits=cache_stats.get("hits", 0),
        cache_misses=cache_stats.get("misses", 0),
    )

    return metadata, diff, file_contexts, enriched_context, trace


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

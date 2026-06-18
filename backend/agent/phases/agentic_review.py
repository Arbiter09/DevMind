"""Agentic Phase 1+2: Claude drives tool selection.

Replaces the hardcoded context_gathering + analysis pipeline.

Claude sees all 10 available tools, decides which ones to call and in what
order based on the PR it encounters, and writes the review when it has
gathered enough context. A MAX_TOOL_TURNS safety cap prevents runaway loops.

Why this is better than a hardcoded pipeline:
  - A doc-only PR skips vulnerability scanning and CI deep-dives automatically.
  - A PR touching auth code will call get_file_history and read extra files.
  - A PR with failing CI gets that surfaced at the top without explicit rules.
  - New tools added to the registry are usable without changing orchestration logic.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import anthropic
import structlog

from ...mcp.tools import (
    get_ci_results,
    get_file_history,
    get_pr_diff,
    get_pr_metadata,
    list_changed_files,
    read_file,
    run_static_analysis,
    scan_dependency_vulnerabilities,
    search_repo_docs,
)
from ...models import PhaseTrace
from ...telemetry.spans import agent_span, record_llm_usage

logger = structlog.get_logger(__name__)

# Hard cap on tool-call turns to prevent infinite loops.
# A thorough review typically uses 6–10 tool calls.
MAX_TOOL_TURNS = 15

# --------------------------------------------------------------------- #
# System prompt — tells Claude HOW to use the tools, not just what they are.
# --------------------------------------------------------------------- #
AGENT_SYSTEM_PROMPT = """\
You are an expert code reviewer with access to a GitHub repository's code, \
CI infrastructure, and dependency graph.

Your job: review a pull request thoroughly by calling tools to gather the \
context you need, then write a structured, actionable code review.

## Tool Usage Strategy

Always start with `get_pr_metadata` — you need the `head_sha` it returns \
to call most other tools.

Then follow the context you find:
- Run `get_pr_diff` and `list_changed_files` to understand the scope.
- Run `get_ci_results` early — failing CI must be addressed before merging.
- Run `run_static_analysis` to catch common security issues in the diff.
- If the PR touches dependency files (requirements.txt, package.json, go.mod, \
  Cargo.toml, etc.), run `scan_dependency_vulnerabilities`.
- Use `read_file` for files where the diff alone isn't enough context \
  (e.g. the function being changed is large, or tests need to be read).
- Use `search_repo_docs` once to understand project conventions \
  (style guide, contribution requirements, PR template).
- Use `get_file_history` for files that look suspicious, recently churned, \
  or central to the change's correctness.

## When to Stop Calling Tools

Stop when you can write a complete, specific review. Do not call tools \
redundantly or fetch context you won't use.

## Review Format

Write the review under these headings:
- **Critical** — bugs, security vulnerabilities, data loss risks, broken contracts
- **Suggestions** — design improvements, performance concerns, missing tests
- **Nitpicks** — style, naming, minor readability issues

Rules:
- Reference specific file paths and line numbers for every finding.
- If CI is failing, put a prominent warning at the very top before the headings.
- If vulnerability CVEs were found, list each one with severity and package name.
- If a section has nothing to report, write "Nothing to flag." — do not omit it.
- End with a one-paragraph overall assessment and one of: \
  APPROVE / REQUEST_CHANGES / COMMENT.
"""

# --------------------------------------------------------------------- #
# Tool schemas in Anthropic format.
# run_static_analysis takes (pr_number, repo) here — it fetches the diff
# internally, so Claude doesn't have to shuttle a 10k-char string back.
# The external MCP server still exposes the (diff) variant for other clients.
# --------------------------------------------------------------------- #
ANTHROPIC_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_pr_metadata",
        "description": (
            "Fetch PR title, author, labels, base branch, head SHA, and change stats. "
            "Call this first — head_sha is required by most other tools."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo": {"type": "string", "description": "owner/repo format"},
            },
            "required": ["pr_number", "repo"],
        },
    },
    {
        "name": "get_pr_diff",
        "description": "Get the unified diff of all files changed in the PR.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo": {"type": "string"},
            },
            "required": ["pr_number", "repo"],
        },
    },
    {
        "name": "list_changed_files",
        "description": (
            "List files changed in the PR with status (added/modified/removed) "
            "and per-file line counts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo": {"type": "string"},
            },
            "required": ["pr_number", "repo"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read raw file content at a specific git ref. Use this when the diff "
            "alone doesn't give enough context — e.g. to see the full function "
            "a change is embedded in, or to read test files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "repo": {"type": "string"},
                "ref": {"type": "string", "description": "Commit SHA from get_pr_metadata"},
            },
            "required": ["path", "repo", "ref"],
        },
    },
    {
        "name": "get_file_history",
        "description": (
            "Get recent commit history for a specific file. Useful for spotting "
            "churn patterns, understanding ownership, or checking whether the "
            "file has a history of bugs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "repo": {"type": "string"},
                "per_page": {"type": "integer", "default": 10},
            },
            "required": ["path", "repo"],
        },
    },
    {
        "name": "get_ci_results",
        "description": (
            "Fetch GitHub Actions check run results for the PR's head commit. "
            "Returns which checks passed, which failed, and a plain-English summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo": {"type": "string"},
                "head_sha": {"type": "string", "description": "From get_pr_metadata"},
            },
            "required": ["pr_number", "repo", "head_sha"],
        },
    },
    {
        "name": "scan_dependency_vulnerabilities",
        "description": (
            "Use the GitHub Dependency Review API to find CVEs introduced by this PR. "
            "Call this if the PR changes any dependency manifest file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo": {"type": "string"},
                "base_sha": {"type": "string", "description": "From get_pr_metadata"},
                "head_sha": {"type": "string", "description": "From get_pr_metadata"},
            },
            "required": ["pr_number", "repo", "base_sha", "head_sha"],
        },
    },
    {
        "name": "run_static_analysis",
        "description": (
            "Scan the PR diff for common security and quality patterns: "
            "hardcoded secrets, eval/exec, SQL injection risks, unsafe subprocess, "
            "pickle deserialisation, TODO/FIXME markers, and debug prints. "
            "Returns structured findings with severity (critical/warning/info) and line numbers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo": {"type": "string"},
            },
            "required": ["pr_number", "repo"],
        },
    },
    {
        "name": "search_repo_docs",
        "description": (
            "Fetch project documentation (README, CONTRIBUTING, PR template, style guide). "
            "Call once per review to understand project conventions and validate the PR against them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
            },
            "required": ["repo"],
        },
    },
]


# --------------------------------------------------------------------- #
# Tool dispatcher — maps Claude's tool_use blocks to our MCP functions.
# --------------------------------------------------------------------- #
async def _dispatch_tool(name: str, inputs: dict[str, Any]) -> Any:
    """Execute one tool call. Returns a JSON-serialisable result.

    run_static_analysis is special: Claude passes (pr_number, repo) and we
    fetch the diff ourselves so Claude doesn't have to shuttle a large string.
    """
    if name == "get_pr_metadata":
        return await get_pr_metadata(**inputs)
    if name == "get_pr_diff":
        return await get_pr_diff(**inputs)
    if name == "list_changed_files":
        return await list_changed_files(**inputs)
    if name == "read_file":
        return await read_file(**inputs)
    if name == "get_file_history":
        return await get_file_history(**inputs)
    if name == "get_ci_results":
        return await get_ci_results(**inputs)
    if name == "scan_dependency_vulnerabilities":
        return await scan_dependency_vulnerabilities(**inputs)
    if name == "run_static_analysis":
        diff = await get_pr_diff(pr_number=inputs["pr_number"], repo=inputs["repo"])
        return run_static_analysis(diff=diff)
    if name == "search_repo_docs":
        return await search_repo_docs(**inputs)
    raise ValueError(f"Unknown tool: {name}")


# --------------------------------------------------------------------- #
# Anthropic client helpers (same model fallback pattern as analysis.py)
# --------------------------------------------------------------------- #
_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _model_candidates() -> list[str]:
    configured = os.getenv("ANTHROPIC_MODEL", "").strip()
    fallback = os.getenv(
        "ANTHROPIC_MODEL_FALLBACKS",
        "claude-3-5-sonnet-latest,claude-3-5-haiku-latest,claude-3-haiku-20240307",
    )
    raw = ([configured] if configured else []) + [m.strip() for m in fallback.split(",")]
    models: list[str] = []
    for m in raw:
        if m and m not in models:
            models.append(m)
    return models


# --------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------- #
async def run_agentic_review(
    pr_number: int,
    repo: str,
) -> tuple[str, list[dict[str, Any]], PhaseTrace]:
    """Claude-driven Phase 1+2: tool gathering + initial review draft.

    Returns:
        review_draft   — the initial review text Claude produced
        tool_calls_log — list of {name, inputs, result_summary} for observability
        phase_trace    — timing + token usage
    """
    started = datetime.utcnow()
    tokens_in = 0
    tokens_out = 0
    tool_calls_log: list[dict[str, Any]] = []

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                f"Please review pull request #{pr_number} in the repository `{repo}`. "
                f"Use the available tools to gather the context you need, then write "
                f"a thorough, actionable code review."
            ),
        }
    ]

    review_draft = ""
    model_used = "unknown"

    with agent_span(
        "devmind.agentic_review",
        {"pr.number": pr_number, "pr.repo": repo},
    ) as span:
        client = _get_client()
        candidates = _model_candidates()
        model = candidates[0] if candidates else "claude-3-5-sonnet-latest"

        for turn in range(MAX_TOOL_TURNS):
            last_exc: Exception | None = None
            response = None

            for candidate in candidates:
                try:
                    response = await client.messages.create(
                        model=candidate,
                        max_tokens=4096,
                        system=AGENT_SYSTEM_PROMPT,
                        tools=ANTHROPIC_TOOLS,
                        messages=messages,
                    )
                    model_used = candidate
                    break
                except Exception as exc:
                    last_exc = exc
                    msg = str(exc).lower()
                    if "not_found_error" in msg and "model" in msg:
                        logger.warning("agentic_review.model_unavailable", model=candidate)
                        continue
                    raise

            if response is None:
                raise last_exc or RuntimeError("No model available")

            tokens_in += response.usage.input_tokens
            tokens_out += response.usage.output_tokens

            # Append assistant turn to conversation
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Claude is done — extract final text
                for block in response.content:
                    if hasattr(block, "text"):
                        review_draft += block.text
                logger.info(
                    "agentic_review.complete",
                    turns=turn + 1,
                    tool_calls=len(tool_calls_log),
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    model=model_used,
                )
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    logger.info(
                        "agentic_review.tool_call",
                        turn=turn + 1,
                        tool=block.name,
                        inputs=block.input,
                    )
                    try:
                        result = await _dispatch_tool(block.name, block.input)
                        result_str = json.dumps(result, default=str)
                        error = None
                    except Exception as exc:
                        result_str = json.dumps({"error": str(exc), "tool": block.name})
                        error = str(exc)
                        logger.warning("agentic_review.tool_error", tool=block.name, error=error)

                    tool_calls_log.append({
                        "turn": turn + 1,
                        "name": block.name,
                        "inputs": block.input,
                        "result_length": len(result_str),
                        "error": error,
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

                messages.append({"role": "user", "content": tool_results})

        else:
            # Exceeded MAX_TOOL_TURNS — extract whatever text Claude produced last
            logger.warning("agentic_review.max_turns_exceeded", pr=pr_number, repo=repo)
            for block in (messages[-2].get("content", []) if len(messages) >= 2 else []):
                if hasattr(block, "text"):
                    review_draft += block.text
            if not review_draft:
                review_draft = (
                    "⚠️ Review could not be completed — agent exceeded the maximum number "
                    "of tool-call turns. Please trigger a manual review."
                )

        span.set_attribute("tool_calls.count", len(tool_calls_log))
        span.set_attribute("tokens.input", tokens_in)
        span.set_attribute("tokens.output", tokens_out)
        record_llm_usage(span, tokens_in, tokens_out)

    trace = PhaseTrace(
        phase="agentic_review",
        started_at=started,
        ended_at=datetime.utcnow(),
        tokens_input=tokens_in,
        tokens_output=tokens_out,
    )

    return review_draft, tool_calls_log, trace

"""Prompt compression utilities.

Two mechanisms:
1. Context extraction — given a diff and a full file, extract only the
   function/class containing the changed lines (not the entire file).
2. Deduplication — if the same file appears multiple times in the context
   window (e.g. imported by several changed files), include it only once.
"""
from __future__ import annotations

import re


def extract_changed_context(file_content: str, patch: str, context_lines: int = 10) -> str:
    """Extract the minimal relevant slice of a file based on its diff patch.

    Finds the line numbers mentioned in the patch hunk headers (@@ -L,N +L,N @@)
    and returns a window of `context_lines` lines around each hunk, rather than
    the full file. Falls back to the full content if parsing fails.
    """
    if not patch or not file_content:
        return file_content

    lines = file_content.splitlines()
    hunk_pattern = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    relevant_ranges: list[tuple[int, int]] = []
    for match in hunk_pattern.finditer(patch):
        start = int(match.group(1)) - 1  # convert to 0-indexed
        length = int(match.group(2)) if match.group(2) else 1
        lo = max(0, start - context_lines)
        hi = min(len(lines), start + length + context_lines)
        relevant_ranges.append((lo, hi))

    if not relevant_ranges:
        return file_content

    # Merge overlapping ranges
    merged: list[tuple[int, int]] = []
    for lo, hi in sorted(relevant_ranges):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))

    # Build compressed content with line-number annotations
    parts = []
    for lo, hi in merged:
        chunk = lines[lo:hi]
        annotated = "\n".join(f"{lo + i + 1:4d} | {line}" for i, line in enumerate(chunk))
        parts.append(annotated)

    return "\n...\n".join(parts)


def deduplicate_file_contexts(contexts: dict[str, str]) -> dict[str, str]:
    """Remove exact-duplicate file contents, keeping the first occurrence."""
    seen: set[str] = set()
    deduped: dict[str, str] = {}
    for path, content in contexts.items():
        sig = content.strip()
        if sig not in seen:
            seen.add(sig)
            deduped[path] = content
    return deduped


def build_analysis_prompt(
    pr_metadata: dict,
    diff: str,
    file_contexts: dict[str, str],
) -> str:
    """Assemble the compressed prompt sent to Claude for initial review generation."""
    meta_block = (
        f"PR #{pr_metadata['number']}: {pr_metadata['title']}\n"
        f"Author: {pr_metadata['author']} | Base: {pr_metadata['base_branch']}\n"
        f"Changes: +{pr_metadata['additions']} -{pr_metadata['deletions']} "
        f"across {pr_metadata['changed_files']} file(s)\n"
    )
    if pr_metadata.get("body"):
        meta_block += f"\nDescription:\n{pr_metadata['body'][:500]}\n"

    contexts_block = ""
    deduped = deduplicate_file_contexts(file_contexts)
    if deduped:
        parts = [f"### {path}\n```\n{content}\n```" for path, content in deduped.items()]
        contexts_block = "\n\n".join(parts)

    return f"""\
You are an expert code reviewer. Perform a thorough review of the following pull request.

## PR Overview
{meta_block}

## Diff
```diff
{diff[:10000]}
```

{"## Relevant File Context" + chr(10) + contexts_block if contexts_block else ""}

## Instructions
- Identify bugs, security issues, performance problems, and design concerns.
- Be specific: reference line numbers and file names.
- Organise feedback under clear headings (e.g. **Critical**, **Suggestions**, **Nitpicks**).
- If a section has no issues, say so briefly (e.g. "No security concerns found.").
- End with a one-paragraph overall assessment and a recommended action: APPROVE / REQUEST_CHANGES / COMMENT.
"""

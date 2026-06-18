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


def _build_ci_block(ci: dict) -> str:
    """Render CI results into a prompt section."""
    if not ci or not ci.get("available"):
        return ""
    lines = [f"**Summary**: {ci['summary']}"]
    failed = [c for c in ci.get("checks", []) if c.get("conclusion") not in ("success", "neutral", "skipped", None)]
    if failed:
        lines.append("\nFailing checks:")
        for c in failed[:6]:
            lines.append(f"  - {c['name']}: {c['conclusion']}")
    return "\n".join(lines)


def _build_vuln_block(vuln: dict) -> str:
    """Render dependency vulnerability report into a prompt section."""
    if not vuln or not vuln.get("available"):
        return ""
    lines = [f"**Summary**: {vuln['summary']}"]
    if vuln.get("added_packages"):
        lines.append(f"Added packages: {', '.join(vuln['added_packages'][:10])}")
    if vuln.get("vulnerabilities"):
        lines.append("\nVulnerable packages:")
        for v in vuln["vulnerabilities"][:8]:
            advisory = f" ({v['advisory']})" if v.get("advisory") else ""
            lines.append(f"  - {v['package']}@{v.get('version', '?')} — {v['severity'].upper()}{advisory}")
    return "\n".join(lines)


def _build_static_block(sa: dict) -> str:
    """Render static analysis findings into a prompt section."""
    if not sa or not sa.get("findings"):
        return ""
    lines = [f"**Summary**: {sa['summary']}", ""]
    for f in sa["findings"][:20]:
        lines.append(f"  [{f['severity'].upper()}] {f['file']}:{f['line']} — {f['type']}: `{f['snippet'][:80]}`")
    return "\n".join(lines)


def _build_docs_block(docs: dict) -> str:
    """Render repository docs into a prompt section (only the most useful ones)."""
    if not docs:
        return ""
    parts = []
    # Prefer CONTRIBUTING over README for style/contribution standards
    priority = ["CONTRIBUTING.md", ".github/PULL_REQUEST_TEMPLATE.md", "README.md"]
    for key in priority + [k for k in docs if k not in priority]:
        content = docs.get(key, "")
        if content:
            parts.append(f"### {key}\n{content[:1500]}")
        if len(parts) >= 2:  # cap at 2 doc sections to manage prompt size
            break
    return "\n\n".join(parts)


def build_analysis_prompt(
    pr_metadata: dict,
    diff: str,
    file_contexts: dict[str, str],
    enriched_context: dict | None = None,
) -> str:
    """Assemble the compressed prompt sent to Claude for initial review generation.

    Incorporates CI status, dependency vulnerabilities, static analysis findings,
    and repository documentation alongside the standard diff + file context.
    """
    ec = enriched_context or {}

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

    ci_block = _build_ci_block(ec.get("ci_results", {}))
    vuln_block = _build_vuln_block(ec.get("vuln_report", {}))
    static_block = _build_static_block(ec.get("static_analysis", {}))
    docs_block = _build_docs_block(ec.get("repo_docs", {}))

    optional_sections = []
    if ci_block:
        optional_sections.append(f"## CI Status\n{ci_block}")
    if vuln_block:
        optional_sections.append(f"## Dependency Vulnerabilities\n{vuln_block}")
    if static_block:
        optional_sections.append(f"## Static Analysis Pre-scan\n{static_block}")
    if docs_block:
        optional_sections.append(f"## Repository Standards\n{docs_block}")

    enrichment = ("\n\n" + "\n\n".join(optional_sections)) if optional_sections else ""

    return f"""\
You are an expert code reviewer. Perform a thorough review of the following pull request.

## PR Overview
{meta_block}

## Diff
```diff
{diff[:10000]}
```

{"## Relevant File Context" + chr(10) + contexts_block if contexts_block else ""}{enrichment}

## Instructions
- Identify bugs, security issues, performance problems, and design concerns.
- Be specific: reference line numbers and file names.
- If CI is failing, call it out prominently — failing tests must be addressed before merging.
- If dependency vulnerabilities were found, flag each CVE explicitly with severity and package name.
- If the static analysis pre-scan flagged issues, verify them in the diff and include them in your review.
- If repository standards/docs are provided, check the PR against them and note any deviations.
- Organise feedback under clear headings (e.g. **Critical**, **Suggestions**, **Nitpicks**).
- If a section has no issues, say so briefly (e.g. "No security concerns found.").
- End with a one-paragraph overall assessment and a recommended action: APPROVE / REQUEST_CHANGES / COMMENT.
"""

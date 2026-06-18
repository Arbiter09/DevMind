"""MCP tools for security scanning: dependency vulnerabilities and static analysis."""
from __future__ import annotations

import re
from typing import Any

from ...cache import get_cache_client
from ..github_client import GitHubClient, parse_repo

_github: GitHubClient | None = None


def _get_github() -> GitHubClient:
    global _github
    if _github is None:
        _github = GitHubClient()
    return _github


# ---------------------------------------------------------------------------
# Static analysis patterns applied to diff added-lines (+).
# Each entry: (finding_type, severity, compiled_regex)
# ---------------------------------------------------------------------------
_STATIC_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    (
        "hardcoded_secret",
        "critical",
        re.compile(
            r'(?i)(?:password|passwd|secret|api_key|apikey|token|auth_token|access_key)\s*=\s*["\'][^"\']{6,}["\']'
        ),
    ),
    (
        "eval_exec",
        "critical",
        re.compile(r'\b(?:eval|exec)\s*\('),
    ),
    (
        "sql_injection_risk",
        "critical",
        re.compile(r'\.execute\s*\(\s*(?:f["\']|["\'][^"\']*\{|["\'][^"\']*%s)'),
    ),
    (
        "unsafe_subprocess",
        "warning",
        re.compile(r'\b(?:os\.system|subprocess\.call|subprocess\.Popen)\s*\('),
    ),
    (
        "pickle_deserialise",
        "critical",
        re.compile(r'\bpickle\.loads?\s*\('),
    ),
    (
        "yaml_unsafe_load",
        "warning",
        re.compile(r'\byaml\.load\s*\([^)]*\)(?!\s*#.*safe)'),
    ),
    (
        "debug_print",
        "info",
        re.compile(r'^\+\s*print\s*\('),
    ),
    (
        "todo_fixme",
        "info",
        re.compile(r'#\s*(?:TODO|FIXME|HACK|XXX)\b', re.IGNORECASE),
    ),
    (
        "hardcoded_ip",
        "info",
        re.compile(r'\b(?:10|172|192)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'),
    ),
    (
        "assert_in_production",
        "warning",
        re.compile(r'^\+\s*assert\s+(?!False\b)'),
    ),
]

# Max findings to report (keeps prompt size bounded)
_MAX_FINDINGS = 30


def run_static_analysis(diff: str) -> dict[str, Any]:
    """Scan diff added-lines for common security and quality patterns.

    Runs entirely in-memory — no external API calls. Returns structured
    findings with file, approximate line number, pattern type, and severity.
    """
    findings: list[dict[str, Any]] = []
    current_file = "unknown"
    current_new_line = 0

    for raw_line in diff.splitlines():
        # Track which file we're in
        if raw_line.startswith("--- "):
            # "--- path/to/file (status)"
            parts = raw_line[4:].split(" ", 1)
            current_file = parts[0].strip()
            current_new_line = 0
            continue

        # Track hunk headers to maintain line numbers
        hunk_match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
        if hunk_match:
            current_new_line = int(hunk_match.group(1)) - 1
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            current_new_line += 1
            code = raw_line[1:]  # strip leading '+'
            for finding_type, severity, pattern in _STATIC_PATTERNS:
                if pattern.search(raw_line if finding_type == "debug_print" else code):
                    findings.append({
                        "type": finding_type,
                        "severity": severity,
                        "file": current_file,
                        "line": current_new_line,
                        "snippet": code.strip()[:120],
                    })
                    if len(findings) >= _MAX_FINDINGS:
                        break
        elif not raw_line.startswith("-"):
            current_new_line += 1

        if len(findings) >= _MAX_FINDINGS:
            break

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: severity_order.get(f["severity"], 9))

    critical = sum(1 for f in findings if f["severity"] == "critical")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    info = sum(1 for f in findings if f["severity"] == "info")

    parts = []
    if critical:
        parts.append(f"{critical} critical")
    if warnings:
        parts.append(f"{warnings} warning{'s' if warnings > 1 else ''}")
    if info:
        parts.append(f"{info} info")
    summary = f"Static analysis: {', '.join(parts)}." if parts else "No static analysis findings."

    return {
        "findings": findings,
        "critical_count": critical,
        "warning_count": warnings,
        "info_count": info,
        "summary": summary,
    }


async def scan_dependency_vulnerabilities(
    pr_number: int, repo: str, base_sha: str, head_sha: str
) -> dict[str, Any]:
    """Fetch dependency changes for the PR and flag any newly introduced CVEs.

    Uses the GitHub Dependency Review API (requires Dependency Graph to be
    enabled on the repo). Returns a graceful empty result if unavailable.
    """
    cache = get_cache_client()
    cached, hit = await cache.get(
        "scan_dependency_vulnerabilities",
        pr_number=pr_number,
        repo=repo,
        head_sha=head_sha,
    )
    if hit:
        return cached

    owner, name = parse_repo(repo)
    try:
        raw = await _get_github().get_dependency_review(owner, name, base_sha, head_sha)
    except Exception:
        result: dict[str, Any] = {
            "available": False,
            "vulnerabilities": [],
            "added_packages": [],
            "removed_packages": [],
            "summary": "Dependency review unavailable.",
        }
        await cache.set(
            "scan_dependency_vulnerabilities", result,
            pr_number=pr_number, repo=repo, head_sha=head_sha,
        )
        return result

    if not raw.get("available", True):
        result = {
            "available": False,
            "vulnerabilities": [],
            "added_packages": [],
            "removed_packages": [],
            "summary": "Dependency review not enabled for this repository.",
        }
        await cache.set(
            "scan_dependency_vulnerabilities", result,
            pr_number=pr_number, repo=repo, head_sha=head_sha,
        )
        return result

    vulns: list[dict[str, Any]] = []
    added_packages: list[str] = []
    removed_packages: list[str] = []

    for change in raw:
        if not isinstance(change, dict):
            continue
        change_type = change.get("change_type", "")
        pkg = change.get("package", {})
        pkg_name = pkg.get("name", "unknown")
        ecosystem = pkg.get("ecosystem", "")
        version = change.get("version", "")
        label = f"{pkg_name}@{version}" if version else pkg_name

        if change_type == "added":
            added_packages.append(label)
        elif change_type == "removed":
            removed_packages.append(label)

        for vuln in change.get("vulnerabilities", []):
            severity = vuln.get("severity", "unknown")
            advisory = vuln.get("advisory_ghsa_id", vuln.get("advisory_summary", ""))
            vulns.append({
                "package": pkg_name,
                "ecosystem": ecosystem,
                "version": version,
                "severity": severity,
                "change_type": change_type,
                "advisory": advisory,
            })

    vulns.sort(key=lambda v: {"critical": 0, "high": 1, "moderate": 2, "low": 3}.get(v["severity"], 4))

    critical_high = [v for v in vulns if v["severity"] in ("critical", "high")]
    if critical_high:
        names = ", ".join(f"{v['package']} ({v['severity']})" for v in critical_high[:4])
        summary = f"⚠️ {len(vulns)} vulnerable package(s) introduced. Critical/high: {names}."
    elif vulns:
        summary = f"{len(vulns)} low/moderate vulnerability/vulnerabilities in new dependencies."
    else:
        summary = f"{len(added_packages)} package(s) added, no known vulnerabilities."

    result = {
        "available": True,
        "vulnerabilities": vulns[:20],
        "added_packages": added_packages[:20],
        "removed_packages": removed_packages[:10],
        "summary": summary,
    }
    await cache.set(
        "scan_dependency_vulnerabilities", result,
        pr_number=pr_number, repo=repo, head_sha=head_sha,
    )
    return result

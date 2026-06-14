#!/usr/bin/env python3
"""Build the committed annotated PR dataset from templates.

Produces simulation/data/annotated_prs.jsonl — one JSON record per template,
with full 12-dimension ground-truth annotations. This file is committed to the
repo (not gitignored) and serves as the static eval benchmark.

Usage:
    python simulation/build_annotated_dataset.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pr_templates import get_all_templates

OUTPUT = Path(__file__).parent / "data" / "annotated_prs.jsonl"


def main() -> None:
    templates = get_all_templates()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT, "w") as f:
        for t in templates:
            record = {
                "id": f"{t.language[:2]}_{t.name}",
                "name": t.name,
                "language": t.language,
                "change_type": t.change_type,
                "severity": t.severity,
                "description": t.description,
                "diff": t.diff_template,
                "expected_findings": t.expected_findings,
                "annotations": [
                    {
                        "dimension": a.dimension,
                        "expected": a.expected,
                        "rationale": a.rationale,
                    }
                    for a in t.annotations
                ],
            }
            f.write(json.dumps(record) + "\n")

    print(f"Wrote {len(templates)} annotated PRs → {OUTPUT}")

    # Summary stats
    from collections import Counter
    langs = Counter(t.language for t in templates)
    sevs = Counter(t.severity for t in templates)
    all_flagged = [dim for t in templates for a in t.annotations if a.expected for dim in [a.dimension]]
    dim_counts = Counter(all_flagged)

    print(f"\nLanguage distribution:")
    for lang, count in sorted(langs.items()):
        print(f"  {lang:<15} {count:>3} templates")

    print(f"\nSeverity distribution:")
    for sev in ["critical", "high", "medium", "low"]:
        print(f"  {sev:<10} {sevs.get(sev, 0):>3} templates")

    print(f"\nDimension coverage (flagged count across all templates):")
    for dim, count in sorted(dim_counts.items(), key=lambda x: -x[1]):
        print(f"  {dim:<25} {count:>3}x")


if __name__ == "__main__":
    main()

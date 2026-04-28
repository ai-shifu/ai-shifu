#!/usr/bin/env python3
"""Scan the repository for harness drift and write a summary report."""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from pathlib import Path

from build_repo_knowledge_index import (
    DOCS_ROOT,
    GENERATED_COMMENT,
    parse_frontmatter,
)
from check_architecture_boundaries import (
    BACKEND_ROOT,
    FRONTEND_ROOT,
    DEFAULT_BASELINE,
    collect_backend_violations,
    collect_frontend_violations,
    dedupe_violations,
    load_baseline,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = ROOT / "docs" / "generated" / "harness-gardening-summary.md"
REVIEW_WINDOW_DAYS = 120
RETIRED_TERM_PATTERNS = ("tasks.md", "temporary root checklist")
ALLOWED_RETIRED_TERM_PATTERNS = {
    ROOT / "AGENTS.md": (
        re.compile(r"Do not create new root `tasks\.md` checklists\."),
    ),
    ROOT / "PLANS.md": (re.compile(r"Repository-root `tasks\.md` is retired\."),),
}
RETIRED_TERM_SCAN_PATHS = (
    ROOT / "AGENTS.md",
    ROOT / "ARCHITECTURE.md",
    ROOT / "PLANS.md",
    DOCS_ROOT / "README.md",
    DOCS_ROOT / "references",
    DOCS_ROOT / "product-specs",
    DOCS_ROOT / "exec-plans" / "active",
)


def stale_review_docs() -> list[str]:
    stale: list[str] = []
    cutoff = date.today().toordinal() - REVIEW_WINDOW_DAYS
    for category in ("design-docs", "product-specs"):
        for path in sorted((DOCS_ROOT / category).glob("*.md")):
            if path.name == "index.md":
                continue
            metadata = parse_frontmatter(path)
            reviewed = str(metadata.get("last_reviewed", "") or "").strip()
            if not reviewed:
                stale.append(f"{path.relative_to(ROOT)} (missing last_reviewed)")
                continue
            try:
                reviewed_date = datetime.strptime(reviewed, "%Y-%m-%d").date()
            except ValueError:
                stale.append(
                    f"{path.relative_to(ROOT)} (invalid last_reviewed={reviewed})"
                )
                continue
            if reviewed_date.toordinal() < cutoff:
                stale.append(f"{path.relative_to(ROOT)} (last_reviewed={reviewed})")
    return stale


def retired_term_hits() -> list[str]:
    hits: list[str] = []
    files: list[Path] = []
    for path in RETIRED_TERM_SCAN_PATHS:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.md")))
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        allowed_patterns = ALLOWED_RETIRED_TERM_PATTERNS.get(path, ())
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in allowed_patterns):
                continue
            for term in RETIRED_TERM_PATTERNS:
                if term in line:
                    hits.append(
                        f"{path.relative_to(ROOT)}:{line_number} contains retired "
                        f"term `{term}`"
                    )
    return hits


def stale_boundary_baseline() -> list[str]:
    current = dedupe_violations(
        collect_frontend_violations(FRONTEND_ROOT)
        + collect_backend_violations(BACKEND_ROOT)
    )
    current_keys = {item.key for item in current}
    baseline_keys = load_baseline(DEFAULT_BASELINE)
    return sorted(baseline_keys - current_keys)


def write_summary(
    path: Path,
    *,
    stale_docs: list[str],
    retired_terms: list[str],
    stale_baseline: list[str],
) -> None:
    lines = [
        GENERATED_COMMENT,
        "",
        "# Harness Gardening Summary",
        "",
        f"- Stale docs: `{len(stale_docs)}`",
        f"- Retired term hits: `{len(retired_terms)}`",
        f"- Stale boundary baseline entries: `{len(stale_baseline)}`",
        "",
    ]
    if stale_docs:
        lines.extend(["## Stale Docs", ""])
        lines.extend(f"- {item}" for item in stale_docs)
        lines.append("")
    if retired_terms:
        lines.extend(["## Retired Workflow Terms", ""])
        lines.extend(f"- {item}" for item in retired_terms)
        lines.append("")
    if stale_baseline:
        lines.extend(["## Stale Boundary Baseline", ""])
        lines.extend(f"- {item}" for item in stale_baseline)
        lines.append("")
    if not any((stale_docs, retired_terms, stale_baseline)):
        lines.extend(["No harness drift detected.", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run harness gardening drift checks.")
    parser.add_argument(
        "--summary-path",
        default=str(DEFAULT_SUMMARY),
        help="Markdown summary file written by the gardening run.",
    )
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Exit with code 1 when any drift is detected.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary_path = Path(args.summary_path).resolve()
    stale_docs = stale_review_docs()
    retired_terms = retired_term_hits()
    stale_baseline = stale_boundary_baseline()
    write_summary(
        summary_path,
        stale_docs=stale_docs,
        retired_terms=retired_terms,
        stale_baseline=stale_baseline,
    )
    print(f"Wrote harness gardening summary to {summary_path}")
    if args.fail_on_drift and any((stale_docs, retired_terms, stale_baseline)):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate the repository's agent-first harness layout."""

from __future__ import annotations

from pathlib import Path
import sys

from build_repo_knowledge_index import (
    DOCS_ROOT,
    FRONTMATTER_FIELDS,
    GARDENING_SUMMARY_PATH,
    GENERATED_COMMENT as KNOWLEDGE_GENERATED_COMMENT,
    build_knowledge_docs,
    parse_frontmatter,
)
from generate_ai_collab_docs import (
    DOC_COMMENT,
    MAX_AGENT_LINES,
    MAX_CLAUDE_LINES,
    MIN_AGENT_LINES,
    MIN_CLAUDE_LINES,
    REQUIRED_HEADINGS,
    build_documents,
)


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_BASELINE = DOCS_ROOT / "generated" / "architecture-boundary-baseline.json"
HARNESS_HEALTH = DOCS_ROOT / "generated" / "harness-health.md"
MANUAL_AGENTS = {
    ROOT / "AGENTS.md": (
        "ARCHITECTURE.md",
        "PLANS.md",
        "docs/engineering-baseline.md",
        "docs/exec-plans/active/",
        "python scripts/check_repo_harness.py",
        "python scripts/check_architecture_boundaries.py",
    ),
    ROOT / "src" / "api" / "AGENTS.md": (
        "../../ARCHITECTURE.md",
        "../../docs/engineering-baseline.md",
        "scripts/harness_diagnostics.py",
        "LiteLLM",
    ),
    ROOT / "src" / "cook-web" / "AGENTS.md": (
        "../../ARCHITECTURE.md",
        "../../docs/engineering-baseline.md",
        "src/lib/request.ts",
        "npm run test:e2e",
    ),
}
REQUIRED_ROOT_DOCS = (
    ROOT / "ARCHITECTURE.md",
    ROOT / "PLANS.md",
    DOCS_ROOT / "README.md",
    DOCS_ROOT / "engineering-baseline.md",
    DOCS_ROOT / "QUALITY_SCORE.md",
    DOCS_ROOT / "RELIABILITY.md",
    DOCS_ROOT / "SECURITY.md",
    DOCS_ROOT / "exec-plans" / "tech-debt-tracker.md",
    DOCS_ROOT / "design-docs" / "agent-first-harness-phase-2.md",
    DOCS_ROOT / "references" / "architecture-boundaries.md",
    BOUNDARY_BASELINE,
    HARNESS_HEALTH,
    GARDENING_SUMMARY_PATH,
)
REQUIRED_DIRS = (
    DOCS_ROOT / "design-docs",
    DOCS_ROOT / "product-specs",
    DOCS_ROOT / "references",
    DOCS_ROOT / "generated",
    DOCS_ROOT / "exec-plans" / "active",
    DOCS_ROOT / "exec-plans" / "completed",
)
MANUAL_RULES = {
    ROOT / ".claude" / "rules" / "global" / "testing-and-commit.md": (
        "docs/exec-plans/active/",
        "PLANS.md",
        "python scripts/check_repo_harness.py",
    ),
}
README_MARKERS = (
    "ARCHITECTURE.md",
    "PLANS.md",
    "design-docs/",
    "product-specs/",
    "references/",
    "exec-plans/active/",
    "generated/",
)
REQUIRED_WORKFLOWS = (
    ROOT / ".github" / "workflows" / "repo-harness.yml",
    ROOT / ".github" / "workflows" / "runtime-harness.yml",
    ROOT / ".github" / "workflows" / "harness-gardening.yml",
)


def check_ordered_headings(path: Path, text: str, errors: list[str]) -> None:
    positions: list[int] = []
    for heading in REQUIRED_HEADINGS:
        marker = f"## {heading}"
        index = text.find(marker)
        if index == -1:
            errors.append(f"Missing heading '{marker}' in {path}")
            return
        positions.append(index)
    if positions != sorted(positions):
        errors.append(f"Headings are out of order in {path}")


def check_generated_ai_docs(errors: list[str]) -> None:
    expected_docs = build_documents()
    for path, expected in sorted(expected_docs.items()):
        if not path.exists():
            errors.append(f"Missing generated AI doc: {path}")
            continue
        actual = path.read_text(encoding="utf-8")
        if DOC_COMMENT not in actual:
            errors.append(f"Missing generated-doc marker in {path}")
        if actual != expected:
            errors.append(f"Generated AI doc is stale: {path}")
        line_count = len(actual.splitlines())
        if path.name == "AGENTS.md" and not (
            MIN_AGENT_LINES <= line_count <= MAX_AGENT_LINES
        ):
            errors.append(
                f"{path} has {line_count} lines; expected between "
                f"{MIN_AGENT_LINES} and {MAX_AGENT_LINES}"
            )
        if path.name == "CLAUDE.md":
            if not (MIN_CLAUDE_LINES <= line_count <= MAX_CLAUDE_LINES):
                errors.append(
                    f"{path} has {line_count} lines; expected between "
                    f"{MIN_CLAUDE_LINES} and {MAX_CLAUDE_LINES}"
                )
            if "@AGENTS.md" not in actual:
                errors.append(f"{path} must include '@AGENTS.md'")


def check_generated_knowledge_docs(errors: list[str]) -> None:
    expected_docs = build_knowledge_docs()
    for path, expected in sorted(expected_docs.items()):
        if not path.exists():
            errors.append(f"Missing generated knowledge doc: {path}")
            continue
        actual = path.read_text(encoding="utf-8")
        if KNOWLEDGE_GENERATED_COMMENT not in actual:
            errors.append(f"Missing generated knowledge marker in {path}")
        if actual != expected:
            errors.append(f"Generated knowledge doc is stale: {path}")


def check_manual_agents(errors: list[str]) -> None:
    for path, markers in MANUAL_AGENTS.items():
        if not path.exists():
            errors.append(f"Missing manual AGENTS file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if DOC_COMMENT in text:
            errors.append(f"Manual AGENTS file should not be generated: {path}")
        check_ordered_headings(path, text, errors)
        for marker in markers:
            if marker not in text:
                errors.append(f"Missing marker '{marker}' in {path}")


def check_manual_rules(errors: list[str]) -> None:
    for path, markers in MANUAL_RULES.items():
        if not path.exists():
            errors.append(f"Missing manual Claude rule: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if DOC_COMMENT in text:
            errors.append(f"Manual Claude rule should not be generated: {path}")
        for marker in markers:
            if marker not in text:
                errors.append(f"Missing marker '{marker}' in {path}")


def check_root_docs(errors: list[str]) -> None:
    for path in REQUIRED_ROOT_DOCS:
        if not path.exists():
            errors.append(f"Missing required root knowledge doc: {path}")
    for path in REQUIRED_DIRS:
        if not path.exists():
            errors.append(f"Missing required docs directory: {path}")
    for path in REQUIRED_WORKFLOWS:
        if not path.exists():
            errors.append(f"Missing required harness workflow: {path}")

    readme = DOCS_ROOT / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        for marker in README_MARKERS:
            if marker not in text:
                errors.append(f"Missing marker '{marker}' in {readme}")

    if (ROOT / "tasks.md").exists():
        errors.append("Repository-root tasks.md is retired and must not exist")

    if BOUNDARY_BASELINE.exists():
        text = BOUNDARY_BASELINE.read_text(encoding="utf-8")
        if '"version"' not in text or '"violations"' not in text:
            errors.append(f"Boundary baseline is malformed: {BOUNDARY_BASELINE}")

    if GARDENING_SUMMARY_PATH.exists():
        text = GARDENING_SUMMARY_PATH.read_text(encoding="utf-8")
        if KNOWLEDGE_GENERATED_COMMENT not in text:
            errors.append(
                "Harness gardening summary is missing generated marker: "
                f"{GARDENING_SUMMARY_PATH}"
            )


def check_frontmatter_docs(errors: list[str]) -> None:
    for category in ("design-docs", "product-specs"):
        for path in sorted((DOCS_ROOT / category).glob("*.md")):
            if path.name == "index.md":
                continue
            metadata = parse_frontmatter(path)
            for field in FRONTMATTER_FIELDS:
                if not metadata.get(field):
                    errors.append(f"Missing frontmatter field '{field}' in {path}")


def main() -> int:
    errors: list[str] = []
    check_generated_ai_docs(errors)
    check_generated_knowledge_docs(errors)
    check_manual_agents(errors)
    check_manual_rules(errors)
    check_root_docs(errors)
    check_frontmatter_docs(errors)

    if errors:
        print("Repository harness validation failed:", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1

    print("Repository harness validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate layered AI collaboration doc coverage and ownership."""

from __future__ import annotations

from pathlib import Path
import sys

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

MANUAL_AGENTS = {
    ROOT / "AGENTS.md": "docs/engineering-baseline.md",
    ROOT / "src" / "api" / "AGENTS.md": "../../docs/engineering-baseline.md",
    ROOT / "src" / "cook-web" / "AGENTS.md": "../../docs/engineering-baseline.md",
    ROOT / ".github" / "AGENTS.md": "../docs/engineering-baseline.md",
    ROOT / "docker" / "AGENTS.md": "../docs/engineering-baseline.md",
    ROOT / "scripts" / "AGENTS.md": "../docs/engineering-baseline.md",
}

MANUAL_AGENT_MARKERS = {
    ROOT / "AGENTS.md": (
        "Use English for code, comments, commit subjects, and instruction files.",
        "Do not hardcode user-facing strings, secrets, or environment-specific URLs",
        "Before implementing a complex design or cross-module architecture change",
        "When a task changes shared contracts or AI collaboration guidance",
        "Run the smallest relevant verification first",
    ),
    ROOT / "src" / "api" / "AGENTS.md": (
        "Use the shared API response envelope with `code`, `message`, and `data`",
        "Do not edit applied migration files.",
        "Do not add hard database foreign-key constraints",
        "src/api/flaskr/common/config.py",
        "Do not bypass the LiteLLM wrapper",
        "namespaces under `src/i18n/`",
    ),
    ROOT / "src" / "cook-web" / "AGENTS.md": (
        "src/cook-web/src/lib/request.ts` and",
        "preserve the unified business-code handling path",
        "Keep Next.js route-entry conventions directly visible in new code",
        "shared i18n JSON namespaces under",
        "Legacy `c-*` directories remain active compatibility surfaces.",
    ),
    ROOT / ".github" / "AGENTS.md": (
        ".github/workflows/",
        "Preserve workflow trigger intent",
        "GitHub Actions secrets or vars",
        "prepare-release.yml",
        "build-on-release.yml",
    ),
    ROOT / "docker" / "AGENTS.md": (
        "docker-compose.dev.yml",
        "docker-compose.latest.yml",
        "docker-compose.yml",
        "Do not bake secrets",
        "docker/.env.example.full",
    ),
    ROOT / "scripts" / "AGENTS.md": (
        "idempotent behavior",
        "Do not silently rewrite tracked files",
        "generator and checker pairs aligned",
        "English-only",
        "python scripts/check_ai_collab_docs.py",
    ),
}

MANUAL_RULES = {
    ROOT / ".claude" / "rules" / "global" / "testing-and-commit.md": (
        "# Claude Rule: Testing And Commit",
        "docs/engineering-baseline.md",
        "English-only code-facing text",
        "docs/<topic>/design.md",
        "python scripts/check_ai_collab_docs.py",
    ),
    ROOT / ".claude" / "rules" / "global" / "skills-routing.md": (
        "# Claude Rule: Skills Routing",
        "SKILL.md",
    ),
    ROOT / ".claude" / "rules" / "backend" / "python-api.md": (
        "# Claude Rule: Backend Python API",
        "docs/engineering-baseline.md",
        "shared API response envelope with `code`, `message`, and `data`",
        "LiteLLM",
        "new Alembic migrations",
        "`src/i18n/`",
    ),
    ROOT / ".claude" / "rules" / "frontend" / "cook-web.md": (
        "# Claude Rule: Cook Web Frontend",
        "docs/engineering-baseline.md",
        "src/cook-web/src/lib/request.ts",
        "unified business-code handling",
        "`src/i18n/`",
        "`c-*` directories as active compatibility surfaces",
    ),
}

BASELINE_HEADINGS = (
    "## Quick Start",
    "## Critical Requirements",
    "## Repository Overview",
    "## Architecture",
    "## Database Model Conventions",
    "## API Contract Baseline",
    "## Testing Expectations",
    "## Development Workflow",
    "## CI/CD And Release Workflow",
    "## Performance Guidelines",
    "## Environment Configuration",
    "## Internationalization Rules",
    "## File And Directory Naming Conventions",
    "## Troubleshooting",
)

README_MARKERS = (
    "docs/<topic>/design.md",
    "docs/<topic>/tasks.md",
    "docs/engineering-baseline.md",
    "- [ ]",
    "- [x]",
)


def check_ordered_markers(
    path: Path, text: str, markers: tuple[str, ...], errors: list[str]
) -> None:
    """Ensure markers exist and appear in order."""

    positions: list[int] = []
    for marker in markers:
        index = text.find(marker)
        if index == -1:
            errors.append(f"Missing marker '{marker}' in {path}")
            return
        positions.append(index)

    if positions != sorted(positions):
        errors.append(f"Markers are out of order in {path}")


def check_generated_line_count(path: Path, text: str, errors: list[str]) -> None:
    """Validate line-count constraints for generated files."""

    line_count = len(text.splitlines())
    if path.name == "AGENTS.md":
        if not MIN_AGENT_LINES <= line_count <= MAX_AGENT_LINES:
            errors.append(
                f"{path} has {line_count} lines; expected between "
                f"{MIN_AGENT_LINES} and {MAX_AGENT_LINES}"
            )
    elif path.name == "CLAUDE.md":
        if not MIN_CLAUDE_LINES <= line_count <= MAX_CLAUDE_LINES:
            errors.append(
                f"{path} has {line_count} lines; expected between "
                f"{MIN_CLAUDE_LINES} and {MAX_CLAUDE_LINES}"
            )
        if "@AGENTS.md" not in text:
            errors.append(f"{path} must include '@AGENTS.md'")


def check_special_formats(path: Path, text: str, errors: list[str]) -> None:
    """Validate generated Cursor and Copilot instruction file structure."""

    if path.suffix == ".mdc":
        if not text.startswith("---\n"):
            errors.append(f"{path} must start with frontmatter")
        if "description:" not in text or "alwaysApply:" not in text:
            errors.append(f"{path} must define Cursor rule metadata")

    if path.name.endswith(".instructions.md"):
        if not text.startswith("---\n"):
            errors.append(f"{path} must start with frontmatter")
        if 'applyTo: "' not in text:
            errors.append(f"{path} must define applyTo frontmatter")


def check_generated_docs(expected_docs: dict[Path, str], errors: list[str]) -> None:
    """Validate generated docs exist and match the generator output."""

    for path, expected in sorted(expected_docs.items()):
        if not path.exists():
            errors.append(f"Missing expected generated file: {path}")
            continue

        actual = path.read_text(encoding="utf-8")
        if DOC_COMMENT not in actual:
            errors.append(f"Missing generated-doc marker in {path}")
        if actual != expected:
            errors.append(f"Generated file is stale or edited manually: {path}")

        check_generated_line_count(path, actual, errors)
        check_special_formats(path, actual, errors)
        if path.name == "AGENTS.md":
            check_ordered_markers(
                path,
                actual,
                tuple(f"## {heading}" for heading in REQUIRED_HEADINGS),
                errors,
            )


def check_manual_agents(errors: list[str]) -> None:
    """Validate hand-maintained root/backend/frontend AGENTS files."""

    for path, baseline_link in MANUAL_AGENTS.items():
        if not path.exists():
            errors.append(f"Missing required manual AGENTS file: {path}")
            continue

        text = path.read_text(encoding="utf-8")
        if DOC_COMMENT in text:
            errors.append(
                f"Manual AGENTS file should not contain generated marker: {path}"
            )
        if baseline_link not in text:
            errors.append(f"Missing engineering baseline link in {path}")
        for marker in MANUAL_AGENT_MARKERS[path]:
            if marker not in text:
                errors.append(f"Missing marker '{marker}' in {path}")

        check_ordered_markers(
            path, text, tuple(f"## {heading}" for heading in REQUIRED_HEADINGS), errors
        )


def check_manual_rules(errors: list[str]) -> None:
    """Validate hand-maintained Claude-only routing rules."""

    for path, required_markers in MANUAL_RULES.items():
        if not path.exists():
            errors.append(f"Missing required manual Claude rule: {path}")
            continue

        text = path.read_text(encoding="utf-8")
        if DOC_COMMENT in text:
            errors.append(
                f"Manual Claude rule should not contain generated marker: {path}"
            )
        for marker in required_markers:
            if marker not in text:
                errors.append(f"Missing marker '{marker}' in {path}")


def check_baseline_and_readme(errors: list[str]) -> None:
    """Validate the engineering baseline and docs README."""

    baseline = ROOT / "docs" / "engineering-baseline.md"
    if not baseline.exists():
        errors.append(f"Missing engineering baseline doc: {baseline}")
    else:
        text = baseline.read_text(encoding="utf-8")
        if DOC_COMMENT in text:
            errors.append(
                "Engineering baseline should be hand-maintained, not generated"
            )
        check_ordered_markers(baseline, text, BASELINE_HEADINGS, errors)

    readme = ROOT / "docs" / "README.md"
    if not readme.exists():
        errors.append(f"Missing docs README: {readme}")
    else:
        text = readme.read_text(encoding="utf-8")
        for marker in README_MARKERS:
            if marker not in text:
                errors.append(f"Missing marker '{marker}' in {readme}")


def main() -> int:
    expected_docs = build_documents()
    errors: list[str] = []

    check_generated_docs(expected_docs, errors)
    check_manual_agents(errors)
    check_manual_rules(errors)
    check_baseline_and_readme(errors)

    if errors:
        print("AI collaboration doc validation failed:", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1

    manual_count = len(MANUAL_AGENTS) + len(MANUAL_RULES) + 2
    print(
        f"Validated {len(expected_docs)} generated AI collaboration documents "
        f"and {manual_count} hand-maintained doc surfaces."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

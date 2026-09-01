#!/usr/bin/env python3
"""Validate the repository's agent-first harness layout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from build_repo_knowledge_index import (
    DOCS_ROOT,
    FRONTMATTER_FIELDS,
    GARDENING_SUMMARY_PATH,
    REQUIRED_RUNTIME_ASSETS,
    build_knowledge_docs,
    parse_frontmatter,
)
from build_repo_knowledge_index import (
    GENERATED_COMMENT as KNOWLEDGE_GENERATED_COMMENT,
)
from check_example_identifiers import find_violations as find_identifier_violations
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
FRONTEND_ROOT = ROOT / "src" / "web"
CODEX_ENVIRONMENT = ROOT / ".codex" / "environments" / "environment.toml"
FRONTEND_ENV_FILENAMES = (
    ".env",
    ".env.local",
    ".env.development",
    ".env.development.local",
    ".env.production",
    ".env.production.local",
    ".env.test",
    ".env.test.local",
)
STALE_FRONTEND_PATH = "src/" + "cook-web"
STALE_FRONTEND_PATH_PARTS = tuple(STALE_FRONTEND_PATH.split("/"))
STALE_FRONTEND_PATH_WHOLE_FILE_ALLOWLIST = {
    Path("docs/exec-plans/active/rename-cook-web-directory.md"),
}
STALE_FRONTEND_PATH_LINE_ALLOWLIST = {
    Path(".github/workflows/prepare-release.yml"): {
        f'"legacy_path": "{STALE_FRONTEND_PATH}/package-lock.json",': 1,
    },
}
STALE_FRONTEND_PATH_CONTEXT_ALLOWLIST = {
    Path(".github/workflows/prepare-release.yml"): (
        "- name: Generate MarkdownFlow dependency changelog",
        '"name": "markdown-flow-ui",',
        '"path": "src/web/package-lock.json",',
        "def build_dependency_section",
    ),
}
BOUNDARY_BASELINE = DOCS_ROOT / "generated" / "architecture-boundary-baseline.json"
HARNESS_HEALTH = DOCS_ROOT / "generated" / "harness-health.md"
PR_REVIEW_SCOPE_MARKERS = (
    "one clearly defined problem",
    "correctly, safely, completely, and with adequate tests",
    "responsibility boundary",
)
CURSOR_REPOSITORY_AI_RULE = ROOT / ".cursor" / "rules" / "repository-ai-collab.mdc"
COPILOT_REPOSITORY_AI_INSTRUCTIONS = ROOT / ".github" / "copilot-instructions.md"
MANUAL_AGENTS = {
    ROOT / "AGENTS.md": (
        "ARCHITECTURE.md",
        "PLANS.md",
        "docs/engineering-baseline.md",
        "docs/exec-plans/active/",
        "docs/references/frontend-product-analytics.md",
        "Umami",
        *PR_REVIEW_SCOPE_MARKERS,
        "product analytics as a completion requirement",
        "best-effort",
        "python scripts/check_repo_harness.py",
        "python scripts/check_architecture_boundaries.py",
    ),
    ROOT / "src" / "api" / "AGENTS.md": (
        "../../ARCHITECTURE.md",
        "../../docs/engineering-baseline.md",
        "scripts/harness_diagnostics.py",
        "LiteLLM",
    ),
    ROOT / "src" / "web" / "AGENTS.md": (
        "../../ARCHITECTURE.md",
        "../../docs/engineering-baseline.md",
        "../../docs/references/frontend-product-analytics.md",
        "Umami",
        "new user-facing Cook Web capability or interaction path",
        "useTracking",
        "fail-open",
        "src/lib/request.ts",
        "npm run test:e2e",
    ),
}
GENERATED_AI_DOC_MARKERS = {
    CURSOR_REPOSITORY_AI_RULE: PR_REVIEW_SCOPE_MARKERS,
    COPILOT_REPOSITORY_AI_INSTRUCTIONS: PR_REVIEW_SCOPE_MARKERS,
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
    DOCS_ROOT / "references" / "frontend-product-analytics.md",
    BOUNDARY_BASELINE,
    HARNESS_HEALTH,
    GARDENING_SUMMARY_PATH,
)
REQUIRED_DOC_MARKERS = {
    DOCS_ROOT / "references" / "frontend-product-analytics.md": (
        "New UI Feature Requirement",
        "definition of done",
        "generic SPA pageview does not satisfy this requirement",
    ),
}
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
    """Check ordered headings."""
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
    """Check generated AI docs."""
    expected_docs = build_documents()
    for path, markers in GENERATED_AI_DOC_MARKERS.items():
        expected = expected_docs.get(path)
        if expected is None:
            errors.append(f"Missing generated AI doc definition: {path}")
            continue
        errors.extend(
            f"Missing marker '{marker}' in generated AI doc definition: {path}"
            for marker in markers
            if marker not in expected
        )
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
    """Check generated knowledge docs."""
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
    """Check manual agents."""
    for path, markers in MANUAL_AGENTS.items():
        if not path.exists():
            errors.append(f"Missing manual AGENTS file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if DOC_COMMENT in text:
            errors.append(f"Manual AGENTS file should not be generated: {path}")
        check_ordered_headings(path, text, errors)
        errors.extend(
            f"Missing marker '{marker}' in {path}"
            for marker in markers
            if marker not in text
        )


def check_manual_rules(errors: list[str]) -> None:
    """Check manual rules."""
    for path, markers in MANUAL_RULES.items():
        if not path.exists():
            errors.append(f"Missing manual Claude rule: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if DOC_COMMENT in text:
            errors.append(f"Manual Claude rule should not be generated: {path}")
        errors.extend(
            f"Missing marker '{marker}' in {path}"
            for marker in markers
            if marker not in text
        )


def check_root_docs(errors: list[str]) -> None:
    """Check root docs."""
    errors.extend(
        f"Missing required root knowledge doc: {path}"
        for path in REQUIRED_ROOT_DOCS
        if not path.exists()
    )
    errors.extend(
        f"Missing required docs directory: {path}"
        for path in REQUIRED_DIRS
        if not path.exists()
    )
    for path, markers in REQUIRED_DOC_MARKERS.items():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        errors.extend(
            f"Missing marker '{marker}' in {path}"
            for marker in markers
            if marker not in text
        )
    errors.extend(
        f"Missing required harness workflow: {path}"
        for path in REQUIRED_WORKFLOWS
        if not path.exists()
    )
    errors.extend(
        f"Missing required runtime harness asset: {path}"
        for path in REQUIRED_RUNTIME_ASSETS
        if not path.exists()
    )

    readme = DOCS_ROOT / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        errors.extend(
            f"Missing marker '{marker}' in {readme}"
            for marker in README_MARKERS
            if marker not in text
        )

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


def _stale_path_is_in_allowed_context(
    relative_path: Path, lines: list[str], line_numbers: list[int]
) -> bool:
    """Keep an allowed stale path inside its owning workflow step."""
    context_markers = STALE_FRONTEND_PATH_CONTEXT_ALLOWLIST.get(relative_path)
    if not context_markers:
        return True

    step_starts = [
        index for index, line in enumerate(lines) if line.strip() == context_markers[0]
    ]
    if len(step_starts) != 1:
        return False

    step_start = step_starts[0]
    step_indent = len(lines[step_start]) - len(lines[step_start].lstrip())
    step_end = len(lines)
    for index in range(step_start + 1, len(lines)):
        line = lines[index]
        line_indent = len(line) - len(line.lstrip())
        if line_indent == step_indent and line.strip().startswith("- name:"):
            step_end = index
            break

    step_lines = lines[step_start:step_end]
    return all(
        any(marker in line for line in step_lines) for marker in context_markers
    ) and all(step_start <= line_number - 1 < step_end for line_number in line_numbers)


def _contains_stale_frontend_path(parts: tuple[str, ...]) -> bool:
    """Match the retired frontend path as complete path components."""
    return any(
        parts[index : index + len(STALE_FRONTEND_PATH_PARTS)]
        == STALE_FRONTEND_PATH_PARTS
        for index in range(len(parts) - len(STALE_FRONTEND_PATH_PARTS) + 1)
    )


def check_frontend_path_contract(errors: list[str]) -> None:
    """Require the current web frontend path and guard stale path additions."""
    if not FRONTEND_ROOT.is_dir():
        errors.append(f"Missing web frontend directory: {FRONTEND_ROOT}")

    try:
        result = subprocess.run(
            ["git", "ls-files", "--stage", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        errors.append(f"Unable to enumerate tracked files for path validation: {error}")
        return

    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        try:
            raw_metadata, raw_filename = raw_path.split(b"\t", 1)
            index_mode, object_id, _stage = raw_metadata.split(b" ", 2)
        except ValueError as error:
            errors.append(f"Unable to parse tracked file entry {raw_path!r}: {error}")
            continue

        relative_path = Path(raw_filename.decode("utf-8", errors="surrogateescape"))
        if _contains_stale_frontend_path(relative_path.parts):
            errors.append(f"Stale frontend path in tracked filename: {relative_path}")

        path = ROOT / relative_path
        if index_mode == b"160000":
            continue
        if index_mode == b"120000":
            try:
                symlink_target = subprocess.run(
                    ["git", "cat-file", "blob", object_id.decode("ascii")],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                ).stdout.decode("utf-8", errors="surrogateescape")
            except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
                errors.append(f"Unable to scan tracked symlink {path}: {error}")
                continue
            if _contains_stale_frontend_path(Path(symlink_target.rstrip("\n")).parts):
                errors.append(
                    f"Stale frontend path in tracked symlink target: "
                    f"{relative_path} -> {symlink_target}"
                )
            continue

        if relative_path in STALE_FRONTEND_PATH_WHOLE_FILE_ALLOWLIST:
            continue
        try:
            text = path.read_bytes().decode("utf-8", errors="surrogateescape")
        except OSError as error:
            errors.append(f"Unable to scan tracked file {path}: {error}")
            continue

        actual_occurrences: dict[str, int] = {}
        stale_line_numbers: list[int] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if STALE_FRONTEND_PATH in line:
                stripped_line = line.strip()
                actual_occurrences[stripped_line] = (
                    actual_occurrences.get(stripped_line, 0) + 1
                )
                stale_line_numbers.append(line_number)
        expected_occurrences = STALE_FRONTEND_PATH_LINE_ALLOWLIST.get(relative_path, {})
        if actual_occurrences != expected_occurrences:
            errors.append(
                f"Unexpected stale frontend path occurrences in {path}: "
                f"expected {expected_occurrences}, got {actual_occurrences}"
            )
        elif not _stale_path_is_in_allowed_context(
            relative_path, text.splitlines(), stale_line_numbers
        ):
            errors.append(
                f"Allowed stale frontend path in {path} is outside its "
                "historical release lookup step"
            )


def check_frontend_runtime_contract(errors: list[str]) -> None:
    """Keep the frontend development and production entry points direct."""
    package_path = FRONTEND_ROOT / "package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"Unable to load frontend package scripts: {error}")
        return

    scripts = package.get("scripts", {})
    expected_scripts = {
        "dev": "next dev --turbopack",
        "build": "next build",
    }
    for script_name, expected_command in expected_scripts.items():
        if scripts.get(script_name) != expected_command:
            errors.append(
                f"Frontend package script '{script_name}' must be '{expected_command}'"
            )

    run_web_path = ROOT / ".cursor" / "run-web.sh"
    try:
        run_web = run_web_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"Unable to load Cursor frontend launcher: {error}")
        return
    if "exec npm run dev -- -H 0.0.0.0 -p 3000" not in run_web:
        errors.append(f"{run_web_path} must launch through 'npm run dev'")


def check_codex_frontend_asset_reuse(errors: list[str]) -> None:
    """Exercise current Codex source checkout asset reuse."""
    try:
        environment = tomllib.loads(CODEX_ENVIRONMENT.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        errors.append(f"Unable to load Codex environment config: {error}")
        return

    setup = environment.get("setup", {})
    current_frontend = Path("src") / "web"
    fixtures = (
        ("current assets", current_frontend, current_frontend, current_frontend),
    )

    for platform in ("darwin", "linux"):
        platform_setup = setup.get(platform, {})
        script = platform_setup.get("script")
        if not isinstance(script, str) or not script.strip():
            errors.append(
                f"Missing Codex {platform} setup script in {CODEX_ENVIRONMENT}"
            )
            continue

        for (
            fixture_name,
            env_directory,
            modules_directory,
            manifest_directory,
        ) in fixtures:
            with tempfile.TemporaryDirectory(
                prefix=f"ai-shifu-codex-{platform}-"
            ) as temporary_directory:
                fixture_root = Path(temporary_directory)
                source_tree = fixture_root / "source"
                worktree = fixture_root / "worktree"
                target_frontend = worktree / current_frontend
                target_frontend.mkdir(parents=True)

                lockfile_content = "compatible-lockfile\n"
                target_manifest = target_frontend / "package-lock.json"
                target_manifest.write_text(lockfile_content, encoding="utf-8")

                source_manifest = source_tree / manifest_directory / "package-lock.json"
                source_manifest.parent.mkdir(parents=True, exist_ok=True)
                source_manifest.write_text(lockfile_content, encoding="utf-8")

                source_envs: dict[str, Path] = {}
                source_env_modes: dict[str, int] = {}
                for env_filename in FRONTEND_ENV_FILENAMES:
                    source_env = source_tree / env_directory / env_filename
                    source_env.parent.mkdir(parents=True, exist_ok=True)
                    source_env.write_text(
                        f"FIXTURE={fixture_name}:{env_filename}\n", encoding="utf-8"
                    )
                    source_mode = 0o600 if env_filename.endswith(".local") else 0o640
                    source_env.chmod(source_mode)
                    source_envs[env_filename] = source_env
                    source_env_modes[env_filename] = source_mode

                source_modules = source_tree / modules_directory / "node_modules"
                source_modules.mkdir(parents=True, exist_ok=True)

                command_environment = os.environ.copy()
                command_environment.update(
                    {
                        "CODEX_SOURCE_TREE_PATH": str(source_tree),
                        "CODEX_WORKTREE_PATH": str(worktree),
                    }
                )
                try:
                    result = subprocess.run(
                        ["sh"],
                        cwd=worktree,
                        env=command_environment,
                        input=script,
                        text=True,
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as error:
                    errors.append(
                        f"Unable to run Codex {platform} {fixture_name} fixture: {error}"
                    )
                    continue

                fixture_label = f"Codex {platform} {fixture_name} fixture"
                if result.returncode != 0:
                    errors.append(
                        f"{fixture_label} failed with exit {result.returncode}: "
                        f"{result.stderr.strip()}"
                    )
                    continue

                for env_filename, source_env in source_envs.items():
                    target_env = target_frontend / env_filename
                    if not target_env.is_file() or target_env.read_text(
                        encoding="utf-8"
                    ) != source_env.read_text(encoding="utf-8"):
                        errors.append(
                            f"{fixture_label} did not copy the expected {env_filename}"
                        )
                        continue
                    if (
                        target_env.stat().st_mode & 0o777
                        != source_env_modes[env_filename]
                    ):
                        errors.append(
                            f"{fixture_label} did not preserve the mode of {env_filename}"
                        )

                target_modules = target_frontend / "node_modules"
                if not target_modules.is_symlink():
                    errors.append(
                        f"{fixture_label} did not reuse compatible node_modules"
                    )
                elif target_modules.resolve() != source_modules.resolve():
                    errors.append(
                        f"{fixture_label} reused node_modules from the wrong path"
                    )

                for occupancy_mode in ("customized", "dangling"):
                    occupied_worktree = fixture_root / f"{occupancy_mode}-worktree"
                    occupied_frontend = occupied_worktree / current_frontend
                    occupied_frontend.mkdir(parents=True)
                    (occupied_frontend / "package-lock.json").write_text(
                        lockfile_content, encoding="utf-8"
                    )
                    occupied_env = occupied_frontend / ".env"
                    occupied_env_link_target = None
                    if occupancy_mode == "customized":
                        occupied_env.write_text("CUSTOMIZED=1\n", encoding="utf-8")
                    else:
                        occupied_env.symlink_to(occupied_frontend / "missing.env")
                        occupied_env_link_target = occupied_env.readlink()

                    occupied_environment = command_environment.copy()
                    occupied_environment["CODEX_WORKTREE_PATH"] = str(occupied_worktree)
                    occupied_result = subprocess.run(
                        ["sh"],
                        cwd=occupied_worktree,
                        env=occupied_environment,
                        input=script,
                        text=True,
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    occupied_label = f"{fixture_label} {occupancy_mode} env fixture"
                    if occupied_result.returncode != 0:
                        errors.append(
                            f"{occupied_label} failed with exit "
                            f"{occupied_result.returncode}: "
                            f"{occupied_result.stderr.strip()}"
                        )
                        continue

                    for env_filename in FRONTEND_ENV_FILENAMES:
                        if env_filename == ".env":
                            continue
                        occupied_local_env = occupied_frontend / env_filename
                        if (
                            occupied_local_env.exists()
                            or occupied_local_env.is_symlink()
                        ):
                            errors.append(
                                f"{occupied_label} copied another frontend env file: "
                                f"{env_filename}"
                            )
                    if occupancy_mode == "customized":
                        if occupied_env.read_text(encoding="utf-8") != "CUSTOMIZED=1\n":
                            errors.append(
                                f"{occupied_label} overwrote the customized env file"
                            )
                    elif not occupied_env.is_symlink():
                        errors.append(
                            f"{occupied_label} did not preserve the dangling symlink"
                        )
                    elif occupied_env.readlink() != occupied_env_link_target:
                        errors.append(
                            f"{occupied_label} changed the dangling symlink target"
                        )


def check_frontmatter_docs(errors: list[str]) -> None:
    """Check frontmatter docs."""
    for category in ("design-docs", "product-specs"):
        for path in sorted((DOCS_ROOT / category).glob("*.md")):
            if path.name == "index.md":
                continue
            metadata = parse_frontmatter(path)
            errors.extend(
                f"Missing frontmatter field '{field}' in {path}"
                for field in FRONTMATTER_FIELDS
                if not metadata.get(field)
            )


def check_example_identifiers(errors: list[str]) -> None:
    """Check example identifiers."""
    errors.extend(str(violation) for violation in find_identifier_violations())


def main() -> int:
    """Validate collaboration guidance and generated repository knowledge."""
    errors: list[str] = []
    check_generated_ai_docs(errors)
    check_generated_knowledge_docs(errors)
    check_manual_agents(errors)
    check_manual_rules(errors)
    check_root_docs(errors)
    check_frontend_path_contract(errors)
    check_frontend_runtime_contract(errors)
    check_codex_frontend_asset_reuse(errors)
    check_frontmatter_docs(errors)
    check_example_identifiers(errors)

    if errors:
        print("Repository harness validation failed:", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1

    print("Repository harness validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate the repository's agent-first harness layout."""

from __future__ import annotations

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
LEGACY_FRONTEND_PATH = "src/" + "cook-web"
LEGACY_FRONTEND_FILENAME_TOKEN = "cook-" + "web"
LEGACY_FRONTEND_FILENAME_ALLOWLIST = {
    Path("docs/exec-plans/active/rename-cook-web-directory.md"),
}
LEGACY_FRONTEND_IGNORE_PATTERNS = (
    f"{LEGACY_FRONTEND_PATH}/node_modules",
    f"{LEGACY_FRONTEND_PATH}/.pnp",
    f"{LEGACY_FRONTEND_PATH}/**/.pnp.*",
    f"{LEGACY_FRONTEND_PATH}/.yarn/*",
    f"!{LEGACY_FRONTEND_PATH}/.yarn/patches",
    f"!{LEGACY_FRONTEND_PATH}/.yarn/plugins",
    f"!{LEGACY_FRONTEND_PATH}/.yarn/releases",
    f"!{LEGACY_FRONTEND_PATH}/.yarn/versions",
    f"{LEGACY_FRONTEND_PATH}/coverage",
    f"{LEGACY_FRONTEND_PATH}/playwright-report",
    f"{LEGACY_FRONTEND_PATH}/playwright/.auth",
    f"{LEGACY_FRONTEND_PATH}/test-results",
    f"{LEGACY_FRONTEND_PATH}/.next/",
    f"{LEGACY_FRONTEND_PATH}/out/",
    f"{LEGACY_FRONTEND_PATH}/build",
    f"{LEGACY_FRONTEND_PATH}/**/*.pem",
    f"{LEGACY_FRONTEND_PATH}/**/.env*",
    f"{LEGACY_FRONTEND_PATH}/**/.pnpm-debug.log*",
    f"{LEGACY_FRONTEND_PATH}/**/.vercel",
    f"{LEGACY_FRONTEND_PATH}/**/*.tsbuildinfo",
    f"{LEGACY_FRONTEND_PATH}/**/next-env.d.ts",
    f"{LEGACY_FRONTEND_PATH}/**/.eslintcache",
)
LEGACY_FRONTEND_PATH_OCCURRENCE_ALLOWLIST = {
    Path(".gitignore"): dict.fromkeys(LEGACY_FRONTEND_IGNORE_PATTERNS, 1),
    Path(".codex/environments/environment.toml"): {
        f'legacy_frontend_directory="$source_tree/{LEGACY_FRONTEND_PATH}"': 2,
    },
    Path(".github/workflows/prepare-release.yml"): {
        f'"legacy_path": "{LEGACY_FRONTEND_PATH}/package-lock.json",': 1,
    },
}
LEGACY_FRONTEND_PATH_WHOLE_FILE_ALLOWLIST = {
    Path("docs/exec-plans/active/rename-cook-web-directory.md"): (
        "Rename The Cook Web Directory"
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


def check_frontend_path_contract(errors: list[str]) -> None:
    """Require the web path and reject stale tracked path assumptions."""
    if not FRONTEND_ROOT.is_dir():
        errors.append(f"Missing web frontend directory: {FRONTEND_ROOT}")

    # Existing checkouts can retain ignored .env, node_modules, or build output
    # under the old directory after Git applies the tracked rename. The tracked
    # file inventory below is the repository contract; ignored local residue
    # must not make the same commit pass in CI but fail for an existing checkout.

    for (
        relative_path,
        expected_occurrences,
    ) in LEGACY_FRONTEND_PATH_OCCURRENCE_ALLOWLIST.items():
        path = ROOT / relative_path
        if not path.is_file():
            errors.append(f"Missing legacy-path compatibility surface: {path}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            errors.append(
                f"Unable to validate legacy path compatibility in {path}: {error}"
            )
            continue

        actual_occurrences: dict[str, int] = {}
        for line in text.splitlines():
            if LEGACY_FRONTEND_PATH not in line:
                continue
            stripped_line = line.strip()
            actual_occurrences[stripped_line] = (
                actual_occurrences.get(stripped_line, 0) + 1
            )
        if actual_occurrences != expected_occurrences:
            errors.append(
                f"Unexpected legacy frontend path occurrences in {path}: "
                f"expected {expected_occurrences}, got {actual_occurrences}"
            )

    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
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
        relative_path = Path(raw_path.decode("utf-8", errors="surrogateescape"))
        if (
            LEGACY_FRONTEND_FILENAME_TOKEN in relative_path.as_posix()
            and relative_path not in LEGACY_FRONTEND_FILENAME_ALLOWLIST
        ):
            errors.append(f"Stale frontend name in tracked path: {relative_path}")
        path = ROOT / relative_path
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if relative_path in LEGACY_FRONTEND_PATH_OCCURRENCE_ALLOWLIST:
            continue
        if LEGACY_FRONTEND_PATH not in text:
            continue

        whole_file_marker = LEGACY_FRONTEND_PATH_WHOLE_FILE_ALLOWLIST.get(relative_path)
        if whole_file_marker is None:
            errors.append(f"Stale frontend path '{LEGACY_FRONTEND_PATH}' in {path}")
        elif whole_file_marker not in text:
            errors.append(
                f"Legacy frontend path allowlist marker '{whole_file_marker}' "
                f"is missing in {path}"
            )


def check_codex_frontend_asset_reuse(errors: list[str]) -> None:
    """Exercise current, legacy, and upgraded Codex source checkout layouts."""
    try:
        environment = tomllib.loads(CODEX_ENVIRONMENT.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        errors.append(f"Unable to load Codex environment config: {error}")
        return

    setup = environment.get("setup", {})
    current_frontend = Path("src") / "web"
    legacy_frontend = Path("src") / LEGACY_FRONTEND_FILENAME_TOKEN
    fixtures = (
        ("current assets", current_frontend, current_frontend, current_frontend),
        ("legacy revision", legacy_frontend, legacy_frontend, legacy_frontend),
        ("upgraded checkout", legacy_frontend, legacy_frontend, current_frontend),
        (
            "current env with legacy modules",
            current_frontend,
            legacy_frontend,
            current_frontend,
        ),
        (
            "legacy env with current modules",
            legacy_frontend,
            current_frontend,
            current_frontend,
        ),
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

                source_env = source_tree / env_directory / ".env"
                source_env.parent.mkdir(parents=True, exist_ok=True)
                source_env.write_text(f"FIXTURE={fixture_name}\n", encoding="utf-8")

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

                target_env = target_frontend / ".env"
                if not target_env.is_file() or target_env.read_text(
                    encoding="utf-8"
                ) != source_env.read_text(encoding="utf-8"):
                    errors.append(f"{fixture_label} did not copy the expected .env")

                target_modules = target_frontend / "node_modules"
                if not target_modules.is_symlink():
                    errors.append(
                        f"{fixture_label} did not reuse compatible node_modules"
                    )
                elif target_modules.resolve() != source_modules.resolve():
                    errors.append(
                        f"{fixture_label} reused node_modules from the wrong path"
                    )


def check_legacy_frontend_artifact_ignores(errors: list[str]) -> None:
    """Keep migrated local artifacts ignored without hiding legacy source files."""
    legacy_frontend = Path("src") / LEGACY_FRONTEND_FILENAME_TOKEN
    artifact_paths = {
        legacy_frontend / relative_path
        for relative_path in (
            "node_modules/package/index.js",
            ".pnp",
            "cache/.pnp.cjs",
            ".yarn/cache/package.zip",
            "coverage/lcov.info",
            "playwright-report/index.html",
            "playwright/.auth/state.json",
            "test-results/results.json",
            ".next/cache/data",
            "out/index.html",
            "build/index.html",
            "certificates/local.pem",
            "config/.env.preview",
            ".pnpm-debug.log.1",
            "logs/.pnpm-debug.log.2",
            "deployment/.vercel/project.json",
            "cache/tsconfig.tsbuildinfo",
            "generated/next-env.d.ts",
            "cache/.eslintcache",
        )
    }
    visible_paths = {
        legacy_frontend / "src" / "app" / "page.tsx",
        legacy_frontend / "cache" / ".pnp",
        legacy_frontend / ".yarn" / "patches" / "package.patch",
        legacy_frontend / ".yarn" / "plugins" / "plugin.cjs",
        legacy_frontend / ".yarn" / "releases" / "yarn.cjs",
        legacy_frontend / ".yarn" / "versions" / "version.yml",
    }
    candidates = sorted((*artifact_paths, *visible_paths))
    fixture_environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }

    try:
        ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(
            prefix="ai-shifu-legacy-ignore-"
        ) as temporary_directory:
            fixture_root = Path(temporary_directory)
            empty_template = fixture_root / "empty-template"
            repository = fixture_root / "repository"
            empty_template.mkdir()
            repository.mkdir()
            init_result = subprocess.run(
                ["git", "init", "--quiet", f"--template={empty_template}"],
                cwd=repository,
                env=fixture_environment,
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if init_result.returncode != 0:
                errors.append(
                    "Unable to initialize legacy ignore fixture: "
                    f"{init_result.stderr.strip() or f'git exited {init_result.returncode}'}"
                )
                return
            (repository / ".gitignore").write_text(ignore_text, encoding="utf-8")
            result = subprocess.run(
                [
                    "git",
                    "-c",
                    f"core.excludesFile={os.devnull}",
                    "check-ignore",
                    "--no-index",
                    "--stdin",
                ],
                cwd=repository,
                env=fixture_environment,
                input="".join(f"{path.as_posix()}\n" for path in candidates),
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        errors.append(f"Unable to validate legacy frontend ignores: {error}")
        return

    if result.returncode not in (0, 1):
        errors.append(
            "Unable to validate legacy frontend ignores: "
            f"{result.stderr.strip() or f'git exited {result.returncode}'}"
        )
        return

    ignored_paths = {Path(line) for line in result.stdout.splitlines() if line}
    missing_ignores = sorted(artifact_paths - ignored_paths)
    if missing_ignores:
        errors.append(
            "Legacy frontend artifacts are not ignored: "
            + ", ".join(path.as_posix() for path in missing_ignores)
        )
    hidden_visible_paths = sorted(visible_paths & ignored_paths)
    if hidden_visible_paths:
        errors.append(
            "Legacy frontend ignore compatibility hides visible paths: "
            + ", ".join(path.as_posix() for path in hidden_visible_paths)
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
    check_codex_frontend_asset_reuse(errors)
    check_legacy_frontend_artifact_ignores(errors)
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

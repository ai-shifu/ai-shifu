#!/usr/bin/env python3
"""Exercise instruction validation independently of the retired generator."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import check_repo_harness as harness


class RepoInstructionsTest(unittest.TestCase):
    """Protect manual ownership, navigation, and required instruction guardrails."""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.copilot = self.root / ".github/copilot-instructions.md"
        self.enterContext(patch.object(harness, "ROOT", self.root))
        self.enterContext(
            patch.object(harness, "COPILOT_REPOSITORY_AI_INSTRUCTIONS", self.copilot)
        )

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_git(self, *args: str) -> None:
        subprocess.run(
            ["git", "-c", f"core.excludesFile={os.devnull}", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
        )

    def test_rejects_tracked_local_overrides_in_root_and_nested_directories(
        self,
    ) -> None:
        self.run_git("init", "--quiet")
        self.write(".gitignore", "personal/\n")
        self.write("CLAUDE.local.md", "# Shared override\n")
        self.write("module with space/CLAUDE.local.md", "# Nested override\n")
        self.write("personal/CLAUDE.local.md", "# Ignored override\n")
        self.run_git("add", "CLAUDE.local.md", "module with space/CLAUDE.local.md")
        errors: list[str] = []
        harness.check_tracked_claude_instructions(errors)
        assert len(errors) == 2
        assert any(error.endswith(": CLAUDE.local.md") for error in errors)
        assert any("module with space/CLAUDE.local.md" in error for error in errors)

        self.run_git("add", "--force", "personal/CLAUDE.local.md")
        errors = []
        harness.check_tracked_claude_instructions(errors)
        assert len(errors) == 3
        assert any("personal/CLAUDE.local.md" in error for error in errors)

    def test_allows_untracked_and_ignored_personal_overrides(self) -> None:
        self.run_git("init", "--quiet")
        self.write(".gitignore", "personal/\n")
        self.write("CLAUDE.local.md", "# Untracked personal override\n")
        self.write("personal/CLAUDE.local.md", "# Ignored personal override\n")
        errors: list[str] = []
        harness.check_instruction_files(errors)
        harness.check_tracked_claude_instructions(errors)
        assert errors == []

    def test_claude_files_are_rejected_only_when_tracked(self) -> None:
        self.run_git("init", "--quiet")
        self.write(".gitignore", ".claude/\n")
        self.write("CLAUDE.md", "# Untracked personal instructions\n")
        self.write(".claude/CLAUDE.md", "# Ignored personal instructions\n")
        errors: list[str] = []
        harness.check_instruction_files(errors)
        harness.check_tracked_claude_instructions(errors)
        assert errors == []

        self.run_git("add", "CLAUDE.md")
        self.run_git("add", "--force", ".claude/CLAUDE.md")
        harness.check_tracked_claude_instructions(errors)
        assert len(errors) == 2
        assert any(error.endswith(": CLAUDE.md") for error in errors)
        assert any(error.endswith(": .claude/CLAUDE.md") for error in errors)

    def test_reports_failure_to_enumerate_tracked_overrides(self) -> None:
        with patch.object(
            harness.subprocess, "run", side_effect=OSError("git missing")
        ):
            errors: list[str] = []
            harness.check_tracked_claude_instructions(errors)
        assert len(errors) == 1
        assert "Unable to enumerate tracked Claude instructions" in errors[0]

    def test_accepts_concise_manual_module_with_local_headings(self) -> None:
        self.write("AGENTS.md", "# Shared rules\n\nKeep secrets out of source.\n")
        self.write(
            "module/AGENTS.md",
            "# Module\n\n## Constraints\n\nPreserve the public payload.\n",
        )
        errors: list[str] = []
        harness.check_instruction_files(errors)
        assert errors == []

    def test_rejects_generated_marker_and_empty_instructions(self) -> None:
        self.write("module/AGENTS.md", harness.RETIRED_GENERATED_MARKER + " -->\n")
        self.write("empty/AGENTS.md", "\n")
        errors: list[str] = []
        harness.check_instruction_files(errors)
        assert len(errors) == 2
        assert any("hand-maintained" in error for error in errors)
        assert any("Empty instruction" in error for error in errors)

    def test_skips_dependency_instruction_trees(self) -> None:
        self.write("node_modules/package/AGENTS.md", harness.RETIRED_GENERATED_MARKER)
        self.write(".venv/package/AGENTS.md", harness.RETIRED_GENERATED_MARKER)
        errors: list[str] = []
        harness.check_instruction_files(errors)
        assert errors == []

    def test_validates_relative_and_rooted_links_without_fetching_urls(self) -> None:
        self.write("docs/reference.md", "# Reference\n")
        self.write("docs/with space.md", "# Reference\n")
        self.write(
            "module/AGENTS.md",
            "# Module\n"
            "[Relative](../docs/reference.md#scope)\n"
            "[Rooted](/docs/reference.md)\n"
            "[Encoded](../docs/with%20space.md)\n"
            "[Web](https://example.com/missing)\n"
            "[Heading](#scope)\n"
            "[Missing](../docs/deleted.md)\n",
        )
        errors: list[str] = []
        harness.check_instruction_files(errors)
        assert len(errors) == 1
        assert "Broken instruction link '../docs/deleted.md'" in errors[0]

    def test_rejects_links_that_escape_through_parents_or_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "rules.md"
            external.write_text("# External rules\n", encoding="utf-8")
            (self.root / "external.md").symlink_to(external)
            self.write("docs/reference.md", "# Reference\n")
            (self.root / "internal.md").symlink_to("docs/reference.md")
            self.write(
                "module/AGENTS.md",
                "# Module\n"
                f"[Parents](../../{Path(outside).name}/rules.md)\n"
                f"[Encoded](%2e%2e/%2e%2e/{Path(outside).name}/rules.md)\n"
                "[External symlink](../external.md)\n"
                "[Internal symlink](../internal.md)\n",
            )
            errors: list[str] = []
            harness.check_instruction_files(errors)
        assert len(errors) == 3
        assert all("leaves the repository" in error for error in errors)

    def test_requires_shared_guardrails_and_primary_entry_points(self) -> None:
        agent = self.write(
            "AGENTS.md",
            "# Root\n" + "\n".join(f"## {h}" for h in harness.REQUIRED_HEADINGS),
        )
        missing = self.root / "scripts/AGENTS.md"
        with patch.object(
            harness, "MANUAL_AGENTS", {agent: ("required guardrail",), missing: ()}
        ):
            errors: list[str] = []
            harness.check_manual_agents(errors)
        assert len(errors) == 2
        assert any("required guardrail" in error for error in errors)
        assert any("Missing manual AGENTS" in error for error in errors)

    def test_accepts_minimal_copilot_pointer_and_gemini_symlink(self) -> None:
        self.write("AGENTS.md", "# Root\n")
        self.write(
            ".github/copilot-instructions.md",
            "Read [root instructions](../AGENTS.md), then the nearest AGENTS.md.\n",
        )
        (self.root / "GEMINI.md").symlink_to("AGENTS.md")
        errors: list[str] = []
        harness.check_compatibility_entry_points(errors)
        assert errors == []

    def test_rejects_missing_pointer_and_gemini_copy(self) -> None:
        self.write("AGENTS.md", "# Root\n")
        self.write("GEMINI.md", "# Root\n")
        errors: list[str] = []
        harness.check_compatibility_entry_points(errors)
        assert len(errors) == 2
        assert any("Missing Copilot" in error for error in errors)
        assert any("GEMINI.md must link" in error for error in errors)


if __name__ == "__main__":
    unittest.main()

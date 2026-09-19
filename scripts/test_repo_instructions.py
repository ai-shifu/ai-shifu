#!/usr/bin/env python3
"""Exercise instruction validation independently of the retired generator."""

from __future__ import annotations

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

    def test_rejects_nested_claude_files_but_skips_dependency_trees(self) -> None:
        self.write("module/.claude/CLAUDE.md", "# Retired wrapper\n")
        self.write("node_modules/package/CLAUDE.md", "# Vendor instructions\n")
        self.write(".venv/package/AGENTS.md", harness.RETIRED_GENERATED_MARKER)
        errors: list[str] = []
        harness.check_instruction_files(errors)
        assert len(errors) == 1
        assert "module/.claude/CLAUDE.md" in errors[0]

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

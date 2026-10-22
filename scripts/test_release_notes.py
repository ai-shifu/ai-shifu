# ruff: noqa: INP001 -- Standalone release notes regression tests.
"""Exercise frozen release notes with the real pinned Commitizen and local Git."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path

import release_notes as notes


class FrozenCommitizenNotes(unittest.TestCase):
    """Keep commit bodies and candidate boundaries without external lookups."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.config = self.repo / "cz.json"
        self.config.write_text(
            json.dumps(
                {
                    "commitizen": {
                        "name": "cz_conventional_commits",
                        "tag_format": "v$major.$minor.$patch",
                        "version_provider": "scm",
                    }
                }
            ),
            encoding="utf-8",
        )
        self.change = self.repo / "changed.txt"
        self.change.write_text("baseline\n", encoding="utf-8")
        self.commit("feat: baseline feature")
        self.git("tag", "v3.0.0")

    def git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self, message: str) -> str:
        self.git("add", ".")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def test_pinned_commitizen_retains_breaking_body_at_frozen_source(self) -> None:
        """Use the shipped CLI, even when the current checkout has newer config."""
        installed = subprocess.run(
            ["cz", "version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert installed == "4.16.2", "Install commitizen==4.16.2 for release tests"
        migration = (
            "Anonymous API access is removed; configure API_TOKEN before upgrading."
        )
        self.change.write_text("candidate\n", encoding="utf-8")
        source = self.commit(
            f"feat!: require API tokens\n\nBREAKING CHANGE: {migration}"
        )
        self.change.write_text("later\n", encoding="utf-8")
        self.config.write_text(
            '{"commitizen": {"name": "unavailable_future_plugin"}}\n',
            encoding="utf-8",
        )
        later = self.commit("feat: exclude newer main changes")
        self.git("tag", "v3.0.2")
        self.change.write_text("local unstaged edits\n", encoding="utf-8")

        for tagged in (False, True):
            with self.subTest(candidate_already_tagged=tagged):
                if tagged:
                    self.git("tag", "v3.0.1", source)
                refs = self.git("show-ref")
                status = self.git("status", "--porcelain")
                with chdir(self.repo):
                    rendered = notes.product_notes(source, "v3.0.0", "fixture/product")
                assert "### BREAKING CHANGE" in rendered
                assert migration in rendered
                assert rendered.count("- require API tokens") == 1
                assert "exclude newer main changes" not in rendered
                assert "baseline feature" not in rendered
                assert self.git("rev-parse", "HEAD") == later
                assert self.git("symbolic-ref", "--short", "HEAD") == "main"
                assert self.git("show-ref") == refs
                assert self.git("status", "--porcelain") == status
                assert (
                    self.change.read_text(encoding="utf-8") == "local unstaged edits\n"
                )
                assert not (self.repo / "CHANGELOG.md").exists()


if __name__ == "__main__":
    unittest.main()

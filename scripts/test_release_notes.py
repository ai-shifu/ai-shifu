# ruff: noqa: INP001 -- Standalone release notes regression tests.
"""Exercise frozen release notes with the real pinned Commitizen and local Git."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
import urllib.request
from contextlib import chdir
from pathlib import Path
from unittest import mock

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

    def test_same_pr_reference_does_not_hide_filtered_commit_subjects(self) -> None:
        """Real Commitizen entries cover only their own type, scope and subject."""
        covered = {
            "feat(auth): add login (#42)": "**auth**: add login (#42)",
            "feat(api): add login (#42)": "**api**: add login (#42)",
            "fix: retain sessions (#42)": "retain sessions (#42)",
        }
        omitted = (
            "chore: refresh build tooling (#42)",
            "chore(auth): add login (#42)",
            "chore(api): add login (#42)",
            "chore(other): add login (#42)",
            "refresh build tooling (#42)",
        )
        for subject in (*covered, *omitted):
            self.change.write_text(subject + "\n", encoding="utf-8")
            source = self.commit(subject)
        with (
            chdir(self.repo),
            mock.patch.dict(os.environ, {"GH_TOKEN": "fixture-credential"}),
            mock.patch.object(
                urllib.request,
                "urlopen",
                side_effect=lambda *_args, **_kwargs: io.BytesIO(
                    b'{"user": {"login": "fixture-teacher"}}'
                ),
            ) as author_http,
        ):
            rendered = notes.product_notes(source, "v3.0.0", "fixture/product")
        other_changes = rendered.partition("### Other Changes\n\n")[2].splitlines()
        for subject in omitted:
            with self.subTest(filtered_subject=subject):
                assert f"- {subject} (@fixture-teacher)" in other_changes
        for subject, entry in covered.items():
            with self.subTest(rendered_subject=subject):
                assert rendered.count(f"- {entry} (@fixture-teacher)") == 1
                assert f"- {subject} (@fixture-teacher)" not in rendered.splitlines()
        author_http.assert_called_once()
        request = author_http.call_args.args[0]
        assert (
            request.full_url == "https://api.github.com/repos/fixture/product/pulls/42"
        )

    def test_release_installation_preserves_existing_keys(self) -> None:
        """Published notes and PR previews give the same safe installation path."""
        self.change.write_text("candidate\n", encoding="utf-8")
        source = self.commit("fix: generate a private installation key")
        installation_commands = """git clone https://github.com/fixture/product.git
cd product
git checkout v3.0.1
cd docker
python3 ../scripts/prepare_env.py
# Configure a provider API key in .env and set LLM_MODEL_1_ID
# to a text model served by that provider (required; no default).
# LLM_MODEL_1_NAME is optional; an empty name displays the configured model ID.
docker compose -f docker-compose.yml -f docker-compose.secret-key.yml up -d"""

        for preview in (False, True):
            with self.subTest(pr_preview=preview):
                output = self.repo / "release-body.md"
                arguments = [
                    "release_notes.py",
                    "--source",
                    source,
                    "--version",
                    "3.0.1",
                    "--repository",
                    "fixture/product",
                    "--output",
                    str(output),
                ]
                if preview:
                    arguments.append("--pr-body")
                with (
                    chdir(self.repo),
                    mock.patch("sys.argv", arguments),
                    mock.patch.object(notes, "dependency_notes", return_value=""),
                ):
                    notes.main()
                rendered = output.read_text(encoding="utf-8")
                installation_section = rendered.split(
                    "## Installation from Source\n\n", 1
                )[1]
                installation = installation_section.split(
                    "\nExisting installations", 1
                )[0]
                assert installation_commands in installation
                assert (
                    "Python 3.10+ on a POSIX host (Linux, macOS or WSL)\n"
                    "and Docker Compose 2.24.4+" in installation
                )
                assert "include both Compose files on every" in installation
                assert (
                    "Compose command, including restarts and upgrades." in installation
                )
                assert "cp .env.example.full .env" not in rendered
                assert "docker compose up" not in rendered
                assert "secrets.token_urlsafe" not in rendered
                assert (
                    "Keep the original saved configuration and historical effective "
                    "`SECRET_KEY`." in rendered
                )
                assert (
                    "Existing pinned deployments must retain their original Compose "
                    "commands" in rendered
                )
                assert "not add `docker-compose.secret-key.yml` blindly" in rendered
                assert "before a deliberate migration." in rendered
                assert (
                    "https://github.com/fixture/product/blob/v3.0.1/"
                    "INSTALL_MANUAL.md#secret-key-preservation-and-recovery" in rendered
                )
                assert (
                    "https://github.com/fixture/product/blob/v3.0.1/"
                    "INSTALL_MANUAL.md#upgrading-to-numbered-models" in rendered
                )


if __name__ == "__main__":
    unittest.main()

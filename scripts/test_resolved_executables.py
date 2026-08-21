#!/usr/bin/env python3
# Copyright 2026 AI-Shifu
"""Verify repository tools resolve executables before starting processes."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

import check_dev_tools
import check_example_identifiers


class ResolvedExecutablesTest(unittest.TestCase):
    """Cover executable resolution and missing-tool behavior."""

    def test_dev_tools_reuses_resolved_git(self) -> None:
        """Use the resolved Git path for every hooks-directory query."""
        with (
            patch("check_dev_tools.shutil.which", return_value="/trusted/git"),
            patch("check_dev_tools.subprocess.run") as run,
        ):
            run.side_effect = [
                SimpleNamespace(returncode=1, stdout=""),
                SimpleNamespace(returncode=0, stdout=".git/hooks\n"),
            ]

            hooks_dir = vars(check_dev_tools)["_hooks_dir"]()

        assert hooks_dir == check_dev_tools.ROOT / ".git/hooks"
        assert run.call_args_list == [
            call(
                ["/trusted/git", "config", "--get", "core.hooksPath"],
                cwd=check_dev_tools.ROOT,
                capture_output=True,
                text=True,
                check=False,
            ),
            call(
                ["/trusted/git", "rev-parse", "--git-path", "hooks"],
                cwd=check_dev_tools.ROOT,
                capture_output=True,
                text=True,
                check=True,
            ),
        ]

    def test_dev_tools_handles_missing_git(self) -> None:
        """Keep the existing unavailable-hooks result when Git is absent."""
        with (
            patch("check_dev_tools.shutil.which", return_value=None),
            patch("check_dev_tools.subprocess.run") as run,
        ):
            hooks_dir = vars(check_dev_tools)["_hooks_dir"]()

        assert hooks_dir is None
        run.assert_not_called()

    def test_dev_tools_resolves_ruff_before_version_check(self) -> None:
        """Use an absolute Ruff path for the version subprocess."""
        with (
            patch("check_dev_tools.shutil.which", return_value="tools/ruff"),
            patch("check_dev_tools.subprocess.run") as run,
        ):
            run.return_value = SimpleNamespace(
                stdout=f"ruff {check_dev_tools.RUFF_VERSION}\n"
            )

            matches = vars(check_dev_tools)["_ruff_version_matches"]()

        assert matches is True
        run.assert_called_once_with(
            [str(Path("tools/ruff").resolve()), "--version"],
            cwd=check_dev_tools.ROOT,
            capture_output=True,
            text=True,
            check=True,
        )

    def test_identifier_scans_use_resolved_git(self) -> None:
        """Pass the resolved Git path to every repository inventory command."""
        with (
            patch(
                "check_example_identifiers.shutil.which",
                return_value="/trusted/git",
            ),
            patch("check_example_identifiers.subprocess.run") as run,
        ):
            run.side_effect = [
                subprocess.CompletedProcess([], 0, stdout=b"one.py\0"),
                subprocess.CompletedProcess(
                    [],
                    0,
                    stdout=b"100644 abcdef 0\tone.py\0",
                ),
                subprocess.CompletedProcess([], 0, stdout=b"abcdef blob 3\nabc\n"),
            ]

            paths = vars(check_example_identifiers)["_repository_relative_paths"]()
            entries = vars(check_example_identifiers)["_index_entries"]()
            objects = vars(check_example_identifiers)["_read_index_objects"](["abcdef"])

        assert paths == ["one.py"]
        assert entries == [("one.py", "abcdef")]
        assert objects == {"abcdef": b"abc"}
        assert [item.args[0][0] for item in run.call_args_list] == [
            "/trusted/git",
            "/trusted/git",
            "/trusted/git",
        ]

    def test_identifier_scan_reports_missing_git(self) -> None:
        """Raise an explicit missing-tool error before starting a process."""
        with patch("check_example_identifiers.shutil.which", return_value=None):
            error = _capture_missing_git_error()

        assert str(error) == "git executable not found on PATH"


def _capture_missing_git_error() -> FileNotFoundError:
    try:
        vars(check_example_identifiers)["_git_executable"]()
    except FileNotFoundError as exc:
        return exc
    message = "missing Git should fail before subprocess execution"
    raise AssertionError(message)


if __name__ == "__main__":
    unittest.main()

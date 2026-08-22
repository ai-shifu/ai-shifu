"""Verify that Ruff resolves the D213 docstring-summary rule conflict."""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SUMMARY_FIRST_SOURCE = '''"""Fixture module used to verify the D213 policy."""


def public_function() -> int:
    """Return using the formatter-compatible summary-first layout.

    Preserve a detail line so both competing multiline rules are exercised.
    """
    return 1
'''
SUMMARY_SECOND_LINE_SOURCE = '''"""Fixture module used to verify the D213 policy."""


def public_function() -> int:
    """
    Return a fixture value with a summary that starts on the second line.

    Preserve a detail line so both competing multiline rules are exercised.
    """
    return 1
'''


class RuffD213PolicyTest(unittest.TestCase):
    """Protect the D212 summary-first convention selected by this project."""

    @classmethod
    def setUpClass(cls) -> None:
        """Resolve the same Ruff executable used by local and CI checks."""
        cls.ruff = os.environ.get("RUFF_BIN") or shutil.which("ruff")
        if cls.ruff is None:
            message = "ruff is not installed"
            raise unittest.SkipTest(message)

    def run_ruff(
        self, source: str, *extra_args: str
    ) -> subprocess.CompletedProcess[str]:
        """Run configured Ruff against a docstring-summary fixture."""
        return subprocess.run(
            [
                self.ruff,
                "check",
                "--config",
                str(REPO_ROOT / "ruff.toml"),
                *extra_args,
                "--stdin-filename",
                "src/api/flaskr/docstring_summary_fixture.py",
                "-",
            ],
            cwd=REPO_ROOT,
            input=source,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_ruff_resolves_the_d212_and_d213_summary_conflict(self) -> None:
        """Keep both summary rules selected without a redundant global ignore."""
        with (REPO_ROOT / "ruff.toml").open("rb") as ruff_file:
            config = tomllib.load(ruff_file)

        ignored_codes = config["lint"]["ignore"]
        assert "D213" not in ignored_codes
        assert "D212" not in ignored_codes

        configured_result = self.run_ruff(SUMMARY_FIRST_SOURCE)
        assert configured_result.returncode == 0, (
            configured_result.stdout + configured_result.stderr
        )
        configured_output = configured_result.stdout + configured_result.stderr
        assert "D212" in configured_output
        assert "D213" in configured_output

        configured_violation_result = self.run_ruff(SUMMARY_SECOND_LINE_SOURCE)
        assert configured_violation_result.returncode == 1, (
            configured_violation_result.stdout + configured_violation_result.stderr
        )
        assert "D212" in configured_violation_result.stdout

        d213_result = self.run_ruff(SUMMARY_FIRST_SOURCE, "--select", "D213")
        assert d213_result.returncode == 1, d213_result.stdout + d213_result.stderr
        assert "D213" in d213_result.stdout

        d212_result = self.run_ruff(SUMMARY_FIRST_SOURCE, "--select", "D212")
        assert d212_result.returncode == 0, d212_result.stdout + d212_result.stderr


if __name__ == "__main__":
    unittest.main()

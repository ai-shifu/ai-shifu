"""Verify that Ruff resolves the D203 class-docstring rule conflict."""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CLASS_DOCSTRING_SOURCE = '''"""Fixture module used to verify the D203 policy."""


class Example:
    """Represent the formatter-compatible class-docstring layout."""
'''
CLASS_DOCSTRING_D211_VIOLATION_SOURCE = '''"""Fixture module used to verify the D203 policy."""


class Example:

    """Represent a class-docstring layout that D211 must reject."""
'''


class RuffD203PolicyTest(unittest.TestCase):
    """Protect the D211 class-docstring convention selected by this project."""

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
        """Run the configured Ruff policy against a class-docstring fixture."""
        return subprocess.run(
            [
                self.ruff,
                "check",
                "--config",
                str(REPO_ROOT / "ruff.toml"),
                *extra_args,
                "--stdin-filename",
                "src/api/flaskr/class_docstring_fixture.py",
                "-",
            ],
            cwd=REPO_ROOT,
            input=source,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_ruff_resolves_the_d203_and_d211_layout_conflict(self) -> None:
        """Keep both layout rules selected without a redundant global ignore."""
        with (REPO_ROOT / "ruff.toml").open("rb") as ruff_file:
            config = tomllib.load(ruff_file)

        ignored_codes = config["lint"]["ignore"]
        assert "D203" not in ignored_codes
        assert "D211" not in ignored_codes

        configured_result = self.run_ruff(CLASS_DOCSTRING_SOURCE)
        assert configured_result.returncode == 0, (
            configured_result.stdout + configured_result.stderr
        )
        configured_output = configured_result.stdout + configured_result.stderr
        assert "D203" in configured_output
        assert "D211" in configured_output

        configured_violation_result = self.run_ruff(
            CLASS_DOCSTRING_D211_VIOLATION_SOURCE
        )
        assert configured_violation_result.returncode == 1, (
            configured_violation_result.stdout + configured_violation_result.stderr
        )
        assert "D211" in configured_violation_result.stdout

        d203_result = self.run_ruff(CLASS_DOCSTRING_SOURCE, "--select", "D203")
        assert d203_result.returncode == 1, d203_result.stdout + d203_result.stderr
        assert "D203" in d203_result.stdout

        d211_result = self.run_ruff(CLASS_DOCSTRING_SOURCE, "--select", "D211")
        assert d211_result.returncode == 0, d211_result.stdout + d211_result.stderr


if __name__ == "__main__":
    unittest.main()

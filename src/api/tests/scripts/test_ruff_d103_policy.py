"""Verify the D103 public-function documentation policy boundaries."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
UNDOCUMENTED_PUBLIC_FUNCTION_SOURCE = '''"""Fixture module used to verify the D103 policy."""


def public_function() -> None:
    return None
'''


class RuffD103PolicyTest(unittest.TestCase):
    """Protect the documented public-function policy and its narrow boundaries."""

    @classmethod
    def setUpClass(cls: object) -> None:
        """Resolve the same Ruff executable used by local and CI checks."""
        cls.ruff = os.environ.get("RUFF_BIN") or shutil.which("ruff")
        if cls.ruff is None:
            message = "ruff is not installed"
            raise unittest.SkipTest(message)

    def run_ruff(self, filename: str) -> subprocess.CompletedProcess[str]:
        """Run configured Ruff against fixture source at one repository path."""
        return subprocess.run(
            [
                self.ruff,
                "check",
                "--config",
                str(REPO_ROOT / "ruff.toml"),
                "--stdin-filename",
                filename,
                "-",
            ],
            cwd=REPO_ROOT,
            input=UNDOCUMENTED_PUBLIC_FUNCTION_SOURCE,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_semantic_exception_boundaries_allow_undocumented_functions(
        self,
    ) -> None:
        """Keep D103 exceptions limited to tests, fixtures, and migration history."""
        exception_filenames = (
            "src/api/tests/docstring_fixture.py",
            "scripts/test_docstring_fixture.py",
            "src/api/migrations/versions/docstring_fixture.py",
            "scripts/testdata/architecture_boundaries/docstring_fixture.py",
        )

        for filename in exception_filenames:
            with self.subTest(filename=filename):
                result = self.run_ruff(filename)
                assert "D103" not in result.stdout, result.stdout + result.stderr

    def test_production_function_requires_a_docstring(self) -> None:
        """Keep D103 enforced for public production functions."""
        result = self.run_ruff("src/api/flaskr/documentation_fixture.py")

        assert result.returncode == 1, result.stdout + result.stderr
        assert "D103" in result.stdout


if __name__ == "__main__":
    unittest.main()

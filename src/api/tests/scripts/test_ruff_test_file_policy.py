"""Verify that RUF001 is limited to non-test Python files."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFUSABLE_SOURCE = '''"""Fixture module used to verify the RUF001 policy."""
# ruff: noqa: INP001
value = "（"
'''


class RuffTestFilePolicyTest(unittest.TestCase):
    """Protect the test-only RUF001 exemption boundary."""

    @classmethod
    def setUpClass(cls: object) -> None:
        """Resolve the same Ruff executable used by local and CI checks."""
        cls.ruff = os.environ.get("RUFF_BIN") or shutil.which("ruff")
        if cls.ruff is None:
            message = "ruff is not installed"
            raise unittest.SkipTest(message)

    def run_ruff(self, filename: str) -> subprocess.CompletedProcess[str]:
        """Run the configured Ruff policy against source at one repository path."""
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
            input=CONFUSABLE_SOURCE,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_test_module_allows_confusable_fixture_text(self) -> None:
        """Allow verbatim fixtures without an RUF001 diagnostic under test paths."""
        test_filenames = (
            "example/tests/fixture.py",
            "example/test_fixture.py",
            "example/fixture_test.py",
            "example/conftest.py",
        )

        for filename in test_filenames:
            with self.subTest(filename=filename):
                result = self.run_ruff(filename)
                assert result.returncode == 0, result.stdout + result.stderr
                assert "RUF001" not in result.stdout, result.stdout + result.stderr

    def test_production_module_still_rejects_confusable_text(self) -> None:
        """Keep RUF001 enforced outside test paths."""
        result = self.run_ruff("src/api/flaskr/confusable_fixture.py")

        assert result.returncode == 1, result.stdout + result.stderr
        assert "RUF001" in result.stdout


if __name__ == "__main__":
    unittest.main()

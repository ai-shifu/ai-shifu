"""Verify the ANN201 public-return annotation policy boundaries."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MISSING_RETURN_ANNOTATION_SOURCE = '''"""Fixture module used to verify the ANN201 policy."""
# ruff: noqa: INP001


def public_function():
    return None
'''


class RuffAnn201PolicyTest(unittest.TestCase):
    """Protect ANN201 enforcement while retaining immutable migration history."""

    @classmethod
    def setUpClass(cls) -> None:
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
            input=MISSING_RETURN_ANNOTATION_SOURCE,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_migration_history_remains_exempt(self) -> None:
        """Keep immutable Alembic revisions outside ANN201 enforcement."""
        result = self.run_ruff("src/api/migrations/versions/ann201_fixture.py")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "ANN201" not in result.stdout

    def test_production_function_requires_a_return_annotation(self) -> None:
        """Require an explicit return type for public production functions."""
        result = self.run_ruff("src/api/flaskr/ann201_fixture.py")

        assert result.returncode == 1, result.stdout + result.stderr
        assert "ANN201" in result.stdout

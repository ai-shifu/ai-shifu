#!/usr/bin/env python3
"""Tests for the Cook Web changed-files Prettier helper."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "src/cook-web/scripts/prettier-check-changed.mjs"


def run(
    command: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


class PrettierCheckChangedTest(unittest.TestCase):
    """Verify prettier check changed behavior."""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        self.cook_web = self.repo / "src/cook-web"
        (self.cook_web / "src").mkdir(parents=True)
        (self.repo / "src/api").mkdir(parents=True)

        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "test@example.com"], self.repo)
        run(["git", "config", "user.name", "Test User"], self.repo)

        (self.cook_web / "src/existing.ts").write_text("const value = 1;\n")
        (self.repo / "src/api/app.py").write_text("print('hello')\n")
        run(["git", "add", "."], self.repo)
        run(["git", "commit", "-m", "base"], self.repo)
        self.base = run(["git", "rev-parse", "HEAD"], self.repo).stdout.strip()

        self.fake_bin = self.repo / "fake-bin"
        self.fake_bin.mkdir()
        self.args_file = self.repo / "npx-args.txt"
        (self.fake_bin / "npx").write_text(
            '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$FAKE_NPX_ARGS"\nexit 0\n'
        )
        (self.fake_bin / "npx").chmod(0o755)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def script_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.fake_bin}{os.pathsep}{env['PATH']}"
        env["FAKE_NPX_ARGS"] = str(self.args_file)
        return env

    def commit_changes(self, message: str) -> str:
        run(["git", "add", "."], self.repo)
        result = run(["git", "commit", "-m", message], self.repo)
        assert result.returncode == 0, result.stderr
        return run(["git", "rev-parse", "HEAD"], self.repo).stdout.strip()

    def test_checks_only_changed_cook_web_files(self) -> None:
        (self.cook_web / "src/existing.ts").write_text("const value = 2;\n")
        (self.cook_web / "docs").mkdir()
        (self.cook_web / "docs/notes.md").write_text("# Notes\n")
        (self.repo / "src/api/app.py").write_text("print('outside cook web')\n")
        head = self.commit_changes("change cook web and backend")

        result = run(
            ["node", str(SCRIPT_PATH), "--base", self.base, "--head", head],
            self.cook_web,
            self.script_env(),
        )

        assert result.returncode == 0, result.stderr
        args = self.args_file.read_text().splitlines()
        assert args[:4] == ["prettier", "--check", "--ignore-unknown", "--"]
        assert sorted(args[4:]) == sorted(["docs/notes.md", "src/existing.ts"])

    def test_skips_prettier_when_no_cook_web_files_changed(self) -> None:
        (self.repo / "src/api/app.py").write_text("print('outside only')\n")
        head = self.commit_changes("change backend only")

        result = run(
            ["node", str(SCRIPT_PATH), "--base", self.base, "--head", head],
            self.cook_web,
            self.script_env(),
        )

        assert result.returncode == 0, result.stderr
        assert not self.args_file.exists()
        assert "No changed Cook Web files" in result.stdout


if __name__ == "__main__":
    unittest.main()

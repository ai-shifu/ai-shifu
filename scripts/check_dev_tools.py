#!/usr/bin/env python3
"""Doctor for the local lefthook toolchain.

The repository runs its pre-commit / commit-msg checks through lefthook. Those
git hooks only fire after ``lefthook install`` has wired them into
``.git/hooks``, and even then each hook shells out to tools that must already be
on ``PATH`` (ruff, commitizen, the pre-commit-hooks console scripts, and the
Cook Web prettier binary). If lefthook or any of those tools is missing the
local checks are silently skipped or fail with a cryptic ``command not found``.

Run this from the repository root before committing to find what is missing and
exactly how to install it::

    python scripts/check_dev_tools.py

Exit status:
    0  every required tool is present (Cook Web gaps are warnings by default)
    1  a required tool, or the installed git hook, is missing

Pass ``--strict`` to also fail when Cook Web (frontend) tooling is missing.

NOTE: the pinned versions in the install hints below mirror ``lefthook.yml``'s
header (the single source of truth). Keep them in sync when a tool is bumped
there.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Install hints. Versions mirror lefthook.yml's header comment (lines 10-13).
BREW_INSTALL = "brew install lefthook"
PIP_INSTALL = "pip install ruff==0.15.13 commitizen==4.16.2 pre-commit-hooks==6.0.0"
NPM_INSTALL = "cd src/cook-web && npm ci"
LEFTHOOK_INSTALL = "lefthook install"
NODE_INSTALL = "install Node.js (see INSTALL_MANUAL.md for the supported version)"

# Console scripts provided by the pre-commit-hooks pip package and invoked by
# lefthook.yml's pre-commit hook.
PRE_COMMIT_HOOKS_SCRIPTS = (
    "check-yaml",
    "check-json",
    "check-merge-conflict",
    "check-symlinks",
    "end-of-file-fixer",
    "trailing-whitespace-fixer",
    "pretty-format-json",
    "requirements-txt-fixer",
)

# Cook Web prettier is installed locally, not on PATH (see lefthook.yml).
COOK_WEB_PRETTIER = ROOT / "src" / "cook-web" / "node_modules" / ".bin" / "prettier"


class Check:
    """A single tool/state check and the command that fixes it."""

    def __init__(self, name: str, ok: bool, fix: str, *, required: bool = True):
        self.name = name
        self.ok = ok
        self.fix = fix
        self.required = required


def _hooks_dir() -> Path | None:
    """Return the directory git uses for hooks, honoring core.hooksPath."""
    try:
        configured = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if configured.returncode == 0 and configured.stdout.strip():
            # git config values may use ~ / ~user; Path() does not expand it.
            path = Path(configured.stdout.strip()).expanduser()
            return path if path.is_absolute() else (ROOT / path)

        resolved = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        path = Path(resolved.stdout.strip())
        return path if path.is_absolute() else (ROOT / path)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _lefthook_hook_installed() -> bool:
    """True when ``lefthook install`` has wired the pre-commit hook in."""
    hooks_dir = _hooks_dir()
    if hooks_dir is None:
        return False
    pre_commit = hooks_dir / "pre-commit"
    if not pre_commit.is_file():
        return False
    try:
        return "lefthook" in pre_commit.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def collect_checks() -> tuple[list[Check], list[Check]]:
    """Return (core_checks, frontend_checks)."""
    lefthook_present = shutil.which("lefthook") is not None

    core: list[Check] = [
        Check("lefthook", lefthook_present, BREW_INSTALL),
        # Only meaningful once the binary exists; surface the install step
        # regardless so a half-finished setup is obvious.
        Check(
            "lefthook git hooks (lefthook install)",
            lefthook_present and _lefthook_hook_installed(),
            LEFTHOOK_INSTALL,
        ),
        Check("ruff", shutil.which("ruff") is not None, PIP_INSTALL),
        Check("cz (commitizen)", shutil.which("cz") is not None, PIP_INSTALL),
    ]
    for script in PRE_COMMIT_HOOKS_SCRIPTS:
        core.append(Check(script, shutil.which(script) is not None, PIP_INSTALL))

    frontend: list[Check] = [
        Check("node", shutil.which("node") is not None, NODE_INSTALL, required=False),
        Check("npm", shutil.which("npm") is not None, NODE_INSTALL, required=False),
        Check(
            "Cook Web prettier (node_modules)",
            COOK_WEB_PRETTIER.is_file(),
            NPM_INSTALL,
            required=False,
        ),
    ]
    return core, frontend


def _report(title: str, checks: list[Check]) -> None:
    print(title)
    for check in checks:
        mark = "OK  " if check.ok else "MISS"
        print(f"  [{mark}] {check.name}")


def _fix_lines(missing: list[Check]) -> list[str]:
    """Unique fix commands, preserving first-seen order."""
    seen: list[str] = []
    for check in missing:
        if check.fix not in seen:
            seen.append(check.fix)
    return seen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat missing Cook Web (frontend) tooling as a failure too",
    )
    args = parser.parse_args()

    core, frontend = collect_checks()

    _report("Core lefthook toolchain:", core)
    print()
    _report("Cook Web (frontend) toolchain:", frontend)
    print()

    missing_core = [c for c in core if not c.ok]
    missing_frontend = [c for c in frontend if not c.ok]

    if missing_core:
        print("Missing required tooling. Install with:")
        for line in _fix_lines(missing_core):
            print(f"  {line}")
        print()

    if missing_frontend:
        label = (
            "Missing Cook Web tooling"
            if args.strict
            else (
                "Cook Web tooling missing (warning; needed before committing "
                "frontend changes)"
            )
        )
        print(f"{label}. Install with:")
        for line in _fix_lines(missing_frontend):
            print(f"  {line}")
        print()

    failed = bool(missing_core) or (bool(missing_frontend) and args.strict)
    if failed:
        print("Dev tooling check FAILED. See the commands above.")
        return 1

    if missing_frontend:
        print("Core tooling OK (Cook Web gaps reported as warnings).")
    else:
        print("All dev tooling present. Local lefthook checks will run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

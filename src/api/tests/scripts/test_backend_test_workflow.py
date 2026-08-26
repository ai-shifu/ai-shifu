"""Exercise backend CI target selection and the resulting pytest command."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/backend-tests.yml"


def _workflow_script(step_name: str) -> str:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return next(
        step["run"]
        for step in workflow["jobs"]["backend-tests"]["steps"]
        if step["name"] == step_name
    )


def _select_targets(changed_paths: list[str], tmp_path: Path) -> dict[str, str]:
    # Execute the actual selector, substituting only the git diff output.
    selector = _workflow_script("Select test targets (PR only)")
    selector = selector.removeprefix("python - <<'PY'\n").removesuffix("PY\n")
    selector_file = tmp_path / "selector.py"
    selector_file.write_text(selector, encoding="utf-8")
    changed = "\n".join(changed_paths)
    script = textwrap.dedent(
        f"""\
        import runpy
        from unittest.mock import patch
        with patch("subprocess.check_output", return_value={changed!r}):
            runpy.run_path({str(selector_file)!r}, run_name="__main__")
        """
    )
    env_file = tmp_path / "github_env"
    summary_file = tmp_path / "github_summary"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "BASE_SHA": "base",
            "HEAD_SHA": "head",
            "GITHUB_ENV": str(env_file),
            "GITHUB_STEP_SUMMARY": str(summary_file),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return dict(
        line.split("=", 1) for line in env_file.read_text(encoding="utf-8").splitlines()
    )


@pytest.mark.parametrize(
    ("changed_paths", "expected_targets", "expected_flag"),
    [
        (
            ["src/api/migrations/versions/new_revision.py"],
            "tests",
            "--testmon-noselect",
        ),
        (["src/api/requirements.txt"], "tests", "--testmon-noselect"),
        (["src/api/requirements-ci.txt"], "tests", "--testmon-noselect"),
        (["src/api/flaskr/route/user.py"], "tests", "--testmon-noselect"),
        ([".github/workflows/backend-tests.yml"], "tests", "--testmon-noselect"),
        (
            [
                "src/api/flaskr/service/billing/models.py",
                "src/api/migrations/versions/new_revision.py",
            ],
            "tests",
            "--testmon-noselect",
        ),
        (
            ["src/api/flaskr/service/billing/models.py"],
            "tests/service/billing",
            "--testmon",
        ),
        (
            [
                "src/api/flaskr/service/billing/models.py",
                "src/api/flaskr/service/order/funs.py",
            ],
            "tests/service/billing tests/service/order",
            "--testmon",
        ),
        (
            ["src/api/tests/migrations/test_fresh_mysql_upgrade.py"],
            "tests/migrations/test_fresh_mysql_upgrade.py",
            "--testmon",
        ),
    ],
)
def test_pr_changes_select_the_required_pytest_mode(
    changed_paths: list[str],
    expected_targets: str,
    expected_flag: str,
    tmp_path: Path,
) -> None:
    selection = _select_targets(changed_paths, tmp_path)
    assert selection["SKIP_BACKEND_TESTS"] == "0"
    assert selection["TEST_TARGETS"] == expected_targets

    # Capture argv from the actual shell step without running the suite recursively.
    runner = "python() { printf '%s\\n' \"$@\"; }\n" + _workflow_script(
        "Run tests (PR)"
    )
    result = subprocess.run(
        ["bash", "-c", runner],
        env={**os.environ, **selection},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == [
        "-m",
        "pytest",
        expected_flag,
        *expected_targets.split(),
    ]


def test_pr_control_plane_only_changes_still_skip_backend_tests(tmp_path: Path) -> None:
    selection = _select_targets(["src/api/AGENTS.md"], tmp_path)

    assert selection["SKIP_BACKEND_TESTS"] == "1"
    assert selection["TEST_TARGETS"] == ""

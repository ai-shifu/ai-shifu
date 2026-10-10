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
            ["src/api/tests/service/removed/test_deleted_coverage.py"],
            "tests",
            "--testmon-noselect",
        ),
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
        "-n",
        "2",
        "--dist",
        "loadfile",
        expected_flag,
        *expected_targets.split(),
    ]


def test_pr_control_plane_only_changes_still_skip_backend_tests(tmp_path: Path) -> None:
    selection = _select_targets(["src/api/AGENTS.md"], tmp_path)

    assert selection["SKIP_BACKEND_TESTS"] == "1"
    assert selection["TEST_TARGETS"] == ""


def test_parallel_testmon_collects_dependencies_and_selects_only_changed_code(
    tmp_path: Path,
) -> None:
    pytest.importorskip("testmon", reason="Install requirements-ci.txt for testmon.")
    pytest.importorskip(
        "xdist", reason="Install requirements-ci.txt for parallel tests."
    )
    for name in ("alpha", "beta"):
        (tmp_path / f"{name}.py").write_text(
            "def value():\n    return 1\n", encoding="utf-8"
        )
        (tmp_path / f"test_{name}.py").write_text(
            "from pathlib import Path\n"
            f"from {name} import value\n"
            "def test_value(worker_id):\n"
            "    assert value() > 0\n"
            f"    Path('executed-{name}.txt').write_text(worker_id)\n",
            encoding="utf-8",
        )

    def run_tests() -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-n",
                "2",
                "--dist",
                "loadfile",
                "--testmon",
            ],
            cwd=tmp_path,
            env={
                **{
                    key: value
                    for key, value in os.environ.items()
                    if not key.startswith("COVERAGE_")
                },
                "TESTMON_DATAFILE": str(tmp_path / ".testmondata"),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    run_tests()
    assert {
        (tmp_path / f"executed-{name}.txt").read_text(encoding="utf-8")
        for name in ("alpha", "beta")
    } == {"gw0", "gw1"}
    for marker in tmp_path.glob("executed-*.txt"):
        marker.unlink()

    run_tests()
    assert list(tmp_path.glob("executed-*.txt")) == []

    (tmp_path / "alpha.py").write_text(
        "def value():\n    return 200\n", encoding="utf-8"
    )
    run_tests()
    assert (tmp_path / "executed-alpha.txt").is_file()
    assert not (tmp_path / "executed-beta.txt").exists()


def test_full_coverage_is_manual_only_and_respects_cancellation() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    coverage = next(
        step
        for step in workflow["jobs"]["backend-tests"]["steps"]
        if step.get("id") == "coverage"
    )
    # Manual coverage still runs after a contract failure, but ordinary PR/main
    # checks must not pay for a second full-suite run.
    assert coverage["if"] == (
        "always() && !cancelled() && github.event_name == 'workflow_dispatch' "
        "&& steps.backend-changes.outputs.run == 'true'"
    )


def test_main_still_runs_all_tests_without_coverage() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    main_tests = next(
        step
        for step in workflow["jobs"]["backend-tests"]["steps"]
        if step["name"] == "Run tests (main)"
    )
    assert main_tests["if"] == (
        "github.event_name == 'push' && steps.backend-changes.outputs.run == 'true'"
    )
    assert main_tests["working-directory"] == "src/api"
    assert main_tests["run"] == (
        "python -m pytest -n 2 --dist loadfile --testmon-noselect tests"
    )


def test_contract_tests_use_the_same_two_workers() -> None:
    assert _workflow_script("Run contract tests") == (
        "python -m pytest -n 2 --dist loadfile tests/contract -v --tb=short"
    )


def test_coverage_artifact_keeps_raw_data_and_reports_even_after_gate_failure() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    artifact = next(
        step
        for step in workflow["jobs"]["backend-tests"]["steps"]
        if step["name"] == "Upload backend coverage evidence"
    )
    assert artifact["uses"] == "actions/upload-artifact@v4"
    assert artifact["with"]["include-hidden-files"] is True
    assert artifact["with"]["path"].splitlines() == [
        "src/api/.coverage",
        "src/api/coverage.json",
        "src/api/coverage.xml",
        "src/api/coverage-summary.txt",
    ]
    assert artifact["if"] == (
        "always() && steps.coverage.outcome != 'skipped' && steps.coverage.outcome != ''"
    )


@pytest.mark.parametrize(
    ("test_status", "coverage_status", "expected_status"),
    [(0, 0, 0), (0, 2, 2), (1, 0, 1), (1, 2, 1)],
)
def test_full_coverage_runs_all_tests_and_preserves_both_failure_gates(
    tmp_path: Path, test_status: int, coverage_status: int, expected_status: int
) -> None:
    # Run the workflow's actual shell with a recording Python stub. Both kinds
    # of failure must retain reports, and a failed suite must never be masked.
    stub = r"""
python() {
  printf '%s\n' "$*" >> "$COMMAND_LOG"
  local test_command="-m pytest -n 2 --dist loadfile -p no:testmon"
  test_command+=" --cov --cov-config=.coveragerc --cov-report= --cov-fail-under=0 tests"
  if [[ "$*" == "$test_command" ]]; then
    return "$TEST_STATUS"
  fi
  if [[ "$*" == "-m coverage report -m" ]]; then
    printf 'coverage summary\n'
    return "$COVERAGE_STATUS"
  fi
}
"""
    log = tmp_path / "commands.txt"
    summary = tmp_path / "summary.txt"
    result = subprocess.run(
        ["bash", "-e", "-c", stub + _workflow_script("Run full backend coverage")],
        cwd=tmp_path,
        env={
            **os.environ,
            "COMMAND_LOG": str(log),
            "GITHUB_STEP_SUMMARY": str(summary),
            "TEST_STATUS": str(test_status),
            "COVERAGE_STATUS": str(coverage_status),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_status, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "-m coverage erase",
        "-m pytest -n 2 --dist loadfile -p no:testmon --cov "
        "--cov-config=.coveragerc --cov-report= --cov-fail-under=0 tests",
        "-m coverage json --fail-under=0",
        "-m coverage xml --fail-under=0",
        "-m coverage report -m",
    ]
    assert summary.read_text(encoding="utf-8") == "coverage summary\n"

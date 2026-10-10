"""Verify coverage scope and strict threshold using real instrumented programs."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CONFIG = Path(__file__).resolve().parents[2] / ".coveragerc"


def _coverage(directory: Path, *args: str) -> subprocess.CompletedProcess:
    pytest.importorskip(
        "coverage", reason="Install requirements-ci.txt to run coverage contract tests."
    )
    return subprocess.run(
        [sys.executable, "-m", "coverage", *args],
        cwd=directory,
        env={
            key: value
            for key, value in os.environ.items()
            if not key.startswith("COVERAGE_")
        },
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(("covered", "expected_exit"), [(95, 2), (96, 0)])
def test_statement_gate_rejects_exactly_95_percent_and_accepts_more(
    tmp_path: Path, covered: int, expected_exit: int
) -> None:
    shutil.copyfile(CONFIG, tmp_path / ".coveragerc")
    # The function declaration runs but its body does not: exactly 100 measured
    # statements, with the parameter controlling the executed statement count.
    (tmp_path / "app.py").write_text(
        "value = 1\n" * (covered - 1)
        + "def unused():\n"
        + "    value = 2\n" * (100 - covered),
        encoding="utf-8",
    )
    run = _coverage(tmp_path, "run", "app.py")
    assert run.returncode == 0, run.stderr
    report = _coverage(tmp_path, "report")
    assert report.returncode == expected_exit, report.stdout + report.stderr
    assert _coverage(tmp_path, "json", "--fail-under=0").returncode == 0
    summary = json.loads((tmp_path / "coverage.json").read_text(encoding="utf-8"))[
        "totals"
    ]
    assert summary["covered_lines"] == covered
    assert summary["num_statements"] == 100


def test_application_denominator_includes_unimported_modules_and_excludes_tests(
    tmp_path: Path,
) -> None:
    shutil.copyfile(CONFIG, tmp_path / ".coveragerc")
    package = tmp_path / "flaskr"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "unused.py").write_text("value = 42\n", encoding="utf-8")
    # The real flaskr/service tree is a namespace package without __init__.py.
    # Its unimported modules must count even when no test discovers them.
    namespace = package / "service"
    namespace.mkdir()
    (namespace / "unimported.py").write_text("value = 99\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "celery_app.py").write_text("value = 2\n", encoding="utf-8")
    (tmp_path / "gunicorn.conf.py").write_text(
        "preload_app = True\ndef post_fork():\n    value = 3\n", encoding="utf-8"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "helper.py").write_text("value = 1\n" * 100, encoding="utf-8")
    (tmp_path / "runner.py").write_text(
        # Coverage's directory discovery skips dotted filenames. The mandatory
        # Gunicorn tests load the actual config with runpy, as deployment does.
        "import app\nimport tests.helper\nimport runpy\n"
        "runpy.run_path('gunicorn.conf.py')\n",
        encoding="utf-8",
    )
    assert _coverage(tmp_path, "run", "runner.py").returncode == 0
    assert _coverage(tmp_path, "json", "--fail-under=0").returncode == 0
    report = json.loads((tmp_path / "coverage.json").read_text(encoding="utf-8"))
    assert set(report["files"]) == {
        "app.py",
        "celery_app.py",
        "gunicorn.conf.py",
        "flaskr/__init__.py",
        "flaskr/unused.py",
        "flaskr/service/unimported.py",
    }
    assert report["files"]["flaskr/unused.py"]["summary"]["covered_lines"] == 0
    assert report["files"]["celery_app.py"]["summary"]["covered_lines"] == 0
    assert report["files"]["gunicorn.conf.py"]["summary"]["covered_lines"] == 2
    assert report["files"]["gunicorn.conf.py"]["missing_lines"] == [3]
    assert (
        report["files"]["flaskr/service/unimported.py"]["summary"]["covered_lines"] == 0
    )
    assert report["totals"]["covered_lines"] == 3
    assert report["totals"]["num_statements"] == 7


def test_parallel_coverage_combines_both_workers_and_preserves_the_gate(
    tmp_path: Path,
) -> None:
    pytest.importorskip(
        "pytest_cov", reason="Install requirements-ci.txt for coverage."
    )
    pytest.importorskip(
        "xdist", reason="Install requirements-ci.txt for parallel tests."
    )
    shutil.copyfile(CONFIG, tmp_path / ".coveragerc")
    package = tmp_path / "flaskr"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "unimported.py").write_text("value = 99\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    for name in ("alpha", "beta"):
        (package / f"{name}.py").write_text(
            f"def value():\n    return {name!r}\n", encoding="utf-8"
        )
        (tests / f"test_{name}.py").write_text(
            "from pathlib import Path\n"
            f"from flaskr.{name} import value\n"
            "def test_value(worker_id):\n"
            f"    assert value() == {name!r}\n"
            f"    Path('worker-{name}.txt').write_text(worker_id)\n",
            encoding="utf-8",
        )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-n",
            "2",
            "--dist",
            "loadfile",
            "-p",
            "no:testmon",
            "--cov",
            "--cov-config=.coveragerc",
            "--cov-report=",
            "--cov-fail-under=0",
            "tests",
        ],
        cwd=tmp_path,
        env={
            key: value
            for key, value in os.environ.items()
            if not key.startswith("COVERAGE_")
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert {
        (tmp_path / f"worker-{name}.txt").read_text(encoding="utf-8")
        for name in ("alpha", "beta")
    } == {"gw0", "gw1"}
    assert _coverage(tmp_path, "json", "--fail-under=0").returncode == 0
    report = json.loads((tmp_path / "coverage.json").read_text(encoding="utf-8"))
    for name in ("alpha", "beta"):
        assert report["files"][f"flaskr/{name}.py"]["summary"]["covered_lines"] == 2
    assert report["files"]["flaskr/unimported.py"]["summary"]["covered_lines"] == 0
    assert report["totals"]["covered_lines"] == 4
    assert report["totals"]["num_statements"] == 5
    # Worker collection succeeds, then the single combined report enforces 95.01%.
    assert _coverage(tmp_path, "report").returncode == 2

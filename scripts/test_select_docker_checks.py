#!/usr/bin/env python3
"""Protect service selection and real PR diff semantics for packaging checks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from select_docker_checks import changed_paths, select_services

SCRIPT_PATH = Path(__file__).with_name("select_docker_checks.py")


def git(repo: Path, *arguments: str) -> str:
    """Run fixture Git commands and retain failures as actionable test output."""
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_file(repo: Path, path: str, content: str = "fixture\n") -> None:
    """Write a fixture input without requiring its parent directories to exist."""
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def commit(repo: Path, message: str) -> str:
    """Snapshot all fixture changes and return the exact commit SHA."""
    git(repo, "add", ".")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Create an isolated repository so diff behavior is exercised by Git."""
    repo = tmp_path / "repository"
    repo.mkdir()
    git(repo, "init", "--initial-branch=main")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.com")
    write_file(repo, "README.md")
    commit(repo, "initial fixture")
    return repo


def invoke(
    repo: Path, output: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """Invoke the public CLI from a fixture repository, rather than test internals."""
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--output", str(output), *arguments],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def selected_output(output: Path) -> tuple[str, list[str]]:
    """Decode the workflow contract while asserting a single-line compact matrix."""
    lines = output.read_text().splitlines()
    run_line, matrix_line = lines[-2:]
    assert matrix_line.startswith("matrix=")
    matrix_text = matrix_line.removeprefix("matrix=")
    matrix = json.loads(matrix_text)
    assert matrix_text == json.dumps(matrix, separators=(",", ":"))
    assert set(matrix) == {"include"}
    for image in matrix["include"]:
        service = image["service"]
        assert image == {
            "service": service,
            "image-name": f"ai-shifu-{service}",
            "dockerfile": f"src/{service}/Dockerfile",
        }
    return run_line, [image["service"] for image in matrix["include"]]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/api/Dockerfile", {"api"}),
        ("src/api/requirements.txt", {"api"}),
        ("src/web/Dockerfile", {"web"}),
        ("src/web/package.json", {"web"}),
        ("src/web/package-lock.json", {"web"}),
        ("src/web/.npmrc", {"web"}),
        ("src/web/next.config.js", {"web"}),
        ("src/web/next.config.mjs", {"web"}),
        ("src/web/next.config.ts", {"web"}),
        ("src/web/scripts/check-production-dependencies.mjs", {"web"}),
        (".dockerignore", {"api", "web"}),
        (".github/workflows/build-latest.yml", {"api", "web"}),
        (".github/workflows/build-on-release.yml", {"api", "web"}),
        (".github/workflows/build-docker-image.yml", {"api", "web"}),
        (".github/workflows/docker-build-check.yml", {"api", "web"}),
        (".github/workflows/runtime-harness.yml", {"api", "web"}),
        (".github/workflows/prepare-release.yml", {"api", "web"}),
        (".github/actions/docker-image-metadata/action.yml", {"api", "web"}),
        ("docker/docker-compose.latest.yml", {"api", "web"}),
        ("docker/docker-compose.runtime-harness.yml", {"api", "web"}),
        ("scripts/merge_docker_manifests.py", {"api", "web"}),
        ("scripts/test_merge_docker_manifests.py", {"api", "web"}),
        ("scripts/check_docker_image.py", {"api", "web"}),
        ("scripts/test_check_docker_image.py", {"api", "web"}),
        ("scripts/test_docker_image_metadata.py", {"api", "web"}),
        ("scripts/select_docker_checks.py", {"api", "web"}),
        ("scripts/test_select_docker_checks.py", {"api", "web"}),
        ("scripts/test_runtime_packaging.py", {"api", "web"}),
    ],
)
def test_packaging_inputs_select_affected_services(
    path: str, expected: set[str]
) -> None:
    assert select_services([path]) == expected


def test_application_code_and_nonproduction_inputs_need_no_extra_architecture() -> None:
    assert (
        select_services(
            [
                "src/api/app.py",
                "src/api/flaskr/service/shifu/route.py",
                "src/api/tests/service/test_route.py",
                "src/api/requirements-ci.txt",
                "src/api/docs/production.md",
                "src/web/src/components/ShifuSetting.tsx",
                "src/web/src/components/ShifuSetting.test.tsx",
                "src/web/README.md",
                "src/web/docs/next.config.mjs",
                "src/i18n/zh-CN/shifu-setting.json",
                "docs/references/docker-image-publication.md",
            ]
        )
        == set()
    )


def test_two_service_inputs_select_both_services() -> None:
    assert select_services(["src/api/requirements.txt", "src/web/.npmrc"]) == {
        "api",
        "web",
    }


def test_three_dot_diff_ignores_new_base_only_changes(
    repository: Path, tmp_path: Path
) -> None:
    git(repository, "checkout", "-b", "feature")
    write_file(repository, "src/web/package.json")
    head = commit(repository, "change web dependency")
    git(repository, "checkout", "main")
    write_file(repository, "src/api/requirements.txt")
    base = commit(repository, "advance main with API dependency")
    output = tmp_path / "github-output"
    result = invoke(
        repository,
        output,
        "--event",
        "pull_request",
        "--base-sha",
        base,
        "--head-sha",
        head,
    )
    assert result.returncode == 0, result.stderr
    assert selected_output(output) == ("run=true", ["web"])


@pytest.mark.parametrize("change", ["delete", "rename-away", "rename-in"])
def test_deleted_and_renamed_packaging_inputs_still_select_service(
    repository: Path, tmp_path: Path, change: str
) -> None:
    source = "src/api/Dockerfile" if change != "rename-in" else "docs/old.txt"
    write_file(repository, source)
    base = commit(repository, "add original input")
    if change == "delete":
        git(repository, "rm", source)
    else:
        target = "docs/moved.txt" if change == "rename-away" else "src/api/Dockerfile"
        (repository / target).parent.mkdir(parents=True, exist_ok=True)
        git(repository, "mv", source, target)
    head = commit(repository, "move or delete input")
    output = tmp_path / "github-output"
    result = invoke(
        repository,
        output,
        "--event",
        "pull_request",
        "--base-sha",
        base,
        "--head-sha",
        head,
    )
    assert result.returncode == 0, result.stderr
    assert selected_output(output) == ("run=true", ["api"])


def test_nul_diff_handles_unusual_names_and_untracked_code_is_not_executed(
    repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = git(repository, "rev-parse", "HEAD")
    write_file(repository, "docs/space and\nnewline.txt")
    write_file(
        repository, "src/api/flaskr/service/changed.py", "raise RuntimeError()\n"
    )
    write_file(repository, "scripts/select_docker_checks.py", "raise RuntimeError()\n")
    head = commit(repository, "add unusual name and executable-looking text")
    monkeypatch.chdir(repository)
    assert sorted(changed_paths(base, head)) == [
        "docs/space and\nnewline.txt",
        "scripts/select_docker_checks.py",
        "src/api/flaskr/service/changed.py",
    ]
    output = tmp_path / "github-output"
    result = invoke(
        repository,
        output,
        "--event",
        "pull_request",
        "--base-sha",
        base,
        "--head-sha",
        head,
    )
    assert result.returncode == 0, result.stderr
    assert selected_output(output) == ("run=true", ["api", "web"])


def test_application_only_pr_writes_noop_output(
    repository: Path, tmp_path: Path
) -> None:
    base = git(repository, "rev-parse", "HEAD")
    write_file(repository, "src/api/flaskr/service/changed.py")
    write_file(repository, "src/i18n/zh-CN/example.json")
    head = commit(repository, "change application and translations")
    output = tmp_path / "github-output"
    result = invoke(
        repository,
        output,
        "--event",
        "pull_request",
        "--base-sha",
        base,
        "--head-sha",
        head,
    )
    assert result.returncode == 0, result.stderr
    assert selected_output(output) == ("run=false", [])


def test_manual_run_selects_both_without_git_history(tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    output.write_text("previous=value\n")
    result = invoke(tmp_path, output, "--event", "workflow_dispatch")
    assert result.returncode == 0, result.stderr
    assert output.read_text().startswith("previous=value\n")
    assert selected_output(output) == ("run=true", ["api", "web"])


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        ("--base-sha", "a" * 40),
        ("--head-sha", "b" * 40),
        ("--base-sha", "--output=bad", "--head-sha", "b" * 40),
        ("--base-sha", "not-a-sha", "--head-sha", "b" * 40),
        ("--base-sha", "a" * 40, "--head-sha", "b" * 40),
    ],
)
def test_invalid_or_missing_pr_comparison_fails_without_skip_output(
    repository: Path, tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    output = tmp_path / "github-output"
    result = invoke(repository, output, "--event", "pull_request", *arguments)
    assert result.returncode != 0
    assert not output.exists()


def test_git_failure_propagates_outside_repository(tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    result = invoke(
        tmp_path,
        output,
        "--event",
        "pull_request",
        "--base-sha",
        "a" * 40,
        "--head-sha",
        "b" * 40,
    )
    assert result.returncode != 0
    assert not output.exists()


def test_changed_paths_rejects_option_like_inputs() -> None:
    with pytest.raises(ValueError, match="complete hexadecimal"):
        changed_paths("--help", "b" * 40)

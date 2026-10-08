# ruff: noqa: INP001 -- This test is a standalone repository script.
"""Exercise registry resolution and publication permissions without credentials."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(name: str) -> dict:
    """Read the job settings used by publishing and validation callers."""
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text())


def resolve(
    tmp_path: Path, **environment: str
) -> tuple[subprocess.CompletedProcess, dict]:
    """Run the actual composite action shell with only disposable fixture values."""
    action = yaml.safe_load(
        (ROOT / ".github/actions/docker-image-metadata/action.yml").read_text()
    )
    output = tmp_path / "outputs"
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", action["runs"]["steps"][0]["run"]],
        env={
            "PATH": os.defpath,
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY_OWNER": "AI-Shifu",
            "IMAGE_NAME": "ai-shifu-api",
            "REQUESTED_PUSH": "true",
            "REQUIRE_REGISTRY": "false",
            "PUBLISH_GHCR": "false",
            **environment,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    values = (
        dict(line.split("=", 1) for line in output.read_text().splitlines())
        if output.exists()
        else {}
    )
    return result, values


def test_ghcr_publishes_without_external_registry_secrets(tmp_path: Path) -> None:
    """The repository token destination must survive absent optional mirrors."""
    result, values = resolve(tmp_path, PUBLISH_GHCR="true", REQUIRE_REGISTRY="true")
    assert result.returncode == 0, result.stderr
    assert values == {"images": "ghcr.io/ai-shifu/ai-shifu-api", "push-images": "true"}


def test_all_three_destinations_share_image_metadata(tmp_path: Path) -> None:
    """Configured mirrors cannot replace the GHCR destination."""
    credentials = {
        name: uuid4().hex
        for name in (
            "DOCKERHUB_USER",
            "DOCKERHUB_TOKEN",
            "ALIYUN_DOCKER_USERNAME",
            "ALIYUN_DOCKER_PASSWORD",
        )
    }
    result, values = resolve(
        tmp_path,
        PUBLISH_GHCR="true",
        ALIYUN_DOCKER_REGISTRY="registry.example.invalid",
        **credentials,
    )
    assert result.returncode == 0, result.stderr
    assert values["images"].split(",") == [
        "ghcr.io/ai-shifu/ai-shifu-api",
        f"{credentials['DOCKERHUB_USER']}/ai-shifu-api",
        "registry.example.invalid/ai-shifu/ai-shifu-api",
    ]
    assert values["push-images"] == "true"
    for key in ("DOCKERHUB_TOKEN", "ALIYUN_DOCKER_PASSWORD"):
        assert credentials[key] not in str(values) + result.stdout + result.stderr


@pytest.mark.parametrize("ghcr", ["true", "false"])
def test_build_only_never_enables_publication(tmp_path: Path, ghcr: str) -> None:
    """Even a selected GHCR destination cannot override a disabled push toggle."""
    result, values = resolve(tmp_path, PUBLISH_GHCR=ghcr, REQUESTED_PUSH="false")
    assert result.returncode == 0, result.stderr
    assert values["push-images"] == "false"


def test_missing_owner_fails_instead_of_omitting_ghcr(tmp_path: Path) -> None:
    """Requested GHCR publication cannot silently fall back to another registry."""
    result, values = resolve(tmp_path, PUBLISH_GHCR="true", GITHUB_REPOSITORY_OWNER="")
    assert result.returncode != 0
    assert "requires a repository owner" in result.stdout
    assert values == {}


def test_credential_free_validation_still_works(tmp_path: Path) -> None:
    """Untrusted PR validation keeps its local-only registry-independent mode."""
    result, values = resolve(tmp_path, REQUESTED_PUSH="false")
    assert result.returncode == 0, result.stderr
    assert values == {"images": "ai-shifu-local/ai-shifu-api", "push-images": "false"}


def test_only_publishing_callers_grant_package_write() -> None:
    """Permissions must reach both reusable jobs without broadening PR checks."""
    builtin_expression = "${{ github.token }}"
    reusable = workflow("build-docker-image.yml")
    assert "permissions" not in reusable
    for job in reusable["jobs"].values():
        assert "permissions" not in job
        login = next(
            step
            for step in job["steps"]
            if step.get("with", {}).get("registry") == "ghcr.io"
        )
        assert "push-images == 'true'" in login["if"]
        assert "inputs.publish-ghcr" in login["if"]
        assert login["with"]["password"] == builtin_expression
    for filename, name in [
        ("build-latest.yml", "build-latest"),
        ("build-on-release.yml", "build-docker"),
        ("docker-build-check.yml", "candidate-build"),
    ]:
        job = workflow(filename)["jobs"][name]
        assert job["permissions"]["packages"] == "write"
        assert job["with"]["publish-ghcr"] is True
    checks = workflow("docker-build-check.yml")
    validation = checks["jobs"]["native-build"]
    assert "permissions" not in validation
    assert checks["permissions"] == {"contents": "read"}
    assert validation["with"]["push-images"] is False
    assert "secrets" not in validation
    assert "publish-ghcr" not in validation["with"]
    latest = workflow("build-latest.yml")
    assert latest["jobs"]["build-latest"]["if"] == "github.ref == 'refs/heads/main'"


def test_release_pull_commands_match_lowercase_ghcr_owner(tmp_path: Path) -> None:
    """Execute the actual summary shell for a mixed-case owner and custom names."""
    step = workflow("build-on-release.yml")["jobs"]["deploy-summary"]["steps"][0]
    script = re.sub(
        r"\$\{\{(.*?)\}\}",
        lambda match: "success" if "build-docker.result" in match[1] else "fixture",
        step["run"],
    )
    summary = tmp_path / "summary"
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        env={
            "PATH": os.defpath,
            "GITHUB_STEP_SUMMARY": str(summary),
            "GHCR_OWNER": "AcmeOrg",
            "API_IMAGE_NAME": "custom-api",
            "WEB_IMAGE_NAME": "custom-web",
            "RELEASE_TAG": "v1.2.3",
        },
        capture_output=True,
        text=True,
        check=True,
    )
    result = summary.read_text()
    assert "docker pull ghcr.io/acmeorg/custom-api:v1.2.3" in result
    assert "docker pull ghcr.io/acmeorg/custom-web:v1.2.3" in result
    assert "ghcr.io/AcmeOrg/" not in result

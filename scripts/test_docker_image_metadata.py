# ruff: noqa: INP001 -- This test is a standalone repository script.
"""Exercise registry resolution and publication permissions without credentials."""

from __future__ import annotations

import json
import os
import re
import shutil
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


@pytest.mark.parametrize("image", ["ai-shifu-api", "ai-shifu-web"])
def test_all_three_destinations_share_image_metadata(
    tmp_path: Path, image: str
) -> None:
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
        IMAGE_NAME=image,
        ALIYUN_DOCKER_REGISTRY="registry.example.invalid",
        **credentials,
    )
    assert result.returncode == 0, result.stderr
    assert values["images"].split(",") == [
        f"ghcr.io/ai-shifu/{image}",
        f"{credentials['DOCKERHUB_USER']}/{image}",
        f"registry.example.invalid/ai-shifu/{image}",
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
            "DOCKERHUB_OWNER": "fixture-mirror",
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
    assert "docker pull fixture-mirror/custom-api:v1.2.3" in result
    assert "docker pull fixture-mirror/custom-web:v1.2.3" in result
    assert "ai-shifu-cook-web" not in result
    assert "ghcr.io/AcmeOrg/" not in result


@pytest.mark.parametrize(
    ("filename", "job_name"),
    [
        ("build-latest.yml", "build-latest"),
        ("build-on-release.yml", "build-docker"),
        ("docker-build-check.yml", "candidate-build"),
    ],
)
def test_publication_callers_use_new_web_package(filename: str, job_name: str) -> None:
    """Prevent a stale caller or repository variable from publishing the old package."""
    job = workflow(filename)["jobs"][job_name]
    services = {row["service"]: row for row in job["strategy"]["matrix"]["include"]}
    assert services["web"]["default-image"] == "ai-shifu-web"
    assert services["web"]["image-name"] == "AI_SHIFU_WEB_IMAGE_NAME"
    assert services["api"]["default-image"] == "ai-shifu-api"
    assert "AI_SHIFU_COOK_WEB_IMAGE_NAME" not in str(job)


@pytest.mark.parametrize("previous_web", ["ai-shifu-cook-web", "ai-shifu-web"])
def test_release_bump_migrates_web_without_retagging_other_images(
    tmp_path: Path, previous_web: str
) -> None:
    """Exercise the real release shell against legacy and already migrated bundles."""
    step = next(
        step
        for job in workflow("prepare-release.yml")["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name") == "Update project version files"
    )
    # Run the Compose portion with a throwaway index; no commits or registry writes.
    script = (
        step["run"]
        .split("# 6. Docker Compose files", 1)[1]
        .split("# 7. Version files", 1)[0]
    )
    script = script.split("\n", 1)[1]
    docker = tmp_path / "docker"
    docker.mkdir()
    pinned = docker / "docker-compose.yml"
    pinned.write_text(
        "services:\n"
        f"  web:\n    image: aishifu/{previous_web}:v2.3.3\n"
        "  api:\n    image: aishifu/ai-shifu-api:v2.3.3\n"
        "  worker:\n    image: aishifu/ai-shifu-api:v2.3.3\n"
        "  redis:\n    image: redis:7-alpine\n"
    )
    latest = docker / "docker-compose.latest.yml"
    latest.write_text("services:\n  web:\n    image: aishifu/ai-shifu-web:latest\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        [
            "bash",
            "-e",
            "-o",
            "pipefail",
            "-c",
            "TAG_NAME=v9.8.7; UPDATED_FILES=();\n" + script,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    images = {
        name: service["image"]
        for name, service in yaml.safe_load(pinned.read_text())["services"].items()
    }
    assert images == {
        "web": "aishifu/ai-shifu-web:v9.8.7",
        "api": "aishifu/ai-shifu-api:v9.8.7",
        "worker": "aishifu/ai-shifu-api:v9.8.7",
        "redis": "redis:7-alpine",
    }
    assert "ai-shifu-web:latest" in latest.read_text()


def test_release_bump_regenerates_lockfile_without_changing_dependencies(
    tmp_path: Path,
) -> None:
    """Run the release npm path offline and retain the locked dependency graph."""
    npm = shutil.which("npm")
    assert npm is not None, "Release lockfile regression requires npm on PATH"
    step = next(
        step
        for job in workflow("prepare-release.yml")["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name") == "Update project version files"
    )
    script = step["run"].split("# 2. Python pyproject.toml projects", 1)[0]
    script = script.replace("${{ steps.version.outputs.version }}", "9.8.7")
    script = script.replace("${{ steps.version.outputs.tag }}", "v9.8.7")
    environment = {
        **os.environ,
        "npm_config_cache": str(tmp_path / "npm-cache"),
        "npm_config_offline": "true",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
    }
    dependency_dir = tmp_path / "dependency"
    dependency_dir.mkdir()
    (dependency_dir / "package.json").write_text(
        json.dumps({"name": "fixture-dependency", "version": "1.2.3"}) + "\n"
    )
    packed = subprocess.run(
        [
            npm,
            "pack",
            "--ignore-scripts",
            "--json",
            "--pack-destination",
            str(tmp_path),
        ],
        cwd=dependency_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    tarball = tmp_path / json.loads(packed.stdout)[0]["filename"]
    workspace = tmp_path / "repo"
    package_dir = workspace / "src" / "web"
    package_dir.mkdir(parents=True)
    manifest_path = package_dir / "package.json"
    manifest = {
        "name": "fixture-web",
        "version": "1.0.0",
        "dependencies": {"fixture-dependency": "file:" + str(tarball)},
        "scripts": dict.fromkeys(
            ("preinstall", "install", "postinstall", "prepare"), "touch lifecycle-ran"
        ),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    subprocess.run(
        [
            npm,
            "install",
            "--package-lock-only",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ],
        cwd=package_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    lock_path = package_dir / "package-lock.json"
    original_lock = json.loads(lock_path.read_text())
    original_dependencies = {
        name: record for name, record in original_lock["packages"].items() if name
    }
    assert (
        original_dependencies["node_modules/fixture-dependency"]["version"] == "1.2.3"
    )
    assert original_dependencies["node_modules/fixture-dependency"]["integrity"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "npm"
    wrapper.write_text(
        "#!/bin/sh\n"
        'printf "%s\\t" "$PWD" "$@" >> "$NPM_CALL_LOG"\n'
        'printf "\\n" >> "$NPM_CALL_LOG"\n'
        'exec "$REAL_NPM" "$@"\n'
    )
    wrapper.chmod(0o755)
    call_log = tmp_path / "npm-calls"
    environment.update(
        {
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "REAL_NPM": npm,
            "NPM_CALL_LOG": str(call_log),
        }
    )
    first_lock = None
    for _ in range(2):
        result = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", script],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        updated_lock = json.loads(lock_path.read_text())
        assert json.loads(manifest_path.read_text())["version"] == "9.8.7"
        assert updated_lock["version"] == "9.8.7"
        assert updated_lock["packages"][""]["version"] == "9.8.7"
        assert {
            name: record for name, record in updated_lock["packages"].items() if name
        } == original_dependencies
        assert not (package_dir / "lifecycle-ran").exists()
        assert not (package_dir / "node_modules").exists()
        if first_lock is None:
            first_lock = lock_path.read_bytes()
        else:
            assert lock_path.read_bytes() == first_lock
    calls = [
        line.rstrip("\t").split("\t") for line in call_log.read_text().splitlines()
    ]
    assert len(calls) == 2
    for directory, *arguments in calls:
        assert Path(directory) == package_dir.resolve()
        assert arguments == [
            "install",
            "--package-lock-only",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ]


@pytest.mark.parametrize("package_path", ["src/web", "scripts/markdownflow-arena"])
def test_release_bump_preserves_real_lockfiles(
    tmp_path: Path, package_path: str
) -> None:
    """Keep native metadata and dependency flags when bumping real package versions."""
    release_steps = {
        step["name"]: step
        for job in workflow("prepare-release.yml")["jobs"].values()
        for step in job.get("steps", [])
        if "name" in step
    }
    npm_setup = release_steps["Set up npm for lockfile updates"]["run"]
    pinned_npm = re.search(
        r"npm install --global npm@(\d+\.\d+\.\d+)(?:\s|$)", npm_setup
    )
    assert pinned_npm is not None
    docker_npm_setup = next(
        step["run"]
        for job in workflow("docker-build-check.yml")["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name") == "Set up npm for lockfile updates"
    )
    assert docker_npm_setup == npm_setup
    npm_version = subprocess.run(
        ["npm", "--version"], capture_output=True, text=True, check=True
    )
    assert npm_version.stdout.strip() == pinned_npm[1]
    script = release_steps["Update project version files"]["run"].split(
        "# 2. Python pyproject.toml projects", 1
    )[0]
    script = script.replace("${{ steps.version.outputs.version }}", "9.8.7")
    script = script.replace("${{ steps.version.outputs.tag }}", "v9.8.7")
    workspace = tmp_path / "repo"
    package_dir = workspace / package_path
    package_dir.mkdir(parents=True)
    for filename in ("package.json", "package-lock.json", ".npmrc"):
        source = ROOT / package_path / filename
        if source.exists():
            shutil.copyfile(source, package_dir / filename)
    lock_path = package_dir / "package-lock.json"
    original_lock = json.loads(lock_path.read_text())
    original_dependencies = {
        name: record for name, record in original_lock["packages"].items() if name
    }
    environment = {
        **os.environ,
        "npm_config_cache": str(tmp_path / "npm-cache"),
        "npm_config_registry": "https://registry.npmjs.org",
        "npm_config_offline": "false",
        "npm_config_update_notifier": "false",
    }
    first_lock = None
    for _ in range(2):
        result = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", script],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        updated_lock = json.loads(lock_path.read_text())
        assert (
            json.loads((package_dir / "package.json").read_text())["version"] == "9.8.7"
        )
        assert updated_lock["version"] == "9.8.7"
        assert updated_lock["packages"][""]["version"] == "9.8.7"
        assert {
            name: record for name, record in updated_lock["packages"].items() if name
        } == original_dependencies
        assert not (package_dir / "node_modules").exists()
        if first_lock is None:
            first_lock = lock_path.read_bytes()
        else:
            assert lock_path.read_bytes() == first_lock

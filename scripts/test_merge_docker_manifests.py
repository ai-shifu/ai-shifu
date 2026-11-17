#!/usr/bin/env python3
"""Cover registry isolation, bounded retries, and native image artifact reuse."""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch
from uuid import uuid4

import pytest
from merge_docker_manifests import load_images, main, publish, verify_manifest

if TYPE_CHECKING:
    from pathlib import Path

AMD64 = "sha256:" + "a" * 64
ARM64 = "sha256:" + "b" * 64
DIGESTS = {"linux/amd64": AMD64, "linux/arm64": ARM64}
GHCR = "ghcr.io/example/web"
DOCKERHUB = "docker.io/example/web"
ALIYUN = "registry.example.invalid/example/web"


def write_image(directory: Path, platform: str, digest: str, attempt: int) -> Path:
    """Model a native image archive and its smoke record."""
    arch = platform.split("/")[1]
    artifact = directory / f"docker-image-web-{arch}-{attempt}"
    artifact.mkdir()
    (artifact / f"{arch}.json").write_text(
        json.dumps({"platform": platform, "digest": digest})
    )
    archive = artifact / "image.tar"
    archive.touch()
    return archive


@pytest.fixture
def images(tmp_path: Path) -> Path:
    """Create native build outputs from a successful workflow attempt."""
    for platform, digest in DIGESTS.items():
        write_image(tmp_path, platform, digest, 1)
    return tmp_path


def manifest(digests: dict[str, str]) -> str:
    """Produce an index returned by registry preflight or inspection."""
    return json.dumps(
        {
            "manifests": [
                {
                    "digest": digest,
                    "platform": {"os": "linux", "architecture": platform.split("/")[1]},
                }
                for platform, digest in digests.items()
            ]
        }
    )


def successful_command(
    command: tuple[str, ...], **_kwargs: object
) -> subprocess.CompletedProcess:
    """Return matching native descriptors for manifest commands."""
    return subprocess.CompletedProcess(command, 0, stdout=manifest(DIGESTS))


def test_failed_build_rerun_reuses_the_successful_platform_archive(
    images: Path,
) -> None:
    """Use the newest ARM64 artifact with the successful earlier AMD64 artifact."""
    replacement = "sha256:" + "c" * 64
    archive = write_image(images, "linux/arm64", replacement, 2)
    selected = load_images(images)
    assert (
        selected["linux/amd64"].archive == images / "docker-image-web-amd64-1/image.tar"
    )
    assert selected["linux/amd64"].digest == AMD64
    assert selected["linux/arm64"].archive == archive
    assert selected["linux/arm64"].digest == replacement


@pytest.mark.parametrize("missing", ["arm64.json", "image.tar"])
def test_missing_platform_never_contacts_a_registry(images: Path, missing: str) -> None:
    """A missing archive or smoke record prevents login and tag updates."""
    (images / "docker-image-web-arm64-1" / missing).unlink()
    with (
        patch("merge_docker_manifests.subprocess.run") as run,
        pytest.raises(ValueError, match="tested image"),
    ):
        publish(images, {"tags": [f"{GHCR}:latest"]}, "example", uuid4().hex)
    run.assert_not_called()


def test_invalid_newer_record_never_falls_back(images: Path) -> None:
    """A malformed record cannot replace the verified native digest."""
    write_image(images, "linux/arm64", "invalid", 2)
    with pytest.raises(ValueError, match="Invalid tested image artifact"):
        load_images(images)


@pytest.mark.parametrize(
    ("registry", "repository", "copy_go_debug"),
    [
        ("aliyun", ALIYUN, "gctrace=1,http2client=1,http2client=0"),
        ("ghcr", GHCR, None),
        ("dockerhub", DOCKERHUB, None),
    ],
)
def test_http1_is_scoped_to_aliyun_copies(
    images: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: str,
    repository: str,
    copy_go_debug: str | None,
) -> None:
    """Pass the matrix registry through the publisher entry point to ORAS only."""
    monkeypatch.setattr("sys.argv", ["merge_docker_manifests.py", str(images)])
    monkeypatch.setenv(
        "IMAGE_METADATA", json.dumps({"tags": [f"{repository}:candidate"]})
    )
    monkeypatch.setenv("IMAGE_REGISTRY", registry)
    monkeypatch.setenv("REGISTRY_USERNAME", "example")
    monkeypatch.setenv("REGISTRY_PASSWORD", uuid4().hex)
    monkeypatch.setenv("GODEBUG", "gctrace=1,http2client=1")
    with patch(
        "merge_docker_manifests.subprocess.run",
        side_effect=successful_command,
    ) as run:
        main()

    calls = run.call_args_list
    assert [
        call.args[0][-1] for call in calls if call.args[0][3:5] == ("oras", "cp")
    ] == [
        f"{repository}@{AMD64}",
        f"{repository}@{ARM64}",
    ]
    for call in calls:
        if copy_go_debug and call.args[0][3:5] == ("oras", "cp"):
            assert call.kwargs["env"]["GODEBUG"] == copy_go_debug
        else:
            assert call.kwargs["env"] is None
    assert os.environ["GODEBUG"] == "gctrace=1,http2client=1"


def test_stalled_aliyun_publication_leaves_other_targets_independent(
    images: Path,
) -> None:
    """Exhaust only the stalled registry's upload attempts and publish sibling tags."""
    password = uuid4().hex

    def run_command(
        command: tuple[str, ...], **_kwargs: object
    ) -> subprocess.CompletedProcess:
        if command[3:5] == ("oras", "cp") and command[-1].startswith(ALIYUN):
            raise subprocess.CalledProcessError(124, command)
        return successful_command(command)

    with (
        patch("merge_docker_manifests.subprocess.run", side_effect=run_command) as run,
        patch("merge_docker_manifests.time.sleep") as sleep,
    ):
        with pytest.raises(subprocess.CalledProcessError) as stalled_job:
            publish(
                images,
                {"tags": [f"{ALIYUN}:latest"]},
                "example",
                password,
                registry_name="aliyun",
            )
        assert stalled_job.value.returncode == 124
        stalled = [
            call.args[0] for call in run.call_args_list if call.args[0][3] == "oras"
        ]
        assert len(stalled) == 3
        assert all(
            command[:3] == ("timeout", "--kill-after=5s", "120s") for command in stalled
        )
        assert all(command[-1] == f"{ALIYUN}@{AMD64}" for command in stalled)
        assert [call.args for call in sleep.call_args_list] == [(2,), (4,)]
        assert not any("imagetools" in call.args[0] for call in run.call_args_list)

        for repository in (GHCR, DOCKERHUB):
            run.reset_mock()
            tags = [f"{repository}:latest", f"{repository}:commit"]
            publish(images, {"tags": tags}, "example", password)
            calls = [call.args[0][3:] for call in run.call_args_list]
            assert calls[0][-1] == repository.split("/")[0]
            assert run.call_args_list[0].kwargs["input"] == password + "\n"
            assert all(password not in command for command in calls)
            assert [command[-1] for command in calls if command[0] == "oras"] == [
                f"{repository}@{AMD64}",
                f"{repository}@{ARM64}",
            ]
            assert calls[3][3:5] == ("create", "--dry-run")
            assert calls[4][3:5] == ("create", "--tag")
            assert all(tag in calls[4] for tag in tags)
            assert [command[-1] for command in calls[5:]] == tags


def test_transient_copy_failure_is_retried_before_tags_move(images: Path) -> None:
    """Resume this registry from the same immutable archive after a network error."""
    copies = []

    def run_command(
        command: tuple[str, ...], **_kwargs: object
    ) -> subprocess.CompletedProcess:
        if command[3:5] == ("oras", "cp"):
            copies.append(command[-1])
            if len(copies) == 1:
                raise subprocess.CalledProcessError(
                    1, command, stderr="connection reset"
                )
        return successful_command(command)

    with (
        patch("merge_docker_manifests.subprocess.run", side_effect=run_command) as run,
        patch("merge_docker_manifests.time.sleep"),
    ):
        publish(images, {"tags": [f"{GHCR}:latest"]}, "example", uuid4().hex)
    assert copies == [f"{GHCR}@{AMD64}", f"{GHCR}@{AMD64}", f"{GHCR}@{ARM64}"]
    assert run.call_args[0][0][-1] == f"{GHCR}:latest"


@pytest.mark.parametrize("bad_preflight", [True, False])
def test_rejects_registry_indexes_missing_an_architecture(
    images: Path, bad_preflight: bool
) -> None:
    """Validate the index before writing and read back both architectures afterward."""
    incorrect = manifest({"linux/amd64": AMD64})
    output = [incorrect] if bad_preflight else [manifest(DIGESTS), "", incorrect]
    with (
        patch("merge_docker_manifests.registry_command"),
        patch("merge_docker_manifests.docker", side_effect=output) as docker,
        pytest.raises(ValueError, match="Manifest platforms"),
    ):
        publish(images, {"tags": [f"{GHCR}:latest"]}, "example", uuid4().hex)
    if bad_preflight:
        assert docker.call_count == 1
        assert docker.call_args.args[:2] == ("create", "--dry-run")
    else:
        assert docker.call_args.args[:2] == ("inspect", "--raw")


def test_rejects_wrong_and_duplicate_manifest_platforms() -> None:
    """A successful CLI exit alone cannot prove a correct multi-platform image."""
    wrong = manifest({**DIGESTS, "linux/arm64": "sha256:" + "d" * 64})
    with pytest.raises(ValueError, match="Manifest platforms"):
        verify_manifest(wrong, DIGESTS)
    duplicate = json.loads(manifest(DIGESTS))
    duplicate["manifests"].append(duplicate["manifests"][0])
    with pytest.raises(ValueError, match="Duplicate manifest platform"):
        verify_manifest(json.dumps(duplicate), DIGESTS)


@pytest.mark.parametrize(
    "tags",
    [
        [],
        ["web"],
        [f"{GHCR}:bad tag"],
        [f"{GHCR}@{AMD64}"],
        [f"{GHCR}:latest", f"{ALIYUN}:latest"],
    ],
)
def test_invalid_or_mixed_registry_tags_never_contact_a_registry(
    images: Path, tags: list[str]
) -> None:
    """Disallow metadata that could recreate a shared registry failure gate."""
    with (
        patch("merge_docker_manifests.subprocess.run") as run,
        pytest.raises(ValueError, match="tag"),
    ):
        publish(images, {"tags": tags}, "example", uuid4().hex)
    run.assert_not_called()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))

#!/usr/bin/env python3
"""Publish and verify the tested native images for one registry repository."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PLATFORMS = frozenset({"linux/amd64", "linux/arm64"})
DIGEST_PATTERN = re.compile(r"sha256:[a-f0-9]{64}")
ARTIFACT_PATTERN = re.compile(r"-(amd64|arm64)-([1-9][0-9]*)$")
REGISTRY_TIMEOUT = 30
COPY_TIMEOUT = 120
ATTEMPTS = 3


@dataclass(frozen=True)
class TestedImage:
    """Archive and manifest digest recorded by a successful native smoke test."""

    archive: Path
    digest: str


def load_images(directory: Path) -> dict[str, TestedImage]:
    """Select the newest tested image artifact for each required platform."""
    selected: dict[str, tuple[int, TestedImage]] = {}
    for folder in sorted(directory.glob("docker-image-*")):
        artifact = ARTIFACT_PATTERN.search(folder.name)
        if not artifact:
            message = f"Unexpected image artifact: {folder.name}"
            raise ValueError(message)
        arch, attempt_text = artifact.groups()
        platform = f"linux/{arch}"
        path = folder / f"{arch}.json"
        archive = folder / "image.tar"
        if not path.is_file() or not archive.is_file():
            message = f"Incomplete tested image artifact: {folder.name}"
            raise ValueError(message)
        record = json.loads(path.read_text())
        digest = record.get("digest", "")
        if (
            record.get("platform") != platform
            or not isinstance(digest, str)
            or not DIGEST_PATTERN.fullmatch(digest)
        ):
            message = f"Invalid tested image artifact: {folder.name}"
            raise ValueError(message)
        attempt = int(attempt_text)
        previous = selected.get(platform)
        if previous and previous[0] == attempt:
            message = f"Duplicate image for {platform} attempt {attempt}"
            raise ValueError(message)
        if previous is None or attempt > previous[0]:
            selected[platform] = (attempt, TestedImage(archive, digest))
    if selected.keys() != PLATFORMS:
        message = "Both linux/amd64 and linux/arm64 tested image archives are required"
        raise ValueError(message)
    return {platform: entry[1] for platform, entry in sorted(selected.items())}


def publication_target(metadata: dict) -> tuple[str, list[str]]:
    """Require all tags to address the one repository owned by this job."""
    tags = metadata.get("tags", [])
    repositories = set()
    for tag in tags:
        if not isinstance(tag, str) or "@" in tag or any(c.isspace() for c in tag):
            message = "Invalid image tag"
            raise ValueError(message)
        image, separator, version = tag.rpartition(":")
        if (
            not separator
            or "/" not in image
            or not re.fullmatch(r"[\w][\w.-]{0,127}", version)
        ):
            message = "Fully qualified image tags are required"
            raise ValueError(message)
        repositories.add(image)
    if len(repositories) != 1:
        message = "Publication requires tags for exactly one registry repository"
        raise ValueError(message)
    return repositories.pop(), tags


def registry_command(
    *command: str, timeout: int = REGISTRY_TIMEOUT, input_text: str | None = None
) -> str:
    """Retry a registry command with a deadline for each attempt."""
    # GNU timeout also stops child processes, including Docker CLI plugins.
    bounded = ("timeout", "--kill-after=5s", f"{timeout}s", *command)
    attempt = 1
    while True:
        try:
            return subprocess.run(
                bounded,
                check=True,
                capture_output=True,
                text=True,
                input=input_text,
            ).stdout
        except subprocess.CalledProcessError as error:
            if attempt == ATTEMPTS:
                raise
            delay = attempt * 2
            print(f"{error}. Retrying in {delay}s.", file=sys.stderr, flush=True)
            time.sleep(delay)
            attempt += 1


def docker(*arguments: str) -> str:
    """Run Buildx without shell evaluation and propagate registry failures."""
    return registry_command("docker", "buildx", "imagetools", *arguments)


def verify_manifest(raw: str, digests: dict[str, str]) -> None:
    """Require the manifest to contain exactly the two expected platform images."""
    manifest = json.loads(raw)
    platforms: dict[str, str] = {}
    for image in manifest.get("manifests", []):
        platform = image.get("platform", {})
        key = f"{platform.get('os')}/{platform.get('architecture')}"
        if key in platforms:
            message = f"Duplicate manifest platform: {key}"
            raise ValueError(message)
        platforms[key] = image.get("digest", "")
    if platforms != digests:
        message = "Manifest platforms/digests differ from the native build outputs"
        raise ValueError(message)


def publish(directory: Path, metadata: dict, username: str, password: str) -> None:
    """Copy both tested images, then preflight and verify this repository's tags."""
    images = load_images(directory)
    image, tags = publication_target(metadata)
    if not username or not password:
        message = "Registry credentials are required for publication"
        raise ValueError(message)
    registry = image.split("/", 1)[0]
    registry_command(
        "docker",
        "login",
        "--username",
        username,
        "--password-stdin",
        registry,
        input_text=password + "\n",
    )
    for platform, artifact in images.items():
        target = f"{image}@{artifact.digest}"
        registry_command(
            "oras",
            "cp",
            "--from-oci-layout",
            f"{artifact.archive}@{artifact.digest}",
            target,
            timeout=COPY_TIMEOUT,
        )
        print(f"Copied tested {platform} image to {target}", flush=True)

    digests = {platform: artifact.digest for platform, artifact in images.items()}
    sources = [f"{image}@{digest}" for digest in digests.values()]
    options = [option for tag in tags for option in ("--tag", tag)]
    verify_manifest(docker("create", "--dry-run", *options, *sources), digests)
    docker("create", *options, *sources)
    for tag in tags:
        verify_manifest(docker("inspect", "--raw", tag), digests)
        print(f"Verified {tag}: linux/amd64, linux/arm64", flush=True)


def main() -> None:
    """Read workflow metadata and publish the downloaded image archives."""
    if len(sys.argv) != 2:
        message = "Usage: merge_docker_manifests.py IMAGE_ARTIFACT_DIRECTORY"
        raise SystemExit(message)
    try:
        publish(
            Path(sys.argv[1]),
            json.loads(os.environ["IMAGE_METADATA"]),
            os.environ.pop("REGISTRY_USERNAME"),
            os.environ.pop("REGISTRY_PASSWORD"),
        )
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()

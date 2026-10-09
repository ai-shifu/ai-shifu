#!/usr/bin/env python3
"""Publish image tags only after validating both native platform digests."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PLATFORMS = frozenset({"linux/amd64", "linux/arm64"})
DIGEST_PATTERN = re.compile(r"sha256:[a-f0-9]{64}")
ARTIFACT_PATTERN = re.compile(r"-(amd64|arm64)-([1-9][0-9]*)$")


def load_digests(directory: Path) -> dict[str, str]:
    """Select the newest successful attempt for each required platform."""
    selected: dict[str, tuple[int, str]] = {}
    for path in sorted(directory.glob("*/*.json")):
        artifact = ARTIFACT_PATTERN.search(path.parent.name)
        if not artifact:
            message = f"Unexpected digest artifact: {path.parent.name}"
            raise ValueError(message)
        arch, attempt_text = artifact.groups()
        record = json.loads(path.read_text())
        platform = f"linux/{arch}"
        digest = record.get("digest", "")
        if (
            record.get("platform") != platform
            or path.name != f"{arch}.json"
            or not isinstance(digest, str)
            or not DIGEST_PATTERN.fullmatch(digest)
        ):
            message = f"Invalid digest record: {path.name}"
            raise ValueError(message)
        attempt = int(attempt_text)
        previous = selected.get(platform)
        if previous and previous[0] == attempt:
            message = f"Duplicate digest for {platform} attempt {attempt}"
            raise ValueError(message)
        if previous is None or attempt > previous[0]:
            selected[platform] = (attempt, digest)
    if selected.keys() != PLATFORMS:
        message = "Both linux/amd64 and linux/arm64 digests are required"
        raise ValueError(message)
    return {platform: entry[1] for platform, entry in sorted(selected.items())}


def tags_by_image(metadata: dict) -> dict[str, list[str]]:
    """Group fully qualified tags without mixing registry repositories."""
    grouped: dict[str, list[str]] = {}
    for tag in metadata.get("tags", []):
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
        grouped.setdefault(image, []).append(tag)
    if not grouped:
        message = "At least one publication tag is required"
        raise ValueError(message)
    return grouped


def docker(*arguments: str) -> str:
    """Run Buildx without shell evaluation and propagate registry failures."""
    result = subprocess.run(
        ["docker", "buildx", "imagetools", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


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


def publish(directory: Path, metadata: dict) -> None:
    """Preflight all registries, then publish and inspect their manifest tags."""
    digests = load_digests(directory)
    grouped = tags_by_image(metadata)
    commands: list[tuple[list[str], list[str]]] = []
    for image, tags in grouped.items():
        sources = [f"{image}@{digest}" for digest in digests.values()]
        options = [option for tag in tags for option in ("--tag", tag)]
        # No tags change until every destination can resolve both platform images.
        raw = docker("create", "--dry-run", *options, *sources)
        verify_manifest(raw, digests)
        commands.append((tags, options + sources))
    for tags, arguments in commands:
        docker("create", *arguments)
        for tag in tags:
            verify_manifest(docker("inspect", "--raw", tag), digests)
            print(f"Verified {tag}: linux/amd64, linux/arm64")


def main() -> None:
    """Read workflow metadata and merge downloaded digest artifacts."""
    if len(sys.argv) != 2:
        message = "Usage: merge_docker_manifests.py DIGEST_DIRECTORY"
        raise SystemExit(message)
    try:
        publish(Path(sys.argv[1]), json.loads(os.environ["IMAGE_METADATA"]))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        # Preserve the build/registry error; never retry an entire build or publication.
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()

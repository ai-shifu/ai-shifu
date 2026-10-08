#!/usr/bin/env python3
"""Select extra ARM64 packaging checks for changes to production image inputs."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

SHARED_FILES = frozenset(
    {
        ".dockerignore",
        ".github/workflows/build-latest.yml",
        ".github/workflows/build-on-release.yml",
        ".github/workflows/build-docker-image.yml",
        ".github/workflows/docker-build-check.yml",
        ".github/workflows/runtime-harness.yml",
        ".github/workflows/prepare-release.yml",
        "docker/docker-compose.latest.yml",
        "docker/docker-compose.runtime-harness.yml",
        "scripts/merge_docker_manifests.py",
        "scripts/test_merge_docker_manifests.py",
        "scripts/check_docker_image.py",
        "scripts/test_check_docker_image.py",
        "scripts/test_docker_image_metadata.py",
        "scripts/select_docker_checks.py",
        "scripts/test_select_docker_checks.py",
        "scripts/test_runtime_packaging.py",
    }
)
API_FILES = frozenset({"src/api/Dockerfile", "src/api/requirements.txt"})
WEB_FILES = frozenset(
    {
        "src/web/Dockerfile",
        "src/web/package.json",
        "src/web/package-lock.json",
        "src/web/.npmrc",
        "src/web/scripts/check-production-dependencies.mjs",
    }
)
SERVICE_IMAGES = (
    {
        "service": "api",
        "image-name": "ai-shifu-api",
        "dockerfile": "src/api/Dockerfile",
    },
    {
        "service": "web",
        "image-name": "ai-shifu-web",
        "dockerfile": "src/web/Dockerfile",
    },
)
SHA_PATTERN = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")


def changed_paths(base_sha: str, head_sha: str) -> list[str]:
    """Read the PR's three-dot diff without loading or executing changed files."""
    if not SHA_PATTERN.fullmatch(base_sha) or not SHA_PATTERN.fullmatch(head_sha):
        message = "PR comparison requires complete hexadecimal base and head SHAs"
        raise ValueError(message)
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            f"{base_sha}...{head_sha}",
            "--",
        ],
        check=True,
        capture_output=True,
    )
    # Disabling rename detection retains both deleted and added input paths.
    # NUL separation also keeps whitespace and non-UTF-8 names unambiguous.
    return [os.fsdecode(path) for path in result.stdout.split(b"\0") if path]


def select_services(paths: Iterable[str]) -> set[str]:
    """Select only services whose Dockerfile, dependencies or packaging changed."""
    services: set[str] = set()
    for path in paths:
        if path in SHARED_FILES or path.startswith(
            ".github/actions/docker-image-metadata/"
        ):
            return {"api", "web"}
        if path in API_FILES:
            services.add("api")
        if path in WEB_FILES or (
            path.startswith("src/web/next.config.")
            and "/" not in path.removeprefix("src/web/")
        ):
            services.add("web")
    return services


def write_outputs(output: Path, services: set[str]) -> None:
    """Append deterministic GitHub job outputs with a compact service matrix."""
    matrix = {
        "include": [image for image in SERVICE_IMAGES if image["service"] in services]
    }
    with output.open("a", encoding="utf-8") as stream:
        stream.write(f"run={str(bool(services)).lower()}\n")
        stream.write(f"matrix={json.dumps(matrix, separators=(',', ':'))}\n")


def main() -> None:
    """Select PR inputs or all services for an explicitly requested manual run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--event", required=True, choices=("pull_request", "workflow_dispatch")
    )
    parser.add_argument("--base-sha")
    parser.add_argument("--head-sha")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.event == "workflow_dispatch":
        services = {"api", "web"}
    else:
        if not args.base_sha or not args.head_sha:
            parser.error("pull_request requires --base-sha and --head-sha")
        try:
            services = select_services(changed_paths(args.base_sha, args.head_sha))
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            parser.error(str(error))
    write_outputs(args.output, services)


if __name__ == "__main__":
    main()

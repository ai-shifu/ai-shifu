#!/usr/bin/env python3
"""Coordinate API/web latest promotion and render digest-pinned Compose inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from functools import partial
from pathlib import Path

from merge_docker_manifests import (
    DIGEST_PATTERN,
    PERMANENT_ERRORS,
    PLATFORMS,
    docker,
    inspect_digest,
    require_same_digest,
    write_json,
)

SERVICES = frozenset({"api", "web"})
ARTIFACT_PATTERN = re.compile(r"^docker-publication-(api|web)-([1-9][0-9]*)$")
SHA_PATTERN = re.compile(r"[a-f0-9]{40}")
RUN_ANNOTATION = "io.ai-shifu.publication.run-id"
ATTEMPT_ANNOTATION = "io.ai-shifu.publication.run-attempt"
COMPOSE_SERVICES = {
    "api": ("ai-shifu-api", "ai-shifu-celery-worker", "ai-shifu-celery-beat"),
    "web": ("ai-shifu-cook-web",),
}


class StalePublicationError(ValueError):
    """Indicate that a newer main build already owns the mutable channel."""


def validate_images(images: list[dict]) -> None:
    """Require nonempty, distinct repositories and valid two-platform references."""
    if not images:
        message = "A published service must contain at least one registry image"
        raise ValueError(message)
    repositories = set()
    for image in images:
        repository = image.get("repository", "")
        if (
            not isinstance(repository, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9.:/_-]*", repository)
            or "/" not in repository
        ):
            message = "Invalid descriptor repository"
            raise ValueError(message)
        if repository in repositories:
            message = "Duplicate descriptor repository"
            raise ValueError(message)
        repositories.add(repository)
        if not DIGEST_PATTERN.fullmatch(image.get("digest", "")):
            message = "Invalid descriptor index digest"
            raise ValueError(message)
        platforms = image.get("platforms", {})
        if platforms.keys() != PLATFORMS or any(
            not DIGEST_PATTERN.fullmatch(digest) for digest in platforms.values()
        ):
            message = "Invalid descriptor platform digests"
            raise ValueError(message)


def load_publication(directory: Path, sha: str, run_id: str, attempt: int) -> dict:
    """Carry successful services across attempts of this run, never across SHAs."""
    if not SHA_PATTERN.fullmatch(sha) or not run_id.isdecimal() or attempt < 1:
        message = "Invalid publication source identity"
        raise ValueError(message)
    selected = {}
    for path in sorted(directory.glob("*/service.json")):
        match = ARTIFACT_PATTERN.fullmatch(path.parent.name)
        if not match:
            message = "Unexpected service publication artifact"
            raise ValueError(message)
        service, attempt_text = match.groups()
        service_attempt = int(attempt_text)
        record = json.loads(path.read_text())
        source = record.get("source", {})
        if (
            record.get("schema_version") != 1
            or record.get("service") != service
            or source != {"sha": sha, "run_id": run_id, "run_attempt": service_attempt}
            or service_attempt > attempt
        ):
            message = "Service publication provenance does not match this workflow run"
            raise ValueError(message)
        validate_images(record.get("images", []))
        previous = selected.get(service)
        if previous and previous["build_attempt"] == service_attempt:
            message = "Duplicate service publication artifact"
            raise ValueError(message)
        if previous is None or service_attempt > previous["build_attempt"]:
            selected[service] = {
                "build_attempt": service_attempt,
                "images": record["images"],
            }
    if selected.keys() != SERVICES:
        message = "Successful API and web publication artifacts are both required"
        raise ValueError(message)
    # Both services must be available in precisely the same registry set.
    registries = [
        {registry_of(image["repository"]) for image in selected[service]["images"]}
        for service in sorted(SERVICES)
    ]
    if registries[0] != registries[1]:
        message = "API and web registry destinations differ"
        raise ValueError(message)
    return {
        "schema_version": 1,
        "source": {"sha": sha, "run_id": run_id, "run_attempt": attempt},
        "services": selected,
    }


def registry_of(repository: str) -> str:
    """Normalize short Docker Hub names and explicit registry hosts."""
    first = repository.split("/", maxsplit=1)[0]
    return (
        first if "." in first or ":" in first or first == "localhost" else "docker.io"
    )


def compose_override(descriptor: dict, registry: str) -> dict:
    """Pin the API, workers, scheduler, and web to one publication descriptor."""
    if (
        descriptor.get("schema_version") != 1
        or descriptor.get("services", {}).keys() != SERVICES
    ):
        message = "Unsupported deployment descriptor"
        raise ValueError(message)
    output = {"services": {}}
    for service, record in descriptor["services"].items():
        validate_images(record["images"])
        matches = [
            image
            for image in record["images"]
            if registry_of(image["repository"]) == registry
        ]
        if len(matches) != 1:
            message = f"Exactly one {service} image is required for registry {registry}"
            raise ValueError(message)
        image = matches[0]
        for name in COMPOSE_SERVICES[service]:
            output["services"][name] = {
                "image": f"{image['repository']}@{image['digest']}"
            }
    return output


def ensure_current_main(sha: str) -> None:
    """Fail closed unless the source is still the current main branch tip."""
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        message = "Only main may promote latest"
        raise ValueError(message)
    result = subprocess.run(
        ["git", "ls-remote", "origin", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip().split() != [sha, "refs/heads/main"]:
        message = "Main has advanced; this workflow must not promote latest"
        raise StalePublicationError(message)


def ensure_not_newer(image: dict, source: dict, build_attempt: int) -> None:
    """Preserve a newer successful run, including rebuilds of the same SHA."""
    try:
        current = json.loads(
            docker(
                "inspect",
                "--format",
                "{{json .Manifest}}",
                f"{image['repository']}:latest",
            )
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").lower()
        missing = any(
            marker in detail
            for marker in (
                "manifest unknown",
                "manifest not found",
                "no such manifest",
                ": not found",
                "status: 404",
            )
        )
        if missing and not any(marker in detail for marker in PERMANENT_ERRORS):
            return
        raise
    annotations = current.get("annotations", {})
    current_run = annotations.get(RUN_ANNOTATION)
    current_attempt = annotations.get(ATTEMPT_ANNOTATION)
    if current_run is None and current_attempt is None:
        return  # Migration from the old unannotated latest channel.
    if not str(current_run).isdecimal() or not str(current_attempt).isdecimal():
        message = "Latest has invalid publication ordering annotations"
        raise ValueError(message)
    if (int(current_run), int(current_attempt)) > (
        int(source["run_id"]),
        build_attempt,
    ):
        message = "A newer workflow publication already owns latest"
        raise StalePublicationError(message)


def _ensure_latest_current(source: dict, image: dict, build_attempt: int) -> None:
    """Recheck mutable-channel authorization before every write/retry attempt."""
    ensure_current_main(source["sha"])
    ensure_not_newer(image, source, build_attempt)


def _copy_indexes(descriptor: dict, status_path: Path, *, promote_latest: bool) -> None:
    """Preflight all references and copy unchanged indexes to a selected channel."""
    source = descriptor["source"]
    targets = [
        (image, record["build_attempt"], service)
        for service, record in descriptor["services"].items()
        for image in record["images"]
    ]
    identity = hashlib.sha256(
        (json.dumps(descriptor, indent=2, sort_keys=True) + "\n").encode()
    ).hexdigest()
    status = {
        "phase": "latest-promotion" if promote_latest else "candidate-copy",
        "descriptor_sha256": identity,
        "source": source,
        "state": "pending",
        "targets": [
            {
                "tag": f"{image['repository']}:latest"
                if promote_latest
                else f"{image['repository']}:candidate-copy-{source['run_id']}-{source['run_attempt']}-{service}",
                "expected_digest": image["digest"],
                "state": "pending",
            }
            for image, _, service in targets
        ],
    }
    write_json(status_path, status)
    try:
        if promote_latest:
            ensure_current_main(source["sha"])
        for image, build_attempt, _ in targets:
            if promote_latest:
                ensure_not_newer(image, source, build_attempt)
            reference = f"{image['repository']}@{image['digest']}"
            annotations = {
                RUN_ANNOTATION: source["run_id"],
                ATTEMPT_ANNOTATION: str(build_attempt),
            }
            require_same_digest(
                inspect_digest(reference, image["platforms"], annotations),
                image["digest"],
            )
        for (image, build_attempt, _), target in zip(
            targets, status["targets"], strict=True
        ):
            if promote_latest:
                ensure_current_main(source["sha"])
                ensure_not_newer(image, source, build_attempt)
            target["state"] = "unverified"
            write_json(status_path, status)
            docker(
                "create",
                "--tag",
                target["tag"],
                f"{image['repository']}@{image['digest']}",
                before_attempt=partial(
                    _ensure_latest_current, source, image, build_attempt
                )
                if promote_latest
                else None,
            )
            require_same_digest(
                inspect_digest(target["tag"], image["platforms"]), image["digest"]
            )
            target["state"] = "verified"
            write_json(status_path, status)
        if promote_latest:
            ensure_current_main(source["sha"])
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        status["state"] = (
            "stale" if isinstance(error, StalePublicationError) else "failed"
        )
        status["error_type"] = type(error).__name__
        write_json(status_path, status)
        raise
    status["state"] = "verified"
    write_json(status_path, status)


def promote(descriptor: dict, status_path: Path) -> None:
    """Require current main and publication ordering before moving latest."""
    _copy_indexes(descriptor, status_path, promote_latest=True)


def verify_candidate_copies(descriptor: dict, status_path: Path) -> None:
    """Exercise the exact copy/readback path using isolated candidate tags."""
    _copy_indexes(descriptor, status_path, promote_latest=False)


def main() -> None:
    """Aggregate current-run artifacts or render an already saved descriptor."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect")
    collect.add_argument("artifact_directory", type=Path)
    collect.add_argument("--descriptor", type=Path, required=True)
    collect.add_argument("--status", type=Path, required=True)
    channel = collect.add_mutually_exclusive_group()
    channel.add_argument("--promote-latest", action="store_true")
    channel.add_argument("--verify-candidate-copies", action="store_true")
    render = subparsers.add_parser("render")
    render.add_argument("descriptor", type=Path)
    render.add_argument("--registry", default="docker.io")
    render.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "render":
            write_json(
                args.output,
                compose_override(
                    json.loads(args.descriptor.read_text()), args.registry
                ),
            )
            return
        descriptor = load_publication(
            args.artifact_directory,
            os.environ["GITHUB_SHA"],
            os.environ["GITHUB_RUN_ID"],
            int(os.environ["GITHUB_RUN_ATTEMPT"]),
        )
        write_json(args.descriptor, descriptor)
        if args.promote_latest:
            promote(descriptor, args.status)
        elif args.verify_candidate_copies:
            verify_candidate_copies(descriptor, args.status)
        else:
            write_json(
                args.status,
                {
                    "phase": "descriptor-only",
                    "state": "verified",
                    "source": descriptor["source"],
                },
            )
    except StalePublicationError as error:
        print(f"::notice::{error}")
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()

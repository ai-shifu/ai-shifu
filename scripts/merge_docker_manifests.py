#!/usr/bin/env python3
"""Publish verified service manifests and record their immutable digest references."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

PLATFORMS = frozenset({"linux/amd64", "linux/arm64"})
DIGEST_PATTERN = re.compile(r"sha256:[a-f0-9]{64}")
ARTIFACT_PATTERN = re.compile(r"-(amd64|arm64)-([1-9][0-9]*)$")
TRANSIENT_ERRORS = (
    "tls handshake timeout",
    "i/o timeout",
    "connection reset by peer",
    "connection refused",
    "temporary failure in name resolution",
    "context deadline exceeded",
    "unexpected eof",
)
PERMANENT_ERRORS = (
    "unauthorized",
    "authentication required",
    "denied",
    "forbidden",
    "unsupported media type",
    "unsupported mediatype",
    "manifest invalid",
    "certificate signed by unknown authority",
)


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
    """Group fully qualified immutable/candidate tags by registry repository."""
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
        if version == "latest":
            message = "Only the coordinated main promotion may publish latest"
            raise ValueError(message)
        grouped.setdefault(image, []).append(tag)
    if not grouped:
        message = "At least one publication tag is required"
        raise ValueError(message)
    return grouped


def is_transport_failure(detail: str) -> bool:
    """Recognize recoverable network failures without retrying permanent errors."""
    lowered = detail.lower()
    return any(marker in lowered for marker in TRANSIENT_ERRORS) and not any(
        marker in lowered for marker in PERMANENT_ERRORS
    )


def docker(*arguments: str, before_attempt: Callable[[], None] | None = None) -> str:
    """Retry bounded transport failures; preserve auth and format failures."""
    for attempt in range(3):
        if before_attempt is not None:
            before_attempt()
        try:
            result = subprocess.run(
                ["docker", "buildx", "imagetools", *arguments],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            if attempt == 2 or not is_transport_failure(error.stderr or ""):
                raise
            print(
                f"Registry transport failure; retrying operation ({attempt + 1}/2)",
                file=sys.stderr,
            )
            time.sleep(2**attempt)
        else:
            return result.stdout
    message = "Registry retry loop exhausted"
    raise RuntimeError(message)


def verify_manifest(raw: str, digests: dict[str, str]) -> dict:
    """Require exactly the two expected platform images and return the index."""
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
    return manifest


def inspect_digest(
    reference: str, digests: dict[str, str], annotations: dict[str, str] | None = None
) -> str:
    """Read the registry-reported index digest rather than hashing CLI output."""
    manifest = verify_manifest(
        docker("inspect", "--format", "{{json .Manifest}}", reference), digests
    )
    digest = manifest.get("digest", "")
    if not isinstance(digest, str) or not DIGEST_PATTERN.fullmatch(digest):
        message = "Registry inspection did not return a valid index digest"
        raise ValueError(message)
    if (
        annotations
        and manifest.get("mediaType") != "application/vnd.oci.image.index.v1+json"
    ):
        message = "Registry index must use OCI media type for publication ordering annotations"
        raise ValueError(message)
    if annotations and any(
        manifest.get("annotations", {}).get(key) != value
        for key, value in annotations.items()
    ):
        message = (
            "Registry index publication annotations differ from the workflow source"
        )
        raise ValueError(message)
    return digest


def require_same_digest(actual: str, expected: str | None) -> None:
    """Keep each index reference and its recorded registry digest identical."""
    if expected is not None and actual != expected:
        message = "Registry index digest differs from the publication descriptor"
        raise ValueError(message)


def publication_annotations() -> dict[str, str]:
    """Keep ordering metadata on the index that will later become latest."""
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not run_id:
        return {}
    attempt = os.environ["GITHUB_RUN_ATTEMPT"]
    if not run_id.isdecimal() or not attempt.isdecimal():
        message = "Invalid workflow publication identity"
        raise ValueError(message)
    return {
        "io.ai-shifu.publication.run-id": run_id,
        "io.ai-shifu.publication.run-attempt": attempt,
    }


def write_json(path: Path | None, value: dict) -> None:
    """Persist a report outside the source tree when a caller requests one."""
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def publish(
    directory: Path, metadata: dict, status_path: Path | None = None
) -> list[dict]:
    """Preflight every registry, publish candidates, and record partial outcomes."""
    digests = load_digests(directory)
    grouped = tags_by_image(metadata)
    status = {"phase": "service-manifest", "state": "pending", "targets": []}
    commands: list[tuple[str, list[str], list[str]]] = []
    references: list[dict] = []
    annotations = publication_annotations()
    status["targets"] = [
        {"tag": tag, "state": "pending"} for tags in grouped.values() for tag in tags
    ]
    write_json(status_path, status)
    try:
        for image, tags in grouped.items():
            sources = [f"{image}@{digest}" for digest in digests.values()]
            options = [option for tag in tags for option in ("--tag", tag)]
            for key, value in annotations.items():
                options.extend(("--annotation", f"index:{key}={value}"))
            raw = docker("create", "--dry-run", *options, *sources)
            verify_manifest(raw, digests)
            commands.append((image, tags, options + sources))
        for image, tags, arguments in commands:
            for target in status["targets"]:
                if target["tag"] in tags:
                    target["state"] = "unverified"
            write_json(status_path, status)
            docker("create", *arguments)
            index_digest = None
            for tag in tags:
                digest = inspect_digest(tag, digests, annotations)
                require_same_digest(digest, index_digest)
                index_digest = digest
                target = next(
                    target for target in status["targets"] if target["tag"] == tag
                )
                target.update(state="verified", digest=digest)
                write_json(status_path, status)
                print(f"Verified {tag}: linux/amd64, linux/arm64")
            references.append(
                {"repository": image, "digest": index_digest, "platforms": digests}
            )
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        status["state"] = "failed"
        status["error_type"] = type(error).__name__
        # A create may have reached the registry before a transport failure.
        # Unverified targets are unknown; pending targets were never attempted.
        write_json(status_path, status)
        raise
    status["state"] = "verified"
    write_json(status_path, status)
    return references


def main() -> None:
    """Read workflow metadata and emit a service publication artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("digest_directory", type=Path)
    parser.add_argument("--service", choices=("api", "web"))
    parser.add_argument("--descriptor", type=Path)
    parser.add_argument("--status", type=Path)
    args = parser.parse_args()
    if args.descriptor and not args.service:
        parser.error("--service is required when writing a descriptor")
    try:
        references = publish(
            args.digest_directory, json.loads(os.environ["IMAGE_METADATA"]), args.status
        )
        if args.descriptor:
            write_json(
                args.descriptor,
                {
                    "schema_version": 1,
                    "service": args.service,
                    "source": {
                        "sha": os.environ["GITHUB_SHA"],
                        "run_id": os.environ["GITHUB_RUN_ID"],
                        "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
                    },
                    "images": references,
                },
            )
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()

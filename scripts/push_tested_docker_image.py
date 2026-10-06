#!/usr/bin/env python3
"""Export a smoke-tested native image and retry only cached registry transport failures."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from merge_docker_manifests import DIGEST_PATTERN, PLATFORMS, is_transport_failure

RUN_STEP = re.compile(r"^#([0-9]+) \[.*\] RUN(?: |$)", re.MULTILINE)
CACHED_STEP = re.compile(r"^#([0-9]+) CACHED$", re.MULTILINE)
EXPORT_STEP = re.compile(r"^#([0-9]+) exporting to image$", re.MULTILINE)
TERMINAL_ERROR = re.compile(r"^ERROR: (.+)$", re.MULTILINE)


def cached_graph(log: str) -> bool:
    """Require positive evidence that every reported RUN reused the tested cache."""
    runs = set(RUN_STEP.findall(log))
    return bool(runs) and runs <= set(CACHED_STEP.findall(log))


def retryable_export(log: str) -> bool:
    """Distinguish push/OAuth transport failures from dependency or compile errors."""
    errors = TERMINAL_ERROR.findall(log)
    if not errors or not cached_graph(log) or not is_transport_failure(errors[-1]):
        return False
    final = errors[-1].lower()
    if "failed to push " in final:
        return True
    # BuildKit can report exporter OAuth failures without the 'failed to push'
    # wrapper. Require the exporting vertex itself to own the error.
    for step in EXPORT_STEP.findall(log):
        if re.search(rf"^#{step} ERROR: .+$", log, re.MULTILINE):
            return True
    return False


def build_command(
    builder: str, dockerfile: str, images: str, record: dict, metadata: Path
) -> list[str]:
    """Reproduce the loaded image inputs in the same active builder/exporter."""
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+", builder)
        or record.get("service") not in {"api", "web"}
        or record.get("platform") not in PLATFORMS
        or not DIGEST_PATTERN.fullmatch(record.get("config_digest", ""))
    ):
        message = "A successful native production-smoke record and active builder are required"
        raise ValueError(message)
    repositories = images.split(",")
    if not repositories or any(
        not re.fullmatch(r"[a-z0-9][a-z0-9.:/_-]*", image) or "/" not in image
        for image in repositories
    ):
        message = "Configured registry repositories are required"
        raise ValueError(message)
    command = [
        "docker",
        "buildx",
        "build",
        "--builder",
        builder,
        "--file",
        dockerfile,
        "--platform",
        record["platform"],
        "--progress",
        "plain",
        "--provenance=false",
        "--sbom=false",
        "--metadata-file",
        str(metadata),
        "--output",
        f'type=image,"name={images}",push-by-digest=true,name-canonical=true,push=true,oci-mediatypes=true',
    ]
    for variable, option in (
        ("IMAGE_LABELS", "--label"),
        ("IMAGE_ANNOTATIONS", "--annotation"),
        ("IMAGE_BUILD_ARGS", "--build-arg"),
    ):
        for value in os.environ.get(variable, "").splitlines():
            if value.strip():
                command.extend((option, value))
    command.append(".")
    return command


def validate_metadata(metadata: dict, record: dict) -> str:
    """Require the registry export to identify the exact tested image config."""
    digest = metadata.get("containerimage.digest", "")
    if (
        not DIGEST_PATTERN.fullmatch(digest)
        or metadata.get("containerimage.config.digest") != record["config_digest"]
    ):
        message = "Export metadata differs from the successful production-smoke config"
        raise ValueError(message)
    return digest


def push_tested(
    builder: str, dockerfile: str, images: str, record: dict, metadata: Path
) -> str:
    """Retry a proven cached exporter at most twice, preserving all other failures."""
    command = build_command(builder, dockerfile, images, record, metadata)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        metadata.unlink(missing_ok=True)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        log = (result.stdout or "") + (result.stderr or "")
        print(log, end="" if log.endswith("\n") else "\n")
        if result.returncode:
            if attempt == 2 or not retryable_export(log):
                raise subprocess.CalledProcessError(
                    result.returncode,
                    command,
                    output=result.stdout,
                    stderr=result.stderr,
                )
            print(
                f"Cached registry exporter transport failure; retrying ({attempt + 1}/2)",
                file=sys.stderr,
            )
            time.sleep(2**attempt)
            continue
        # Cache misses must not silently turn this exporter into another build.
        if not cached_graph(log):
            message = (
                "Registry export did not prove all RUN steps reused the tested cache"
            )
            raise ValueError(message)
        return validate_metadata(json.loads(metadata.read_text()), record)
    message = "Registry exporter retry loop exhausted"
    raise RuntimeError(message)


def main() -> None:
    """Read existing smoke/metadata inputs and expose only a validated native digest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--builder", required=True)
    parser.add_argument("--dockerfile", required=True)
    parser.add_argument("--images", required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()
    try:
        digest = push_tested(
            args.builder,
            args.dockerfile,
            args.images,
            json.loads(args.record.read_text()),
            args.metadata,
        )
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write(f"digest={digest}\n")
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()

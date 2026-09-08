"""Own private, atomic run manifests and stable blind comparison identities."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

SCHEMA_VERSION = 1
REQUESTED_MODELS = (
    "gemini-3.8-flash",
    "doubao-seed-2-1-turbo-260628",
    "deepseek-v4-flash-0731",
    "qwen3.8-flash",
)


class ArenaError(RuntimeError):
    """Expose an operator-safe error without credentials or course content."""


def utc_now() -> str:
    """Return a UTC timestamp for an artifact, never a local display time."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def stable_id(value: object, *, prefix: str) -> str:
    """Derive a stable private identity from canonical JSON."""
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return prefix + hashlib.sha256(encoded.encode()).hexdigest()[:24]


def private_directory(path: Path) -> Path:
    """Create a private directory without changing an existing parent's mode."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        msg = "Run directories must not be symbolic links"
        raise ArenaError(msg)
    path.chmod(0o700)
    return path


def write_json(path: Path, value: object) -> None:
    """Atomically replace a JSON artifact using owner-only permissions."""
    private_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=".arena-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    """Load an object from a private configuration or manifest."""
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        msg = "Expected a JSON object"
        raise ArenaError(msg)
    return value


def validate_config(config: dict) -> dict:
    """Reject ambiguous model, identity, and execution configuration."""
    result = dict(config)
    phone = result.get("owner_phone")
    if not isinstance(phone, str) or not re.fullmatch(r"\+?\d{7,16}", phone):
        msg = "owner_phone must identify the authorized course owner"
        raise ArenaError(msg)
    models = result.get("models", list(REQUESTED_MODELS))
    if models != list(REQUESTED_MODELS):
        msg = "This arena requires the four explicitly selected model versions"
        raise ArenaError(msg)
    result["models"] = models
    for key, default, minimum, maximum in (
        ("case_count", 12, 2, 100),
        ("smoke_case_count", 2, 1, 2),
        ("concurrency", 2, 1, 4),
        ("worker_timeout_seconds", 1200, 30, 3600),
        ("renderer_timeout_seconds", 300, 30, 1200),
    ):
        value = result.get(key, default)
        if type(value) is not int or not minimum <= value <= maximum:
            msg = f"Invalid {key}"
            raise ArenaError(msg)
        result[key] = value
    if result["smoke_case_count"] > result["case_count"]:
        msg = "The smoke batch cannot exceed the case count"
        raise ArenaError(msg)
    seed = result.get("seed", 20260908)
    if type(seed) is not int:
        msg = "seed must be an integer"
        raise ArenaError(msg)
    result["seed"] = seed
    for key in ("backend_command", "renderer_command"):
        command = result.get(key)
        if command is not None and (
            not isinstance(command, list)
            or not command
            or any(
                not isinstance(item, str) or not item or "\0" in item
                for item in command
            )
        ):
            msg = f"{key} must be an argument array, not shell text"
            raise ArenaError(msg)
    routes = result.get("model_routes", [])
    if routes and (
        not isinstance(routes, list)
        or len(routes) != len(models)
        or any(
            not isinstance(route, str) or route.rsplit("/", 1)[-1] != model
            for route, model in zip(routes, models, strict=True)
        )
    ):
        msg = "model_routes must preserve the requested model versions and order"
        raise ArenaError(msg)
    result.setdefault("variables", {})
    if not isinstance(result["variables"], dict):
        msg = "variables must be an explicit frozen object"
        raise ArenaError(msg)
    result.setdefault("feishu", {"locale": "zh-CN"})
    if not isinstance(result["feishu"], dict):
        msg = "feishu must be an object"
        raise ArenaError(msg)
    result.setdefault("renderer_asset_hosts", [])
    if not isinstance(result["renderer_asset_hosts"], list) or any(
        not isinstance(host, str) or not re.fullmatch(r"[a-zA-Z0-9.-]+", host)
        for host in result["renderer_asset_hosts"]
    ):
        msg = "renderer_asset_hosts must contain explicit hostnames"
        raise ArenaError(msg)
    return result


@contextlib.contextmanager
def run_lock(run_dir: Path) -> Iterator[None]:
    """Prevent simultaneous generators or publishers from mutating one run."""
    private_directory(run_dir)
    descriptor = os.open(run_dir / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            msg = "This run is already active in another process"
            raise ArenaError(msg) from error
        yield
    finally:
        os.close(descriptor)


def artifact_id(case: dict, model: dict) -> str:
    """Bind an output to the frozen case and the exact configured model route."""
    return stable_id(
        [case["input_hash"], case["case_id"], model["model"]], prefix="art_"
    )


def publication_render_fingerprint(artifact_a: dict, artifact_b: dict) -> str:
    """Identify the visible revision without depending on PDF creation metadata."""
    sides = []
    for artifact in (artifact_a, artifact_b):
        render = artifact.get("render", {})
        pages = render.get("pages", [])
        hashes = render.get("sha256", {})
        page_hashes = [hashes.get(page) for page in pages]
        if not page_hashes or any(
            not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
            for value in page_hashes
        ):
            message = "Verified render page hashes are required for publication"
            raise ArenaError(message)
        sides.append(
            {
                "artifact_id": artifact["artifact_id"],
                "input_hash": artifact.get("input_hash"),
                "page_hashes": page_hashes,
                "width": render.get("width"),
                "height": render.get("height"),
                "renderer_version": render.get("renderer_version"),
            }
        )
    return hashlib.sha256(
        json.dumps(sides, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_matchups(
    run_id: str, cases: list[dict], models: list[dict], seed: int
) -> list[dict]:
    """Create all pairs with deterministic, independent A/B assignments."""
    pairs = []
    for case in cases:
        for first, second in combinations(models, 2):
            ids = [artifact_id(case, first), artifact_id(case, second)]
            pair_id = stable_id([run_id, case["case_id"], sorted(ids)], prefix="match_")
            flip = int(hashlib.sha256(f"{seed}:{pair_id}".encode()).hexdigest(), 16) % 2
            if flip:
                ids.reverse()
            pairs.append(
                {
                    "matchup_id": pair_id,
                    "case_id": case["case_id"],
                    "task_description": case.get("task_description", ""),
                    "category": case.get("category", "prose"),
                    "a_artifact_id": ids[0],
                    "b_artifact_id": ids[1],
                }
            )
    return pairs

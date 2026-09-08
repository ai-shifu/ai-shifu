"""Orchestrate isolated generation, local rendering, and resumable publication."""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import re
import subprocess
import sys
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from .scoring import _timestamp, summarize_votes
from .state import (
    ArenaError,
    artifact_id,
    build_matchups,
    publication_render_fingerprint,
    utc_now,
    write_json,
)
from .worker import WORKER_PROTOCOL_VERSION

if TYPE_CHECKING:
    from collections.abc import Callable

REPO_ROOT = Path(__file__).resolve().parents[4]
API_ROOT = REPO_ROOT / "src" / "api"
MAX_WORKER_RESPONSE_BYTES = 64 * 1024 * 1024


def _parse_worker_response(output: str) -> dict:
    response = json.loads(output)
    if not isinstance(response, dict):
        msg = "Worker response is not an object"
        raise TypeError(msg)
    version = response.get("protocol_version", WORKER_PROTOCOL_VERSION)
    if type(version) is not int or version != WORKER_PROTOCOL_VERSION:
        msg = "Worker response has an unsupported protocol version"
        raise ValueError(msg)
    if "error" in response and not isinstance(response["error"], dict):
        msg = "Worker response has an invalid error payload"
        raise ValueError(msg)
    return response


def _worker_response_data(response: dict) -> object:
    """Decode one complete gzip stream without exceeding the private response cap."""
    if "data" not in response:
        msg = "Worker response has no data"
        raise ValueError(msg)
    if "encoding" not in response:
        return response["data"]
    encoded = response["data"]
    if response["encoding"] != "gzip+base64" or not isinstance(encoded, str):
        msg = "Worker response has an unsupported encoding"
        raise ValueError(msg)
    # Allow gzip overhead for an incompressible maximum-size response, while
    # bounding the allocation before base64 decoding untrusted transport data.
    if len(encoded) > ((MAX_WORKER_RESPONSE_BYTES + 1024 * 1024) * 4 // 3 + 4):
        msg = "Worker response exceeds the transport size limit"
        raise ValueError(msg)
    compressed = base64.b64decode(encoded, validate=True)
    decoder = zlib.decompressobj(wbits=31)
    decoded = decoder.decompress(compressed, MAX_WORKER_RESPONSE_BYTES + 1)
    if (
        len(decoded) > MAX_WORKER_RESPONSE_BYTES
        or not decoder.eof
        or decoder.unconsumed_tail
        or decoder.unused_data
    ):
        msg = "Worker response is oversized or is not one complete gzip stream"
        raise ValueError(msg)
    return json.loads(decoded.decode("utf-8"))


class WorkerBackend:
    """Invoke the same checked-in worker locally or through an operator transport."""

    def __init__(self, config: dict, run_dir: Path) -> None:
        """Keep transport configuration separate from frozen run artifacts."""
        self.config = config
        self.run_dir = run_dir

    def call(self, operation: str, **payload: object) -> object:
        """Submit a private JSON request without shell interpolation."""
        command = self.config.get("backend_command") or [
            sys.executable,
            str(API_ROOT / "scripts" / "markdownflow_arena.py"),
            "worker",
        ]
        request = {"operation": operation, "config": self.config, **payload}
        try:
            result = subprocess.run(
                command,
                input=json.dumps(request, ensure_ascii=False),
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
                cwd=API_ROOT,
                timeout=self.config["worker_timeout_seconds"],
            )
        except subprocess.TimeoutExpired as error:
            msg = f"Backend {operation} timed out; paid-call completion may be unknown"
            raise ArenaError(msg) from error
        except UnicodeError as error:
            msg = f"Backend {operation} returned an invalid protocol response"
            raise ArenaError(msg) from error
        try:
            response = _parse_worker_response(result.stdout)
        except (TypeError, ValueError) as error:
            msg = f"Backend {operation} returned an invalid protocol response"
            raise ArenaError(msg) from error
        if result.returncode or response.get("ok") is not True:
            detail = response.get("error", {}).get(
                "message", "Backend operation failed"
            )
            msg = f"{operation}: {detail}"
            raise ArenaError(msg)
        try:
            return _worker_response_data(response)
        except (TypeError, ValueError, binascii.Error, zlib.error) as error:
            msg = f"Backend {operation} returned an invalid protocol response"
            raise ArenaError(msg) from error


class BrowserRenderer:
    """Render a private generated artifact through the pinned frontend packages."""

    def __init__(self, config: dict) -> None:
        """Use the trusted renderer command and static asset allowlist."""
        self.config = config

    def render(self, artifact_path: Path, output_dir: Path) -> dict:
        """Return verified image/PDF paths from a loopback-only browser renderer."""
        command = list(
            self.config.get("renderer_command")
            or [
                "node",
                str(REPO_ROOT / "src/web/scripts/markdownflow-arena/render.mjs"),
            ]
        )
        command.extend(["--input", str(artifact_path), "--output", str(output_dir)])
        for host in self.config["renderer_asset_hosts"]:
            command.extend(["--asset-host", host])
        try:
            process = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
                cwd=REPO_ROOT / "src/web",
                timeout=self.config["renderer_timeout_seconds"],
            )
        except subprocess.TimeoutExpired as error:
            msg = "Rendering timed out"
            raise ArenaError(msg) from error
        try:
            result = json.loads(process.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as error:
            msg = "Renderer did not return a JSON result"
            raise ArenaError(msg) from error
        if process.returncode or result.get("status") != "complete":
            msg = "Renderer could not capture the complete work"
            raise ArenaError(msg)
        pages = result.get("pages")
        if not isinstance(pages, list) or not pages or not result.get("pdf"):
            msg = "Renderer omitted pages or the complete PDF"
            raise ArenaError(msg)
        output_root = output_dir.resolve()
        for file in [*pages, result["pdf"]]:
            path = Path(file)
            if (
                not path.is_absolute()
                or not path.resolve().is_relative_to(output_root)
                or not path.is_file()
            ):
                msg = "Renderer returned an invalid artifact path"
                raise ArenaError(msg)
        return result


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArenaPipeline:
    """Keep each recoverable stage distinct from chargeable generation."""

    def __init__(
        self,
        manifest: dict,
        run_dir: Path,
        backend: object,
        renderer: object,
        publisher: object,
        save: Callable[[], None],
    ) -> None:
        """Bind recoverable stages to one exclusively locked run manifest."""
        self.manifest = manifest
        self.run_dir = run_dir
        self.backend = backend
        self.renderer = renderer
        self.publisher = publisher
        self.save = save

    def initialize(self) -> None:
        """Freeze source and model identities once, and recheck access on every run."""
        state = self.manifest
        config = state["config"]
        self.publisher.preflight()
        if not state.get("cases"):
            result = self.backend.call("snapshot")
            write_json(self.run_dir / "snapshot.json", result["snapshot"])
            state["owner_user_bid"] = result["snapshot"]["owner_user_bid"]
            state["cases"] = result["cases"]
            self.save()
        allowed = set(
            self.backend.call(
                "revalidate",
                owner_user_bid=state["owner_user_bid"],
                cases=state["cases"],
            )
        )
        if allowed != {case["case_id"] for case in state["cases"]}:
            msg = "One or more frozen sources no longer have prompt access"
            raise ArenaError(msg)
        resolved = self.backend.call("resolve_models")
        if state.get("models") and resolved != state["models"]:
            # Display names do not change what a model runs; route IDs do.
            if [(m["requested"], m["model"]) for m in resolved] != [
                (m["requested"], m["model"]) for m in state["models"]
            ]:
                msg = "The frozen model routes changed; create a new run"
                raise ArenaError(msg)
        elif not state.get("models"):
            state["models"] = resolved
        if not state.get("matchups"):
            state["matchups"] = build_matchups(
                state["run_id"], state["cases"], state["models"], config["seed"]
            )
        state["status"] = "running"
        self.save()

    def _generate(self, case: dict, model: dict) -> dict:
        result = self.backend.call("generate", case=case, model=model)
        if not isinstance(result, dict):
            msg = "Worker returned an invalid generation result"
            raise ArenaError(msg)
        if (
            not isinstance(result.get("input_hash"), str)
            or result["input_hash"] != case["input_hash"]
        ):
            msg = "Generated result did not preserve the frozen input"
            raise ArenaError(msg)
        if not isinstance(result.get("status"), str) or result["status"] not in {
            "complete",
            "generation_failed",
            "truncated",
        }:
            msg = "Worker returned an invalid generation status"
            raise ArenaError(msg)
        if (
            not isinstance(result.get("content"), str)
            or not isinstance(result.get("elements"), list)
            or any(not isinstance(element, dict) for element in result["elements"])
            or not isinstance(result.get("metadata"), dict)
        ):
            msg = "Worker returned malformed generation content"
            raise ArenaError(msg)
        # A worker owns generation payload only. Identity, attempt history, and
        # filesystem paths remain bound to the local frozen manifest.
        return copy.deepcopy(
            {
                key: result[key]
                for key in ("status", "input_hash", "content", "elements", "metadata")
            }
        )

    def _persist_artifact(self, artifact: dict) -> Path:
        """Repair an interrupted artifact write from its checkpointed paid result."""
        artifact_key = artifact.get("artifact_id")
        if not isinstance(artifact_key, str) or not re.fullmatch(
            r"art_[a-f0-9]{24}", artifact_key
        ):
            msg = "Artifact identity is not a local arena artifact ID"
            raise ArenaError(msg)
        artifact_root = self.run_dir.resolve() / "artifacts"
        path = artifact_root / artifact_key / "artifact.json"
        if not path.resolve().is_relative_to(artifact_root):
            msg = "Artifact path escapes the private run artifact directory"
            raise ArenaError(msg)
        payload = {
            key: artifact[key]
            for key in (
                "artifact_id",
                "case_id",
                "model",
                "input_hash",
                "content",
                "elements",
                "metadata",
            )
        }
        payload["status"] = artifact["generation_status"]
        write_json(path, payload)
        artifact["artifact_path"] = str(path)
        artifact["artifact_sha256"] = _file_hash(path)
        self.save()
        return path

    def generate(self, cases: list[dict], *, retry_failed: bool = False) -> None:
        """Checkpoint each result; interrupted paid requests require explicit retry."""
        state = self.manifest
        pending = {}
        with ThreadPoolExecutor(max_workers=state["config"]["concurrency"]) as executor:
            for case in cases:
                for model in state["models"]:
                    key = artifact_id(case, model)
                    artifact = state["artifacts"].get(key)
                    if artifact and artifact.get("generation_status") == "complete":
                        continue
                    if artifact and not retry_failed:
                        continue
                    attempts = []
                    if artifact:
                        attempts = [
                            *artifact.get("attempts", []),
                            {
                                key: value
                                for key, value in artifact.items()
                                if key != "attempts"
                            },
                        ]
                    state["artifacts"][key] = {
                        "artifact_id": key,
                        "case_id": case["case_id"],
                        "model": model,
                        "input_hash": case["input_hash"],
                        "status": "generation_unknown",
                        "generation_status": "pending",
                        "started_at": utc_now(),
                        "attempts": attempts,
                    }
                    self.save()
                    pending[executor.submit(self._generate, case, model)] = key
            for future in as_completed(pending):
                key = pending[future]
                artifact = state["artifacts"][key]
                try:
                    result = future.result()
                    for field in ("input_hash", "content", "elements", "metadata"):
                        artifact[field] = result[field]
                    artifact["generation_status"] = result["status"]
                    artifact["status"] = (
                        "generated"
                        if result["status"] == "complete"
                        else result["status"]
                    )
                    # Persist the paid result before any independently retryable file work.
                    self.save()
                    self._persist_artifact(artifact)
                except Exception as error:
                    artifact["status"] = "generation_unknown"
                    artifact["error_type"] = type(error).__name__
                    if isinstance(error, ArenaError):
                        artifact["error"] = str(error)
                artifact["finished_at"] = utc_now()
                self.save()

    def verify_inputs(self, cases: list[dict]) -> None:
        """Require identical initial runtime messages across all successful models."""
        for case in cases:
            artifacts = [
                self.manifest["artifacts"].get(artifact_id(case, model), {})
                for model in self.manifest["models"]
            ]
            successful = [
                item
                for item in artifacts
                if item.get("generation_status") == "complete"
            ]
            hashes = []
            for item in successful:
                requests = item.get("metadata", {}).get("requests", [])
                hashes.append(requests[0].get("messages_hash") if requests else None)
            if successful and (None in hashes or len(set(hashes)) != 1):
                for item in successful:
                    item["status"] = "input_mismatch"
                self.save()
                msg = "Models did not receive identical initial runtime messages"
                raise ArenaError(msg)

    def render(self, cases: list[dict]) -> None:
        """Retry rendering without repeating successful generation."""
        for case in cases:
            for model in self.manifest["models"]:
                artifact = self.manifest["artifacts"].get(artifact_id(case, model), {})
                if artifact.get("generation_status") != "complete":
                    continue
                path = (
                    Path(artifact["artifact_path"])
                    if artifact.get("artifact_path")
                    else self._persist_artifact(artifact)
                )
                if (
                    not path.is_file()
                    or _file_hash(path) != artifact["artifact_sha256"]
                ):
                    msg = "A frozen generated artifact is missing or modified"
                    raise ArenaError(msg)
                if artifact.get("status") == "complete":
                    render = artifact.get("render", {})
                    files = [*render.get("pages", []), render.get("pdf", "")]
                    hashes = render.get("sha256", {})
                    if files and all(
                        Path(file).is_file()
                        and hashes.get(file) == _file_hash(Path(file))
                        for file in files
                    ):
                        continue
                try:
                    artifact["render"] = self.renderer.render(
                        path, path.parent / "render"
                    )
                    render = artifact["render"]
                    render["sha256"] = {
                        file: _file_hash(Path(file))
                        for file in [*render["pages"], render["pdf"]]
                    }
                    artifact["status"] = "complete"
                except Exception as error:
                    artifact["status"] = "render_failed"
                    artifact["error_type"] = type(error).__name__
                    if isinstance(error, ArenaError):
                        artifact["error"] = str(error)
                self.save()

    def publish(self, cases: list[dict]) -> None:
        """Publish only complete pairs after fresh source-access validation."""
        allowed = set(
            self.backend.call(
                "revalidate",
                owner_user_bid=self.manifest["owner_user_bid"],
                cases=cases,
            )
        )
        if allowed != {case["case_id"] for case in cases}:
            msg = "Course prompt access changed before publication"
            raise ArenaError(msg)
        self.publisher.provision(self.manifest["run_id"])
        selected = {case["case_id"] for case in cases}
        for pair in self.manifest["matchups"]:
            if pair["case_id"] not in selected:
                continue
            a = self.manifest["artifacts"].get(pair["a_artifact_id"], {})
            b = self.manifest["artifacts"].get(pair["b_artifact_id"], {})
            if a.get("status") != "complete" or b.get("status") != "complete":
                continue
            fingerprint = publication_render_fingerprint(a, b)
            if (
                pair.get("record_id")
                and _timestamp(pair.get("published_at"))
                and pair.get("publication_render_fingerprint") == fingerprint
            ):
                continue
            # A revision replacement is not reviewable until both sides have
            # been verified remotely. Persist this before any remote write so
            # a failed upload or later summarize cannot count stale votes.
            pair.pop("published_at", None)
            pair.pop("publication_render_fingerprint", None)
            self.save()
            record_id = self.publisher.publish_matchup(pair, a, b)
            # The publisher persists its first fully verified attachment time
            # before returning. Reuse it after interruption, including older
            # manifests that already saved a remote ID without a ready time.
            published_at = self.publisher.get_publication_ready_at(pair["matchup_id"])
            if not isinstance(published_at, str) or _timestamp(published_at) is None:
                msg = "Publisher did not confirm when the complete matchup became reviewable"
                raise ArenaError(msg)
            pair["record_id"] = record_id
            pair["published_at"] = published_at
            pair["publication_render_fingerprint"] = fingerprint
            self.save()

    def run(self, *, smoke_only: bool = False, retry_failed: bool = False) -> dict:
        """Validate the smoke batch before spending on the rest of a round."""
        self.initialize()
        state = self.manifest
        smoke = state["cases"][: state["config"]["smoke_case_count"]]
        stages = [smoke] if smoke_only else [smoke, state["cases"][len(smoke) :]]
        for index, cases in enumerate(stages):
            self.generate(cases, retry_failed=retry_failed)
            self.verify_inputs(cases)
            self.render(cases)
            expected = [
                state["artifacts"].get(artifact_id(case, model), {})
                for case in cases
                for model in state["models"]
            ]
            if index == 0 and any(
                artifact.get("status") != "complete" for artifact in expected
            ):
                state["status"] = "smoke_failed"
                self.save()
                msg = "Smoke generation or rendering failed; inspect private artifacts before retrying"
                raise ArenaError(msg)
            self.publish(cases)
        state["status"] = (
            "smoke_ready"
            if smoke_only
            else "ready"
            if all(
                artifact.get("status") == "complete"
                for artifact in state["artifacts"].values()
            )
            else "partial"
        )
        state["updated_at"] = utc_now()
        self.save()
        return self.summary()

    def summary(self) -> dict:
        """Read append-only votes and publish private aggregate statistics."""
        result = summarize_votes(self.manifest, self.publisher.fetch_votes())
        write_json(self.run_dir / "summary.json", result)
        self.publisher.publish_summary(result)
        self.manifest["last_summary_at"] = utc_now()
        self.save()
        return result

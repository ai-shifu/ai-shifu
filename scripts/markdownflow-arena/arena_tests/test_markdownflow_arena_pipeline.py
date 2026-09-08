# Assertions are pytest checks, never production runtime guards.
# ruff: noqa: S101

"""Exercise resumable local stages without repeating paid model calls."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from markdownflow_arena_lib import pipeline as pipeline_module  # noqa: E402
from markdownflow_arena_lib.pipeline import ArenaPipeline  # noqa: E402
from markdownflow_arena_lib.state import (  # noqa: E402
    REQUESTED_MODELS,
    ArenaError,
    artifact_id,
    read_json,
    run_lock,
    validate_config,
    write_json,
)


class Backend:
    """Track chargeable calls separately from read-only source validation."""

    def __init__(self) -> None:
        """Start with three fixed cases and five successful model routes."""
        self.calls = []
        self.allowed = True
        self.mismatch = False
        self.failed_model = None
        self.cases = [
            {
                "case_id": f"case-{index}",
                "input_hash": f"input-{index}",
                "category": "slides",
                "task_description": "Read the explanation.",
            }
            for index in range(3)
        ]
        self.models = [
            {"requested": model, "model": model} for model in REQUESTED_MODELS
        ]

    def call(self, operation: str, **payload: object) -> object:
        """Record the operation and return a controlled backend result."""
        self.calls.append((operation, payload))
        if operation == "snapshot":
            return {"snapshot": {"owner_user_bid": "owner"}, "cases": self.cases}
        if operation == "revalidate":
            return (
                [case["case_id"] for case in payload["cases"]] if self.allowed else []
            )
        if operation == "resolve_models":
            return self.models
        if operation == "generate":
            case, model = payload["case"], payload["model"]
            messages_hash = model["model"] if self.mismatch else case["input_hash"]
            return {
                "status": "truncated"
                if model["model"] == self.failed_model
                else "complete",
                "input_hash": case["input_hash"],
                "content": "An explanation.",
                "elements": [{"is_marker": True, "content": "<div>Slide</div>"}],
                "metadata": {"requests": [{"messages_hash": messages_hash}]},
            }
        raise AssertionError(operation)


class Renderer:
    """Produce temporary files and simulate a recoverable browser failure."""

    def __init__(self) -> None:
        """Count captures and allow a deterministic render failure."""
        self.calls = 0
        self.fail = False

    def render(self, _artifact: Path, output_dir: Path) -> dict:
        """Capture a controlled local result without invoking a browser."""
        self.calls += 1
        if self.fail:
            msg = "Test renderer failure"
            raise ArenaError(msg)
        output_dir.mkdir(parents=True, exist_ok=True)
        page, pdf = output_dir / "page-001.png", output_dir / "complete.pdf"
        page.write_bytes(b"image")
        pdf.write_bytes(b"pdf")
        return {
            "status": "complete",
            "pages": [str(page)],
            "pdf": str(pdf),
            "width": 1200,
            "height": 1600,
            "renderer_version": "fixture-v1",
        }


@pytest.mark.parametrize("timeout", [30, 300, 1200])
def test_browser_renderer_receives_pipeline_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: int
) -> None:
    """Keep the browser deadline aligned with the operator's process deadline."""
    artifact_path, output_dir = tmp_path / "artifact.json", tmp_path / "render"
    result = Renderer().render(artifact_path, output_dir)

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        assert command[command.index("--timeout-seconds") + 1] == str(timeout)
        assert kwargs["timeout"] == timeout
        assert (
            command[command.index("--asset-url") + 1]
            == "https://cdn.example/fixed.png?v=1"
        )
        assert "--asset-host" not in command
        return subprocess.CompletedProcess(
            command, 0, stdout="Diagnostic line\n" + json.dumps(result) + "\n\n"
        )

    monkeypatch.setattr(pipeline_module.subprocess, "run", run)
    renderer = pipeline_module.BrowserRenderer(
        {
            "renderer_asset_urls": ["https://cdn.example/fixed.png?v=1"],
            "renderer_timeout_seconds": timeout,
        }
    )
    assert renderer.render(artifact_path, output_dir) == result


@pytest.fixture
def arena(tmp_path: Path) -> ArenaPipeline:
    """Provide arena for the isolated test fixture."""
    manifest = {
        "run_id": "test-run",
        "config": validate_config({"owner_phone": "10000000000", "case_count": 3}),
        "cases": [],
        "models": [],
        "artifacts": {},
    }
    return ArenaPipeline(
        manifest,
        tmp_path,
        Backend(),
        Renderer(),
        lambda: write_json(tmp_path / "manifest.json", manifest),
    )


def test_smoke_then_resume_does_not_regenerate(arena: ArenaPipeline) -> None:
    """Verify smoke then resume does not regenerate."""
    arena.run(smoke_only=True)
    assert arena.manifest["report"]["complete_count"] == 10
    frozen = copy.deepcopy(arena.manifest["cases"])
    arena.run()
    assert arena.manifest["report"]["complete_count"] == 15
    assert arena.manifest["cases"] == frozen
    arena.run()
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 15
    assert arena.renderer.calls == 15


def test_renderer_failure_resumes_without_chargeable_retries(
    arena: ArenaPipeline,
) -> None:
    """Verify renderer failure resumes without chargeable retries."""
    arena.renderer.fail = True
    with pytest.raises(ArenaError):
        arena.run(smoke_only=True)
    arena.renderer.fail = False
    arena.run(smoke_only=True)
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 10
    assert arena.manifest["report"]["complete_count"] == 10


def test_report_failure_resumes_without_chargeable_retries(
    arena: ArenaPipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify report failure resumes without chargeable retries."""
    original = pipeline_module.write_report

    def fail(*_args: object) -> dict:
        message = "Local report failure"
        raise ArenaError(message)

    monkeypatch.setattr(pipeline_module, "write_report", fail)
    with pytest.raises(ArenaError, match="Local report failure"):
        arena.run(smoke_only=True)
    monkeypatch.setattr(pipeline_module, "write_report", original)
    arena.run(smoke_only=True)
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 10
    assert arena.renderer.calls == 10


def test_failed_first_artifact_write_recovers_from_saved_manifest(
    arena: ArenaPipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new process repairs paid output files without another generation call."""
    original_write = pipeline_module.write_json
    failed_paths = []

    def fail_artifact_write(path: Path, value: object) -> None:
        if path.name == "artifact.json":
            failed_paths.append(path)
            message = "Simulated artifact storage interruption"
            raise OSError(message)
        original_write(path, value)

    monkeypatch.setattr(pipeline_module, "write_json", fail_artifact_write)
    arena.initialize()
    smoke = arena.manifest["cases"][:2]
    arena.generate(smoke)
    saved = read_json(arena.run_dir / "manifest.json")
    assert len(failed_paths) == 10
    assert all(
        item["generation_status"] == "complete" for item in saved["artifacts"].values()
    )
    assert all(
        item["content"] and not item.get("artifact_path")
        for item in saved["artifacts"].values()
    )
    monkeypatch.setattr(pipeline_module, "write_json", original_write)
    resumed = ArenaPipeline(
        saved,
        arena.run_dir,
        arena.backend,
        arena.renderer,
        lambda: write_json(arena.run_dir / "manifest.json", saved),
    )
    resumed.run(smoke_only=True)
    assert sum(operation == "generate" for operation, _ in arena.backend.calls) == 10
    assert resumed.manifest["report"]["complete_count"] == 10
    assert all(
        Path(item["artifact_path"]).is_file() for item in saved["artifacts"].values()
    )


@pytest.mark.parametrize("attack", ["relative_path", "absolute_path", "other_identity"])
def test_worker_generation_cannot_override_local_identity_history_or_paths(
    arena: ArenaPipeline, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    """Verify worker generation cannot override local identity history or paths."""
    arena.initialize()
    case, model = arena.manifest["cases"][0], arena.manifest["models"][0]
    trusted_id = artifact_id(case, model)
    previous = {
        "artifact_id": trusted_id,
        "case_id": case["case_id"],
        "model": model,
        "generation_status": "truncated",
        "content": "Previous paid output",
        "attempts": [{"content": "Earlier paid output"}],
    }
    arena.manifest["artifacts"][trusted_id] = copy.deepcopy(previous)
    outside = arena.run_dir.parent / f"{arena.run_dir.name}-untrusted-output"
    malicious_id = {
        "relative_path": f"../../{outside.name}",
        "absolute_path": str(outside),
        "other_identity": "art_" + "0" * 24,
    }[attack]
    original_call = arena.backend.call

    def forged_result(operation: str, **payload: object) -> object:
        result = original_call(operation, **payload)
        if operation == "generate":
            result.update(
                {
                    "artifact_id": malicious_id,
                    "case_id": "different-case",
                    "model": {"model": "different-model"},
                    "artifact_path": str(outside / "artifact.json"),
                    "artifact_sha256": "untrusted",
                    "render": {"pdf": str(outside / "malicious.pdf")},
                    "generation_status": "untrusted",
                    "attempts": [{"content": "Overwrite local audit history"}],
                }
            )
        return result

    monkeypatch.setattr(arena.backend, "call", forged_result)
    arena.generate([case], retry_failed=True)
    artifact = arena.manifest["artifacts"][trusted_id]
    assert artifact["artifact_id"] == trusted_id
    assert artifact["case_id"] == case["case_id"]
    assert artifact["model"] == model
    assert artifact["generation_status"] == "complete"
    assert artifact["attempts"] == [
        *previous["attempts"],
        {key: value for key, value in previous.items() if key != "attempts"},
    ]
    assert "render" not in artifact
    expected = arena.run_dir / "artifacts" / trusted_id / "artifact.json"
    assert Path(artifact["artifact_path"]) == expected
    assert read_json(expected)["artifact_id"] == trusted_id
    assert not outside.exists()
    assert len(list((arena.run_dir / "artifacts").glob("*/artifact.json"))) == 5


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", ["complete"]),
        ("input_hash", 123),
        ("content", None),
        ("elements", {}),
        ("elements", ["not-an-element-object"]),
        ("metadata", []),
    ],
)
def test_generation_accepts_only_typed_payload_fields(
    arena: ArenaPipeline, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    """Verify generation accepts only typed payload fields."""
    arena.initialize()
    case, model = arena.manifest["cases"][0], arena.manifest["models"][0]
    result = arena.backend.call("generate", case=case, model=model)
    result[field] = value
    monkeypatch.setattr(arena.backend, "call", lambda *_args, **_kwargs: result)
    with pytest.raises(ArenaError, match=r"Worker|frozen input"):
        arena._generate(case, model)
    assert not (arena.run_dir / "artifacts").exists()


@pytest.mark.parametrize("kind", ["relative", "absolute", "invalid_format"])
def test_artifact_persistence_rejects_nonlocal_ids_before_any_write(
    arena: ArenaPipeline, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """Verify artifact persistence rejects nonlocal ids before any write."""
    outside = arena.run_dir.parent / f"{arena.run_dir.name}-outside"
    value = {
        "relative": f"../../{outside.name}",
        "absolute": str(outside),
        "invalid_format": "art_not-a-valid-id",
    }[kind]
    writes = []
    monkeypatch.setattr(
        pipeline_module, "write_json", lambda *args: writes.append(args)
    )
    with pytest.raises(ArenaError, match="artifact ID"):
        arena._persist_artifact({"artifact_id": value})
    assert writes == []
    assert not outside.exists()


@pytest.mark.parametrize("symlink_level", ["artifacts", "artifact"])
def test_artifact_persistence_rejects_symlink_escape_before_any_write(
    arena: ArenaPipeline, monkeypatch: pytest.MonkeyPatch, symlink_level: str
) -> None:
    """Verify artifact persistence rejects symlink escape before any write."""
    key = "art_" + "a" * 24
    outside = arena.run_dir.parent / f"{arena.run_dir.name}-outside"
    outside.mkdir()
    artifacts = arena.run_dir / "artifacts"
    if symlink_level == "artifacts":
        artifacts.symlink_to(outside, target_is_directory=True)
    else:
        artifacts.mkdir()
        (artifacts / key).symlink_to(outside, target_is_directory=True)
    writes = []
    monkeypatch.setattr(
        pipeline_module, "write_json", lambda *args: writes.append(args)
    )
    with pytest.raises(ArenaError, match="escapes"):
        arena._persist_artifact({"artifact_id": key})
    assert writes == []
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    "failure", [ArenaError("Contract failure"), ValueError("Private provider output")]
)
def test_cli_failure_reports_resumable_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: Exception,
) -> None:
    """Operators can resume a failed run using the emitted private directory."""
    import markdownflow_arena

    config = tmp_path / "config.json"
    write_json(config, {"owner_phone": "10000000000"})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "markdownflow_arena",
            "run",
            "--config",
            str(config),
            "--run-root",
            str(tmp_path),
        ],
    )

    def fail_run(_self: ArenaPipeline, **_options: bool) -> dict:
        raise failure

    monkeypatch.setattr(ArenaPipeline, "run", fail_run)
    assert markdownflow_arena.main() == 1
    result = json.loads(capsys.readouterr().err)
    assert result["ok"] is False
    run_directory = Path(result["run_directory"])
    assert run_directory.is_relative_to(tmp_path)
    assert (run_directory / "manifest.json").is_file()
    assert read_json(run_directory / "manifest.json")["last_failure_at"].endswith("Z")
    assert "Private provider output" not in json.dumps(result)


def test_permission_revocation_stops_all_new_work(arena: ArenaPipeline) -> None:
    """Verify permission revocation stops all new work."""
    arena.run(smoke_only=True)
    arena.backend.allowed = False
    with pytest.raises(ArenaError, match="prompt access"):
        arena.run()
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 10
    assert arena.manifest["report"]["complete_count"] == 10


def test_failed_smoke_and_input_mismatch_never_publish(arena: ArenaPipeline) -> None:
    """Verify failed smoke and input mismatch never publish."""
    arena.backend.failed_model = REQUESTED_MODELS[0]
    with pytest.raises(ArenaError, match="Smoke"):
        arena.run()
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 10
    arena.backend.failed_model = None
    arena.backend.mismatch = True
    with pytest.raises(ArenaError, match="identical"):
        arena.run(retry_failed=True)


def test_modified_render_is_rebuilt_without_generation(arena: ArenaPipeline) -> None:
    """Verify modified render is rebuilt without generation."""
    arena.run(smoke_only=True)
    artifact = next(iter(arena.manifest["artifacts"].values()))
    Path(artifact["render"]["pages"][0]).write_bytes(b"modified")
    arena.run(smoke_only=True)
    assert arena.renderer.calls == 11
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 10


def test_explicit_retry_retains_failed_attempts(arena: ArenaPipeline) -> None:
    """Verify explicit retry retains failed attempts."""
    arena.backend.failed_model = REQUESTED_MODELS[0]
    with pytest.raises(ArenaError, match="Smoke"):
        arena.run(smoke_only=True)
    arena.backend.failed_model = None
    arena.run(smoke_only=True, retry_failed=True)
    retried = [
        item for item in arena.manifest["artifacts"].values() if item.get("attempts")
    ]
    assert len(retried) == 2
    assert all(
        item["attempts"][0]["generation_status"] == "truncated" for item in retried
    )
    assert all(item["attempts"][0]["content"] == "An explanation." for item in retried)
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 12


def test_private_atomic_state_and_exclusive_lock(tmp_path: Path) -> None:
    """Verify private atomic state and exclusive lock."""
    path = tmp_path / "private" / "manifest.json"
    write_json(path, {"frozen": True})
    assert read_json(path) == {"frozen": True}
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    with (
        run_lock(path.parent),
        pytest.raises(ArenaError, match="already active"),
        run_lock(path.parent),
    ):
        pass


def test_exact_versions_are_required() -> None:
    """Verify exact versions are required."""
    with pytest.raises(ArenaError, match="five explicitly"):
        validate_config({"owner_phone": "10000000000", "models": ["gemini-3.7-flash"]})
    with pytest.raises(ArenaError, match="preserve"):
        validate_config({"owner_phone": "10000000000", "model_routes": ["wrong"]})


def test_no_slides_output_is_not_rendered_or_retried(arena: ArenaPipeline) -> None:
    """Verify no slides output is not rendered or retried."""
    arena.initialize()
    arena.generate(arena.manifest["cases"][:2])
    artifact = next(iter(arena.manifest["artifacts"].values()))
    artifact["elements"] = []
    arena.render(arena.manifest["cases"][:2])
    assert artifact["status"] == "no_slides"
    assert arena.renderer.calls == 9
    arena.run(smoke_only=True)
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 10
    assert arena.manifest["report"]["unavailable_count"] == 6


def test_report_only_does_not_call_backend(arena: ArenaPipeline) -> None:
    """Verify report only does not call backend."""
    arena.run(smoke_only=True)
    before = list(arena.backend.calls)
    arena.report()
    assert arena.backend.calls == before


@pytest.mark.parametrize(
    "value",
    [
        "cdn.example",
        "http://cdn.example/a.png",
        "https://u:p@cdn.example/a",
        "https://cdn.example/a#fragment",
        "https://cdn.example:444/a",
        "https://cdn.example:bad/a",
        42,
    ],
)
def test_asset_urls_reject_unsafe_configuration(value: object) -> None:
    """Fail closed for non-HTTPS or ambiguous operator asset entries."""
    with pytest.raises(ArenaError, match="renderer_asset_urls"):
        validate_config({"owner_phone": "10000000000", "renderer_asset_urls": [value]})


def test_legacy_asset_hosts_require_explicit_url_migration() -> None:
    """Keep offline manifests resumable without accepting broad network access."""
    config = {"owner_phone": "10000000000", "renderer_asset_hosts": []}
    assert validate_config(config)["renderer_asset_urls"] == []
    config["renderer_asset_hosts"] = ["cdn.example"]
    with pytest.raises(ArenaError, match="exact renderer_asset_urls"):
        validate_config(config)


@pytest.mark.parametrize(
    "url", ["https://CDN.example:443/image.png?v=1", "https://cdn.example"]
)
def test_renderer_can_normalize_accepted_asset_urls(url: str) -> None:
    """Retain valid operator URLs for Chromium-compatible canonical matching."""
    config = validate_config(
        {"owner_phone": "10000000000", "renderer_asset_urls": [url]}
    )
    assert config["renderer_asset_urls"] == [url]

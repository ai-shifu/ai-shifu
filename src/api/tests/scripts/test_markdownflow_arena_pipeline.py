"""Exercise resumable external stages and first-reviewer vote contracts."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from markdownflow_arena_lib import pipeline as pipeline_module  # noqa: E402
from markdownflow_arena_lib.pipeline import ArenaPipeline  # noqa: E402
from markdownflow_arena_lib.scoring import summarize_votes  # noqa: E402
from markdownflow_arena_lib.state import (  # noqa: E402
    REQUESTED_MODELS,
    ArenaError,
    build_matchups,
    publication_render_fingerprint,
    read_json,
    run_lock,
    validate_config,
    write_json,
)


class Backend:
    """Track chargeable calls separately from read-only source validation."""

    def __init__(self) -> None:
        """Start with three fixed cases and four successful model routes."""
        self.calls = []
        self.allowed = True
        self.mismatch = False
        self.failed_model = None
        self.cases = [
            {
                "case_id": f"case-{index}",
                "input_hash": f"input-{index}",
                "category": "prose",
                "task_description": "Read the explanation.",
            }
            for index in range(3)
        ]
        self.models = [
            {"requested": model, "model": model} for model in REQUESTED_MODELS
        ]

    def call(self, operation: str, **payload: object) -> object:
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
                "elements": [],
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


class Publisher:
    """Remember remote records independently of local process recovery."""

    def __init__(self) -> None:
        """Keep a fake remote state independently of local manifest writes."""
        self.records = {}
        self.ready_at = {}
        self.render_fingerprints = {}
        self.upload_calls = 0
        self.fail_upload = False
        self.fail_summary = False

    def preflight(self) -> None:
        pass

    def provision(self, _run_id: str) -> dict:
        return {}

    def publish_matchup(self, pair: dict, _a: dict, _b: dict) -> str:
        if self.fail_upload:
            msg = "Test upload failure"
            raise ArenaError(msg)
        key = pair["matchup_id"]
        self.records.setdefault(key, f"rec-{len(self.records)}")
        fingerprint = publication_render_fingerprint(_a, _b)
        if self.render_fingerprints.get(key) != fingerprint:
            self.upload_calls += 1
            self.ready_at[key] = (
                "1970-01-01T00:00:10Z"
                if key in self.render_fingerprints
                else "1970-01-01T00:00:00Z"
            )
            self.render_fingerprints[key] = fingerprint
        return self.records[key]

    def get_publication_ready_at(self, matchup_id: str) -> str | None:
        return self.ready_at.get(matchup_id)

    def fetch_votes(self) -> list:
        return []

    def publish_summary(self, _summary: dict) -> None:
        if self.fail_summary:
            msg = "Test summary failure"
            raise ArenaError(msg)


@pytest.fixture
def arena(tmp_path: Path) -> ArenaPipeline:
    manifest = {
        "run_id": "test-run",
        "config": validate_config({"owner_phone": "10000000000", "case_count": 3}),
        "cases": [],
        "models": [],
        "artifacts": {},
        "matchups": [],
        "feishu": {},
    }
    return ArenaPipeline(
        manifest,
        tmp_path,
        Backend(),
        Renderer(),
        Publisher(),
        lambda: write_json(tmp_path / "manifest.json", manifest),
    )


def test_smoke_then_resume_does_not_regenerate_or_remap(arena: ArenaPipeline) -> None:
    arena.run(smoke_only=True)
    assert len(arena.publisher.records) == 12
    frozen = copy.deepcopy(arena.manifest["matchups"])
    arena.run()
    assert len(arena.publisher.records) == 18
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 12
    assert arena.renderer.calls == 12
    assert [
        {
            k: v
            for k, v in pair.items()
            if k not in {"record_id", "published_at", "publication_render_fingerprint"}
        }
        for pair in frozen
    ] == [
        {
            k: v
            for k, v in pair.items()
            if k not in {"record_id", "published_at", "publication_render_fingerprint"}
        }
        for pair in arena.manifest["matchups"]
    ]
    arena.run()
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 12
    assert arena.renderer.calls == 12


@pytest.mark.parametrize("stage", ["renderer", "upload", "summary"])
def test_stage_failure_resumes_without_chargeable_retries(
    arena: ArenaPipeline, stage: str
) -> None:
    if stage == "renderer":
        arena.renderer.fail = True
    else:
        setattr(arena.publisher, f"fail_{stage}", True)
    with pytest.raises(ArenaError):
        arena.run(smoke_only=True)
    arena.renderer.fail = False
    arena.publisher.fail_upload = arena.publisher.fail_summary = False
    arena.run(smoke_only=True)
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 8
    assert len(arena.publisher.records) == 12


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
    assert len(failed_paths) == 8
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
        arena.publisher,
        lambda: write_json(arena.run_dir / "manifest.json", saved),
    )
    resumed.run(smoke_only=True)
    assert sum(operation == "generate" for operation, _ in arena.backend.calls) == 8
    assert len(arena.publisher.records) == 12
    assert all(
        Path(item["artifact_path"]).is_file() for item in saved["artifacts"].values()
    )


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
    from markdownflow_arena_lib import feishu

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
    monkeypatch.setattr(feishu, "FeishuPublisher", lambda *_args: Publisher())

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
    arena.run(smoke_only=True)
    arena.backend.allowed = False
    with pytest.raises(ArenaError, match="prompt access"):
        arena.run()
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 8
    assert len(arena.publisher.records) == 12


def test_failed_smoke_and_input_mismatch_never_publish(arena: ArenaPipeline) -> None:
    arena.backend.failed_model = REQUESTED_MODELS[0]
    with pytest.raises(ArenaError, match="Smoke"):
        arena.run()
    assert not arena.publisher.records
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 8
    arena.backend.failed_model = None
    arena.backend.mismatch = True
    with pytest.raises(ArenaError, match="identical"):
        arena.run(retry_failed=True)
    assert not arena.publisher.records


def test_modified_render_is_rebuilt_without_generation(arena: ArenaPipeline) -> None:
    arena.run(smoke_only=True)
    artifact = next(iter(arena.manifest["artifacts"].values()))
    Path(artifact["render"]["pages"][0]).write_bytes(b"modified")
    arena.run(smoke_only=True)
    assert arena.renderer.calls == 9
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 8


def test_explicit_retry_retains_failed_attempts(arena: ArenaPipeline) -> None:
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
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 10


def test_first_valid_vote_per_person_and_matchup(arena: ArenaPipeline) -> None:
    arena.run(smoke_only=True)
    pairs = arena.manifest["matchups"][:2]
    rows = []
    for index, (person, matchup, choice, time) in enumerate(
        [
            ("one", 0, "a", 3),
            ("two", 0, "b", 2),
            ("one", 0, "tie", 1),
            ("one", 1, "both_bad", 4),
            ("", 0, "a", 5),
            ("one", 0, "a", True),
        ]
    ):
        rows.append(
            {
                "vote_id": str(index),
                "reviewer_id": person,
                "created_at": time,
                "matchup_record_id": pairs[matchup]["record_id"],
                "choice": choice,
            }
        )
    rows.append({**rows[0], "vote_id": "invalid-run", "run_id": "another-run"})
    result = summarize_votes(arena.manifest, rows)
    assert result["valid_vote_count"] == 3
    assert result["rejected_vote_count"] == 4
    assert {row["vote_id"] for row in result["accepted_votes"]} == {"1", "2", "3"}
    first_pair = pairs[0]
    model_a = arena.manifest["artifacts"][first_pair["a_artifact_id"]]["model"]["model"]
    first_stats = next(row for row in result["models"] if row["model"] == model_a)
    assert first_stats["ties"] == 1
    assert first_stats["losses"] == 1
    assert first_stats["win_rate"] == 0.25


def test_first_valid_vote_ignores_clicks_before_all_artwork_is_ready(
    arena: ArenaPipeline,
) -> None:
    arena.run(smoke_only=True)
    pair = arena.manifest["matchups"][0]
    pair["published_at"] = "1970-01-01T00:00:03Z"
    votes = [
        {
            "vote_id": vote_id,
            "reviewer_id": "reviewer",
            "created_at": when,
            "matchup_record_id": pair["record_id"],
            "choice": choice,
        }
        for vote_id, when, choice in [
            ("early-incomplete", 1, "a"),
            ("first-ready", 3, "b"),
            ("later-duplicate", 4, "tie"),
        ]
    ]
    result = summarize_votes(arena.manifest, votes)
    assert result["accepted_votes"] == [
        {
            "vote_id": "first-ready",
            "matchup_id": pair["matchup_id"],
            "choice": "b",
        }
    ]
    assert result["rejected_votes"] == [
        {"vote_id": "early-incomplete", "reason": "invalid"},
        {"vote_id": "later-duplicate", "reason": "duplicate"},
    ]


@pytest.mark.parametrize(
    "condition", ["unpublished", "missing_ready_time", "wrong_record", "wrong_matchup"]
)
def test_votes_require_a_fully_published_exact_record_mapping(
    arena: ArenaPipeline, condition: str
) -> None:
    arena.run(smoke_only=True)
    pair = arena.manifest["matchups"][0]
    vote = {
        "vote_id": "vote",
        "reviewer_id": "reviewer",
        "created_at": 5,
        "matchup_id": pair["matchup_id"],
        "matchup_record_id": pair["record_id"],
        "choice": "a",
    }
    if condition == "unpublished":
        pair.pop("record_id")
    elif condition == "missing_ready_time":
        pair.pop("published_at")
    elif condition == "wrong_record":
        vote["matchup_record_id"] = "another-record"
    else:
        vote["matchup_id"] = "another-matchup"
    result = summarize_votes(arena.manifest, [vote])
    assert result["valid_vote_count"] == 0
    assert result["rejected_votes"] == [{"vote_id": "vote", "reason": "invalid"}]


@pytest.mark.parametrize("record_saved", [False, True])
def test_resume_recovers_original_ready_time_after_partial_publication_checkpoint(
    arena: ArenaPipeline, record_saved: bool
) -> None:
    arena.run(smoke_only=True)
    pair = arena.manifest["matchups"][0]
    original_time = pair.pop("published_at")
    original_record = pair["record_id"]
    if not record_saved:
        pair.pop("record_id")
    calls_before = sum(op == "generate" for op, _ in arena.backend.calls)
    arena.run(smoke_only=True)
    assert pair["record_id"] == original_record
    assert pair["published_at"] == original_time
    assert len(arena.publisher.records) == 12
    assert sum(op == "generate" for op, _ in arena.backend.calls) == calls_before
    arena.run(smoke_only=True)
    assert pair["published_at"] == original_time


def test_publication_without_confirmed_ready_time_is_not_marked_published(
    arena: ArenaPipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        arena.publisher, "get_publication_ready_at", lambda _matchup_id: None
    )
    with pytest.raises(ArenaError, match="became reviewable"):
        arena.run(smoke_only=True)
    assert all(not pair.get("record_id") for pair in arena.manifest["matchups"])


def test_changed_render_updates_existing_matchups_and_invalidates_previous_votes(
    arena: ArenaPipeline,
) -> None:
    arena.run(smoke_only=True)
    pair = arena.manifest["matchups"][0]
    original_record = pair["record_id"]
    original_fingerprint = pair["publication_render_fingerprint"]
    artifact = arena.manifest["artifacts"][pair["a_artifact_id"]]
    page = artifact["render"]["pages"][0]
    Path(page).write_bytes(b"corrected visible content")
    artifact["render"]["sha256"][page] = pipeline_module._file_hash(Path(page))
    vote = {
        "vote_id": "old-revision",
        "reviewer_id": "reviewer",
        "created_at": 1,
        "matchup_record_id": original_record,
        "choice": "a",
    }
    # A standalone summary between local re-render and remote publication must
    # already reject votes attached to the previous visual revision.
    assert summarize_votes(arena.manifest, [vote])["valid_vote_count"] == 0
    generated = sum(op == "generate" for op, _ in arena.backend.calls)
    upload_calls = arena.publisher.upload_calls
    arena.publish(arena.manifest["cases"][:2])
    assert pair["record_id"] == original_record
    assert pair["publication_render_fingerprint"] != original_fingerprint
    assert pair["published_at"] == "1970-01-01T00:00:10Z"
    assert len(arena.publisher.records) == 12
    assert arena.publisher.upload_calls == upload_calls + 3
    current_vote = {**vote, "vote_id": "new-revision", "created_at": 11, "choice": "b"}
    result = summarize_votes(arena.manifest, [vote, current_vote])
    assert result["accepted_votes"] == [
        {
            "vote_id": "new-revision",
            "matchup_id": pair["matchup_id"],
            "choice": "b",
        }
    ]
    arena.run(smoke_only=True)
    assert arena.publisher.upload_calls == upload_calls + 3
    assert sum(op == "generate" for op, _ in arena.backend.calls) == generated


def test_pdf_metadata_change_does_not_republish_or_reset_valid_votes(
    arena: ArenaPipeline,
) -> None:
    arena.run(smoke_only=True)
    pair = arena.manifest["matchups"][0]
    artifact = arena.manifest["artifacts"][pair["a_artifact_id"]]
    original = copy.deepcopy(pair)
    pdf = artifact["render"]["pdf"]
    Path(pdf).write_bytes(b"same rendered images with new PDF creation timestamp")
    artifact["render"]["sha256"][pdf] = pipeline_module._file_hash(Path(pdf))
    uploads = arena.publisher.upload_calls
    arena.publish(arena.manifest["cases"][:2])
    assert pair == original
    assert arena.publisher.upload_calls == uploads
    result = summarize_votes(
        arena.manifest,
        [
            {
                "vote_id": "still-valid",
                "reviewer_id": "reviewer",
                "created_at": 1,
                "matchup_record_id": pair["record_id"],
                "choice": "a",
            }
        ],
    )
    assert result["valid_vote_count"] == 1


def test_failed_revision_upload_durably_invalidates_ready_state_before_retry(
    arena: ArenaPipeline,
) -> None:
    arena.run(smoke_only=True)
    pair = arena.manifest["matchups"][0]
    original_record = pair["record_id"]
    artifact = arena.manifest["artifacts"][pair["a_artifact_id"]]
    page = artifact["render"]["pages"][0]
    Path(page).write_bytes(b"replacement revision")
    artifact["render"]["sha256"][page] = pipeline_module._file_hash(Path(page))
    arena.publisher.fail_upload = True
    with pytest.raises(ArenaError, match="upload failure"):
        arena.publish(arena.manifest["cases"][:2])
    persisted_pair = read_json(arena.run_dir / "manifest.json")["matchups"][0]
    assert persisted_pair["record_id"] == original_record
    assert "published_at" not in persisted_pair
    assert "publication_render_fingerprint" not in persisted_pair
    arena.publisher.fail_upload = False
    arena.run(smoke_only=True)
    assert pair["record_id"] == original_record
    assert pair["published_at"] == "1970-01-01T00:00:10Z"
    assert sum(op == "generate" for op, _ in arena.backend.calls) == 8


@pytest.mark.parametrize(
    "changed_field",
    ["page_order", "page_hash", "width", "height", "renderer_version", "input_hash"],
)
def test_publication_fingerprint_covers_visible_render_and_input_identity(
    arena: ArenaPipeline, changed_field: str
) -> None:
    arena.run(smoke_only=True)
    pair = arena.manifest["matchups"][0]
    original_a = copy.deepcopy(arena.manifest["artifacts"][pair["a_artifact_id"]])
    original_b = arena.manifest["artifacts"][pair["b_artifact_id"]]
    original_a["render"]["pages"].append("/synthetic/second.png")
    original_a["render"]["sha256"]["/synthetic/second.png"] = "2" * 64
    changed = copy.deepcopy(original_a)
    if changed_field == "page_order":
        changed["render"]["pages"].reverse()
    elif changed_field == "page_hash":
        changed["render"]["sha256"][changed["render"]["pages"][0]] = "3" * 64
    elif changed_field == "input_hash":
        changed["input_hash"] = "changed-input"
    elif changed_field in {"width", "height"}:
        changed["render"][changed_field] += 1
    else:
        changed["render"]["renderer_version"] = "fixture-v2"
    assert publication_render_fingerprint(original_a, original_b) != (
        publication_render_fingerprint(changed, original_b)
    )


def test_private_atomic_state_and_exclusive_lock(tmp_path: Path) -> None:
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


def test_exact_versions_and_pair_count_are_stable() -> None:
    with pytest.raises(ArenaError, match="four explicitly"):
        validate_config({"owner_phone": "10000000000", "models": ["gemini-3.7-flash"]})
    with pytest.raises(ArenaError, match="preserve"):
        validate_config({"owner_phone": "10000000000", "model_routes": ["wrong"]})
    backend = Backend()
    pairs = build_matchups("run", backend.cases, backend.models, 123)
    assert len(pairs) == 18
    assert pairs == build_matchups("run", backend.cases, backend.models, 123)

"""Keep worker authorization bound to the configured owner and errors private."""

from __future__ import annotations

import base64
import gzip
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask import Flask

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from markdownflow_arena_lib import engine, pipeline, source, worker  # noqa: E402
from markdownflow_arena_lib.state import REQUESTED_MODELS, ArenaError  # noqa: E402


@pytest.mark.parametrize("operation", ["generate", "revalidate"])
def test_worker_rejects_frozen_identity_that_differs_from_configured_phone(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forged or stale case owner never reaches permission checks or generation."""
    from flaskr.api import langfuse

    app = Flask(__name__)
    monkeypatch.setattr(worker, "build_app", lambda _config: app)
    monkeypatch.setattr(langfuse, "init_langfuse", lambda _app: None)
    lookup = Mock(return_value="configured-owner")
    revalidate = Mock(return_value={"case"})
    generate = Mock(return_value={"status": "complete"})
    monkeypatch.setattr(source, "resolve_owner_user_bid", lookup)
    monkeypatch.setattr(source, "revalidate_sources", revalidate)
    monkeypatch.setattr(engine, "generate_case", generate)
    request = {
        "operation": operation,
        "config": {"owner_phone": "10000000000"},
        "owner_user_bid": "another-owner",
        "cases": [],
        "case": {"owner_user_bid": "another-owner", "case_id": "case"},
        "model": {"requested": REQUESTED_MODELS[0], "model": REQUESTED_MODELS[0]},
    }
    with pytest.raises(ArenaError, match="identity"):
        worker.execute(request)
    lookup.assert_called_once_with(app, "10000000000")
    revalidate.assert_not_called()
    generate.assert_not_called()


def test_worker_generates_only_after_configured_owner_and_prompt_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The accepted path uses the resolved owner and exact frozen route."""
    from flaskr.api import langfuse

    app = Flask(__name__)
    model = {"requested": REQUESTED_MODELS[0], "model": REQUESTED_MODELS[0]}
    case = {"owner_user_bid": "configured-owner", "case_id": "case"}
    monkeypatch.setattr(worker, "build_app", lambda _config: app)
    monkeypatch.setattr(langfuse, "init_langfuse", lambda _app: None)
    monkeypatch.setattr(
        source, "resolve_owner_user_bid", lambda _app, _phone: "configured-owner"
    )
    revalidate = Mock(return_value={"case"})
    generate = Mock(return_value={"status": "complete"})
    monkeypatch.setattr(source, "revalidate_sources", revalidate)
    monkeypatch.setattr(engine, "resolve_models", lambda _app, _requested: [model])
    monkeypatch.setattr(engine, "generate_case", generate)
    result = worker.execute(
        {
            "operation": "generate",
            "config": {"owner_phone": "10000000000"},
            "case": case,
            "model": model,
        }
    )
    assert result == {"status": "complete"}
    revalidate.assert_called_once_with(app, "configured-owner", [case])
    generate.assert_called_once_with(app, case, model)


@pytest.mark.parametrize("error_type", [ValueError, KeyError, RuntimeError])
def test_worker_does_not_publish_untrusted_exception_messages(
    error_type: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Provider values and logs stay out of the transport error response."""
    private_text = "private prompt and api_key=not-a-real-secret"

    def fail(_request: dict) -> object:
        print(private_text)
        raise error_type(private_text)

    monkeypatch.setattr(worker, "execute", fail)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert worker.worker_main() == 1
    captured = capsys.readouterr()
    response = json.loads(captured.out)
    assert response["ok"] is False
    assert response["error"]["type"] == error_type.__name__
    assert private_text not in captured.out
    assert not captured.err


@pytest.mark.parametrize("large", [False, True])
def test_worker_response_round_trips_large_chinese_and_small_plain_data(
    large: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    data = {"snapshot": {"document": "中文课程提示词\n" * (100_000 if large else 1)}}
    monkeypatch.setattr(worker, "execute", lambda _request: data)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert worker.worker_main() == 0
    output = capsys.readouterr().out
    envelope = json.loads(output)
    assert envelope["protocol_version"] == worker.WORKER_PROTOCOL_VERSION
    if large:
        assert envelope["encoding"] == "gzip+base64"
        assert output.isascii()
        assert len(output) < len(data["snapshot"]["document"].encode("utf-8")) // 10
    else:
        assert "encoding" not in envelope
        assert envelope["data"] == data
    command = Mock(return_value=subprocess.CompletedProcess([], 0, output, ""))
    monkeypatch.setattr(pipeline.subprocess, "run", command)
    backend = pipeline.WorkerBackend({"worker_timeout_seconds": 10}, tmp_path)
    assert backend.call("snapshot") == data
    command.assert_called_once()


def _compressed_envelope(content: bytes) -> dict:
    return {
        "ok": True,
        "protocol_version": worker.WORKER_PROTOCOL_VERSION,
        "encoding": "gzip+base64",
        "data": base64.b64encode(gzip.compress(content, mtime=0)).decode("ascii"),
    }


@pytest.mark.parametrize("corruption", ["truncated", "trailing", "checksum"])
def test_worker_backend_rejects_incomplete_or_corrupt_gzip_without_retry(
    corruption: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    envelope = _compressed_envelope(json.dumps({"content": "完整内容"}).encode())
    compressed = base64.b64decode(envelope["data"])
    if corruption == "truncated":
        compressed = compressed[:-5]
    elif corruption == "trailing":
        compressed += b"unexpected trailing transport bytes"
    else:
        compressed = compressed[:-1] + bytes([compressed[-1] ^ 1])
    envelope["data"] = base64.b64encode(compressed).decode("ascii")
    command = Mock(
        return_value=subprocess.CompletedProcess([], 0, json.dumps(envelope), "")
    )
    monkeypatch.setattr(pipeline.subprocess, "run", command)
    backend = pipeline.WorkerBackend({"worker_timeout_seconds": 10}, tmp_path)
    with pytest.raises(ArenaError, match="invalid protocol response"):
        backend.call("generate")
    command.assert_called_once()


def test_worker_backend_limits_decompression_before_loading_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert pipeline.MAX_WORKER_RESPONSE_BYTES == 64 * 1024 * 1024
    monkeypatch.setattr(pipeline, "MAX_WORKER_RESPONSE_BYTES", 128)
    envelope = _compressed_envelope(json.dumps({"content": "a" * 10_000}).encode())
    command = Mock(
        return_value=subprocess.CompletedProcess([], 0, json.dumps(envelope), "")
    )
    monkeypatch.setattr(pipeline.subprocess, "run", command)
    backend = pipeline.WorkerBackend({"worker_timeout_seconds": 10}, tmp_path)
    with pytest.raises(ArenaError, match="invalid protocol response"):
        backend.call("snapshot")
    command.assert_called_once()


@pytest.mark.parametrize(
    "response",
    [
        '{"ok": true, "data": "truncated',
        "[]",
        '{"ok": true}',
        '{"ok": true, "protocol_version": 2, "data": {}}',
        '{"ok": true, "encoding": "unknown", "data": ""}',
        '{"ok": true, "encoding": "gzip+base64", "data": "not base64!"}',
        json.dumps(_compressed_envelope(b"\xff")),
        json.dumps(_compressed_envelope(b"not JSON")),
    ],
)
def test_worker_backend_rejects_invalid_protocol_without_repeating_paid_call(
    response: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    command = Mock(return_value=subprocess.CompletedProcess([], 0, response, ""))
    monkeypatch.setattr(pipeline.subprocess, "run", command)
    backend = pipeline.WorkerBackend({"worker_timeout_seconds": 10}, tmp_path)
    with pytest.raises(ArenaError, match="invalid protocol response"):
        backend.call("generate")
    command.assert_called_once()


def test_worker_backend_reports_unicode_transport_truncation_without_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    command = Mock(
        side_effect=UnicodeDecodeError("utf-8", b"\xe8", 0, 1, "unexpected end")
    )
    monkeypatch.setattr(pipeline.subprocess, "run", command)
    backend = pipeline.WorkerBackend({"worker_timeout_seconds": 10}, tmp_path)
    with pytest.raises(ArenaError, match="invalid protocol response"):
        backend.call("generate")
    command.assert_called_once()


def test_worker_backend_accepts_legacy_plain_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    command = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, '{"ok": true, "data": {"content": "legacy"}}', ""
        )
    )
    monkeypatch.setattr(pipeline.subprocess, "run", command)
    backend = pipeline.WorkerBackend({"worker_timeout_seconds": 10}, tmp_path)
    assert backend.call("generate") == {"content": "legacy"}

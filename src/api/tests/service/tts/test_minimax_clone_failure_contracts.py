"""Protect voice clone input validation, provider errors and storage recovery."""

from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr import dao
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.resource.models import Resource
from flaskr.service.tts import minimax_voice_clone as clone
from flaskr.service.tts.models import TTSMiniMaxClonedVoice

from tests.service.tts.test_minimax_voice_clone import minimax_clone_app as clone_app

__all__ = ["clone_app"]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> clone.MiniMaxVoiceCloneClient:
    monkeypatch.setattr(
        clone, "get_config", lambda key: "test-key" if key == "MINIMAX_API_KEY" else ""
    )
    return clone.MiniMaxVoiceCloneClient()


@pytest.mark.parametrize(
    ("duration", "purpose", "message"),
    [
        (9999, "source", "at least 10 seconds"),
        (300001, "source", "no longer than 5 minutes"),
        (8001, "prompt", "no longer than 8 seconds"),
        (10000, "unknown", "invalid audio purpose"),
    ],
)
def test_invalid_audio_duration_is_rejected_before_export(
    monkeypatch: pytest.MonkeyPatch, duration: int, purpose: str, message: str
) -> None:
    class Segment:
        def __len__(self) -> int:
            return duration

        export = Mock()

    monkeypatch.setattr(clone.AudioSegment, "from_file", Mock(return_value=Segment()))
    with pytest.raises(ValueError, match=message):
        clone.normalize_audio_blob(b"audio", filename="audio.wav", purpose=purpose)
    Segment.export.assert_not_called()


@pytest.mark.parametrize(
    ("duration", "purpose"), [(10000, "source"), (300000, "source"), (8000, "prompt")]
)
def test_audio_duration_limits_are_inclusive(
    monkeypatch: pytest.MonkeyPatch, duration: int, purpose: str
) -> None:
    class Segment:
        def __len__(self) -> int:
            return duration

        def export(self, output: object, **kwargs: object) -> None:
            assert kwargs == {"format": "wav"}
            output.write(b"normalized-wav")

    decoder = Mock(return_value=Segment())
    monkeypatch.setattr(clone.AudioSegment, "from_file", decoder)
    result = clone.normalize_audio_blob(
        b"audio", filename="Audio.WAV ", purpose=purpose
    )
    assert result == clone.NormalizedAudioBlob(b"normalized-wav", duration)
    assert decoder.call_args.kwargs == {"format": "wav"}


@pytest.mark.parametrize(
    ("data", "filename", "message"),
    [
        (b"", "audio.wav", "audio file is empty"),
        (b"audio", "audio.txt", "unsupported audio file type"),
    ],
)
def test_invalid_audio_is_rejected_before_decode(
    monkeypatch: pytest.MonkeyPatch, data: bytes, filename: str, message: str
) -> None:
    decoder = Mock()
    monkeypatch.setattr(clone.AudioSegment, "from_file", decoder)
    with pytest.raises(ValueError, match=message):
        clone.normalize_audio_blob(data, filename=filename, purpose="source")
    decoder.assert_not_called()


def test_decoder_failure_has_actionable_error_and_original_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = OSError("invalid container")
    monkeypatch.setattr(clone.AudioSegment, "from_file", Mock(side_effect=failure))
    with pytest.raises(ValueError, match="unable to decode audio") as caught:
        clone.normalize_audio_blob(b"audio", filename="audio.mp3", purpose="source")
    assert caught.value.__cause__ is failure


def test_missing_provider_key_fails_at_client_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clone, "get_config", lambda _: " ")
    with pytest.raises(ValueError, match="MINIMAX_API_KEY is not configured"):
        clone.MiniMaxVoiceCloneClient()


@pytest.mark.parametrize("kind", ["source", "prompt", "clone"])
def test_provider_error_keeps_status_and_trace_for_diagnosis(
    client: clone.MiniMaxVoiceCloneClient, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    response = Mock()
    response.json.return_value = {
        "base_resp": {"status_code": 1001, "status_msg": "rejected"},
        "trace_id": "trace-1",
    }
    post = Mock(return_value=response)
    monkeypatch.setattr(clone.requests, "post", post)
    operation = {
        "source": partial(
            client.upload_clone_audio, b"source", "source.wav", "audio/wav"
        ),
        "prompt": partial(
            client.upload_prompt_audio, b"prompt", "prompt.wav", "audio/wav"
        ),
        "clone": partial(
            client.clone_voice,
            file_id="101",
            voice_id="AiShifu_xxxxxxxxxx",
            prompt_file_id="202",
        ),
    }[kind]
    with pytest.raises(ValueError, match="1001 - rejected, trace_id=trace-1"):
        operation()
    response.raise_for_status.assert_called_once()
    if kind == "clone":
        assert post.call_args.kwargs["json"]["clone_prompt"] == {"prompt_audio": 202}
    else:
        assert post.call_args.kwargs["data"] == {
            "purpose": "voice_clone" if kind == "source" else "prompt_audio"
        }


@pytest.mark.parametrize(
    "message", [{}, {"file": "invalid"}, {"data": {"file_id": ""}}]
)
def test_upload_success_without_file_identifier_is_rejected(
    client: clone.MiniMaxVoiceCloneClient,
    monkeypatch: pytest.MonkeyPatch,
    message: dict,
) -> None:
    response = Mock()
    response.json.return_value = message
    monkeypatch.setattr(clone.requests, "post", Mock(return_value=response))
    with pytest.raises(ValueError, match="did not return file_id"):
        client.upload_clone_audio(b"source", "source.wav", "")


def test_clone_preserves_nonnumeric_file_ids_and_provider_sensitive_result(
    client: clone.MiniMaxVoiceCloneClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = Mock()
    response.json.return_value = {
        "data": {
            "voice_id": "provider-voice",
            "demo_audio_url": "https://audio.invalid/demo",
            "input_sensitive": True,
            "input_sensitive_type": "restricted",
            "extra_info": ["invalid"],
        }
    }
    post = Mock(return_value=response)
    monkeypatch.setattr(clone.requests, "post", post)
    result = client.clone_voice(
        file_id=" opaque-id ", voice_id="requested-voice", prompt_file_id="prompt-id"
    )
    assert post.call_args.kwargs["json"]["file_id"] == "opaque-id"
    assert post.call_args.kwargs["json"]["clone_prompt"] == {
        "prompt_audio": "prompt-id"
    }
    assert result.voice_id == "provider-voice"
    assert result.demo_audio == "https://audio.invalid/demo"
    assert result.input_sensitive
    assert result.input_sensitive_type == "restricted"
    assert result.extra_info == {}


@pytest.mark.parametrize(
    ("data", "filename", "maximum"),
    [(b"", "audio.wav", 4), (b"12345", "audio.wav", 4), (b"123", "audio.txt", 4)],
)
def test_upload_validation_rejects_missing_oversized_and_unsupported_files(
    data: bytes, filename: str, maximum: int
) -> None:
    with pytest.raises(AppError) as caught:
        clone._validate_audio_upload(data, filename=filename, max_bytes=maximum)
    assert caught.value.code == ERROR_CODE["server.common.paramsError"]


@pytest.mark.parametrize(
    "owner", ["", "!!!", "123owner", "owner-with.dots", "longowner" * 10]
)
def test_generated_voice_ids_always_satisfy_provider_contract(owner: str) -> None:
    first = clone._generate_voice_id(owner)
    second = clone._generate_voice_id(owner)
    assert clone.is_valid_minimax_custom_voice_id(first)
    assert first != second
    assert len(first) <= 64


@pytest.mark.parametrize("field", ["owner_user_bid", "voice_bid"])
def test_blank_required_identifiers_fail_before_database_access(field: str) -> None:
    with pytest.raises(AppError) as caught:
        clone._normalize_required(" \n ", field)
    assert caught.value.code == ERROR_CODE["server.common.paramsError"]


@pytest.mark.parametrize(
    "operation",
    [
        "get_minimax_cloned_voice",
        "retry_minimax_voice_clone",
        "delete_minimax_cloned_voice",
    ],
)
def test_nonowners_cannot_read_retry_or_delete_voice(
    clone_app: object, operation: str
) -> None:
    row = clone.TTSMiniMaxClonedVoice(
        voice_bid="voice",
        voice_id="AiShifu_xxxxxxxxxx",
        owner_user_bid="owner",
        status=clone.TTS_MINIMAX_CLONE_STATUS_FAILED,
    )
    dao.db.session.add(row)
    dao.db.session.commit()
    with pytest.raises(AppError) as caught:
        getattr(clone, operation)(clone_app, owner_user_bid="other", voice_bid="voice")
    assert caught.value.code == ERROR_CODE["server.shifu.noPermission"]
    dao.db.session.expire_all()
    persisted = TTSMiniMaxClonedVoice.query.filter_by(voice_bid="voice").one()
    assert persisted.deleted == 0
    assert persisted.status == clone.TTS_MINIMAX_CLONE_STATUS_FAILED
    assert persisted.retry_count == 0


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (clone.TTS_MINIMAX_CLONE_STATUS_PROCESSING, "already_processing"),
        (999, "skipped"),
    ],
)
def test_worker_does_not_repeat_processing_or_run_unknown_states(
    clone_app: object, monkeypatch: pytest.MonkeyPatch, status: int, expected: str
) -> None:
    dao.db.session.add(
        TTSMiniMaxClonedVoice(
            voice_bid="voice", voice_id="AiShifu_xxxxxxxxxx", status=status
        )
    )
    dao.db.session.commit()
    execute = Mock()
    monkeypatch.setattr(clone, "_execute_clone_processing", execute)
    result = clone.run_minimax_voice_clone(clone_app, voice_bid="voice")
    assert result.to_payload() == {
        "status": expected,
        "voice_bid": "voice",
        "voice_id": "AiShifu_xxxxxxxxxx",
        "message": "",
    }
    execute.assert_not_called()


def test_missing_voice_is_a_parameter_error(clone_app: object) -> None:
    with pytest.raises(AppError) as caught:
        clone.get_minimax_cloned_voice(
            clone_app, owner_user_bid="owner", voice_bid="absent"
        )
    assert caught.value.code == ERROR_CODE["server.common.paramsError"]


def test_resource_memory_and_disk_fallback_return_exact_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setattr(clone, "_PENDING_AUDIO_BLOBS", {})
    monkeypatch.setattr(clone, "_temp_resource_path", lambda bid: tmp_path / bid)
    clone._remember_resource_bytes("audio", b"source")
    assert clone._read_resource_bytes(" audio ") == b"source"
    clone._PENDING_AUDIO_BLOBS.clear()
    assert clone._read_resource_bytes("audio") == b"source"
    assert (tmp_path / "audio").read_bytes() == b"source"
    clone._remember_resource_bytes(" ", b"ignored")
    assert clone._PENDING_AUDIO_BLOBS == {}
    with pytest.raises(ValueError, match="audio resource is missing"):
        clone._read_resource_bytes(" ")


@pytest.mark.usefixtures("clone_app")
@pytest.mark.parametrize("exists", [True, False])
def test_missing_or_unreadable_storage_reports_unavailable_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object, exists: bool
) -> None:
    monkeypatch.setattr(clone, "_PENDING_AUDIO_BLOBS", {})
    monkeypatch.setattr(clone, "_temp_resource_path", lambda bid: tmp_path / bid)
    read = Mock(side_effect=OSError("storage offline"))
    monkeypatch.setattr(clone, "read_storage_bytes", read)
    if exists:
        dao.db.session.add(
            Resource(
                resource_id="resource",
                name="source.wav",
                type=0,
                url="https://storage.invalid/source.wav",
                status=0,
                is_deleted=0,
                created_by="owner",
                updated_by="owner",
                oss_name="audio/source.wav",
                oss_bucket="course-assets",
            )
        )
        dao.db.session.commit()
    with pytest.raises(ValueError, match="source audio is no longer available"):
        clone._read_resource_bytes("resource")
    assert read.call_count == int(exists)


@pytest.mark.parametrize("available", [True, False])
def test_enqueue_uses_registered_task_or_fails_explicitly(
    monkeypatch: pytest.MonkeyPatch, available: bool
) -> None:
    from flaskr.common import celery_app

    task = Mock()
    app = object()
    get = Mock(
        return_value=SimpleNamespace(
            tasks={"tts.minimax_clone_voice": task} if available else {}
        )
    )
    monkeypatch.setattr(celery_app, "get_celery_app", get)
    if available:
        assert clone._enqueue_minimax_clone_task(app, voice_bid="voice")
        task.apply_async.assert_called_once_with(kwargs={"voice_bid": "voice"})
    else:
        with pytest.raises(RuntimeError, match="task is unavailable"):
            clone._enqueue_minimax_clone_task(app, voice_bid="voice")
        task.apply_async.assert_not_called()
    get.assert_called_once_with(flask_app=app)

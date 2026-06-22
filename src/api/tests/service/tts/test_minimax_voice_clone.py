from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_METRIC_TTS_REQUEST_COUNT,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW, BILL_USAGE_TYPE_TTS
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.models import DraftShifu


@pytest.fixture
def minimax_clone_app(monkeypatch):
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REDIS_KEY_PREFIX="minimax-clone-test",
        TZ="UTC",
    )
    monkeypatch.setattr(
        "flaskr.service.billing.admission.is_billing_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.is_billing_enabled",
        lambda: True,
    )
    dao.db.init_app(app)
    with app.app_context():
        from flaskr.service.tts.models import TTSMiniMaxClonedVoice  # noqa: F401

        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _seed_course_wallet_and_rate(app: Flask) -> None:
    with app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-creator-1",
            creator_bid="creator-1",
            available_credits=Decimal("10.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-creator-1",
            wallet_bid=wallet.wallet_bid,
            creator_bid="creator-1",
            bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
            source_type=0,
            source_bid="manual",
            priority=10,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("10.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 1, 1, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        rate = CreditUsageRate(
            rate_bid="rate-minimax-clone-test",
            usage_type=BILL_USAGE_TYPE_TTS,
            provider="minimax",
            model="voice_clone",
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
            billing_metric=BILLING_METRIC_TTS_REQUEST_COUNT,
            unit_size=1,
            credits_per_unit=Decimal("3.0000000000"),
            rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
            effective_from=datetime(2026, 1, 1, 0, 0, 0),
            effective_to=None,
            status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
        )
        course = DraftShifu(
            shifu_bid="shifu-1",
            title="Course",
            created_user_bid="creator-1",
            updated_user_bid="creator-1",
        )
        dao.db.session.add_all([wallet, bucket, rate, course])
        dao.db.session.commit()


def test_validate_minimax_custom_voice_id_rules() -> None:
    from flaskr.service.tts.minimax_voice_clone import (
        is_valid_minimax_custom_voice_id,
    )
    from flaskr.service.tts.validation import validate_tts_settings_strict

    assert is_valid_minimax_custom_voice_id("AiShifu_voice_123")
    assert not is_valid_minimax_custom_voice_id("1starts-with-digit")
    assert not is_valid_minimax_custom_voice_id("AiShifu_voice_")

    settings = validate_tts_settings_strict(
        provider="minimax",
        model="speech-2.8-turbo",
        voice_id="AiShifu_voice_123",
        speed=1.0,
        pitch=0,
        emotion="neutral",
    )

    assert settings.voice_id == "AiShifu_voice_123"

    with pytest.raises(AppException) as exc_info:
        validate_tts_settings_strict(
            provider="baidu",
            model="",
            voice_id="AiShifu_voice_123",
            speed=5.0,
            pitch=5,
            emotion="",
        )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_normalize_audio_blob_validates_duration_and_exports_wav(monkeypatch) -> None:
    from flaskr.service.tts import minimax_voice_clone

    class FakeSegment:
        def __len__(self):
            return 12_000

        def export(self, out, format="wav"):
            assert format == "wav"
            out.write(b"WAV-BYTES")

    monkeypatch.setattr(
        minimax_voice_clone.AudioSegment,
        "from_file",
        lambda _stream, format=None: FakeSegment(),
        raising=False,
    )

    result = minimax_voice_clone.normalize_audio_blob(
        b"RAW",
        filename="recording.webm",
        purpose="source",
    )

    assert result.duration_ms == 12_000
    assert result.extension == "wav"
    assert result.content_type == "audio/wav"
    assert result.audio_bytes == b"WAV-BYTES"


def test_minimax_upload_file_accepts_official_file_response(monkeypatch) -> None:
    from flaskr.service.tts import minimax_voice_clone
    from flaskr.service.tts.minimax_voice_clone import MiniMaxVoiceCloneClient

    monkeypatch.setattr(
        minimax_voice_clone,
        "get_config",
        lambda key: {
            "MINIMAX_API_KEY": "test-api-key",
            "MINIMAX_GROUP_ID": "test-group",
        }.get(key, ""),
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "file": {
                    "file_id": 123456789012345680,
                    "bytes": 5896337,
                    "filename": "audio_sample.wav",
                    "purpose": "voice_clone",
                },
                "base_resp": {"status_code": 0, "status_msg": "success"},
            }

    def fake_post(url, headers, data, files, timeout):
        assert url.endswith("/v1/files/upload?GroupId=test-group")
        assert headers["Authorization"] == "Bearer test-api-key"
        assert data == {"purpose": "voice_clone"}
        assert files["file"][0] == "audio_sample.wav"
        assert timeout == (10, 120)
        return FakeResponse()

    monkeypatch.setattr(minimax_voice_clone.requests, "post", fake_post)

    result = MiniMaxVoiceCloneClient().upload_clone_audio(
        b"WAV",
        filename="audio_sample.wav",
        content_type="audio/wav",
    )

    assert result.file_id == "123456789012345680"
    assert result.extra_info["purpose"] == "voice_clone"


def test_minimax_clone_voice_sends_numeric_file_id(monkeypatch) -> None:
    from flaskr.service.tts import minimax_voice_clone
    from flaskr.service.tts.minimax_voice_clone import MiniMaxVoiceCloneClient

    monkeypatch.setattr(
        minimax_voice_clone,
        "get_config",
        lambda key: {
            "MINIMAX_API_KEY": "test-api-key",
            "MINIMAX_GROUP_ID": "test-group",
        }.get(key, ""),
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "input_sensitive": False,
                "demo_audio": "https://example.test/demo.mp3",
                "extra_info": {"usage_characters": 10},
                "base_resp": {"status_code": 0, "status_msg": "success"},
            }

    def fake_post(url, headers, json, timeout):
        assert url.endswith("/v1/voice_clone?GroupId=test-group")
        assert headers["Authorization"] == "Bearer test-api-key"
        assert headers["Content-Type"] == "application/json"
        assert json["file_id"] == 123456789012345680
        assert isinstance(json["file_id"], int)
        assert json["voice_id"] == "AiShifu_teacher_1"
        assert timeout == (10, 120)
        return FakeResponse()

    monkeypatch.setattr(minimax_voice_clone.requests, "post", fake_post)

    result = MiniMaxVoiceCloneClient().clone_voice(
        file_id="123456789012345680",
        voice_id="AiShifu_teacher_1",
    )

    assert result.voice_id == "AiShifu_teacher_1"
    assert result.demo_audio == "https://example.test/demo.mp3"


def test_run_minimax_voice_clone_success_captures_credit_once(
    minimax_clone_app: Flask,
    monkeypatch,
) -> None:
    from flaskr.service.tts.minimax_voice_clone import (
        TTS_MINIMAX_CLONE_STATUS_READY,
        TTS_MINIMAX_CLONE_STATUS_QUEUED,
        submit_minimax_voice_clone,
        run_minimax_voice_clone,
    )
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    _seed_course_wallet_and_rate(minimax_clone_app)
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone._enqueue_minimax_clone_task",
        lambda _app, *, voice_bid: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone._store_resource_bytes",
        lambda app, **kwargs: SimpleNamespace(
            resource_bid=f"res-{kwargs['resource_kind']}",
            url=f"/resource/{kwargs['resource_kind']}",
            object_key=f"key/{kwargs['resource_kind']}",
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone._delete_resource_object",
        lambda app, resource_bid: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone.normalize_audio_blob",
        lambda data, filename, purpose: SimpleNamespace(
            audio_bytes=b"WAV",
            duration_ms=12_000,
            extension="wav",
            content_type="audio/wav",
        ),
    )

    class FakeClient:
        def upload_clone_audio(self, audio_bytes, filename, content_type):
            assert audio_bytes == b"WAV"
            assert filename.endswith(".wav")
            assert content_type == "audio/wav"
            return SimpleNamespace(file_id="file-source")

        def upload_prompt_audio(self, audio_bytes, filename, content_type):
            raise AssertionError("prompt upload should not be called")

        def clone_voice(self, **kwargs):
            assert kwargs["file_id"] == "file-source"
            return SimpleNamespace(
                voice_id=kwargs["voice_id"],
                demo_audio="https://example.test/demo.mp3",
                status_code=0,
                status_msg="success",
                input_sensitive=False,
                input_sensitive_type=None,
                extra_info={"usage_characters": 20},
                trace_id="trace-1",
            )

    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone.MiniMaxVoiceCloneClient",
        lambda: FakeClient(),
    )

    submitted = submit_minimax_voice_clone(
        minimax_clone_app,
        owner_user_bid="creator-1",
        shifu_bid="shifu-1",
        display_name="Teacher Voice",
        voice_id="AiShifu_teacher_1",
        source_audio_bytes=b"RAW",
        source_filename="recording.webm",
        source_content_type="audio/webm",
        source_capture_method="recording",
    )
    assert submitted.status == TTS_MINIMAX_CLONE_STATUS_QUEUED

    first_run = run_minimax_voice_clone(
        minimax_clone_app, voice_bid=submitted.voice_bid
    )
    second_run = run_minimax_voice_clone(
        minimax_clone_app, voice_bid=submitted.voice_bid
    )

    assert first_run.status == "ready"
    assert second_run.status == "already_ready"
    with minimax_clone_app.app_context():
        row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid=submitted.voice_bid).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
        usage = BillUsageRecord.query.filter_by(usage_bid=row.clone_usage_bid).one()
        assert row.status == TTS_MINIMAX_CLONE_STATUS_READY
        assert row.billing_status == "charged"
        assert row.charged_credits == Decimal("3.0000000000")
        assert wallet.available_credits == Decimal("7.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert usage.provider == "minimax"
        assert usage.model == "voice_clone"
        assert usage.extra["usage_source"] == "minimax_voice_clone"


def test_run_minimax_voice_clone_reads_persisted_storage_when_worker_cache_misses(
    minimax_clone_app: Flask,
    monkeypatch,
) -> None:
    from flaskr.service.resource.models import Resource
    from flaskr.service.tts import minimax_voice_clone
    from flaskr.service.tts.minimax_voice_clone import (
        TTS_MINIMAX_CLONE_STATUS_READY,
        run_minimax_voice_clone,
        submit_minimax_voice_clone,
    )
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    _seed_course_wallet_and_rate(minimax_clone_app)
    stored_objects: dict[str, bytes] = {}
    read_calls: list[tuple[str, str]] = []

    def fake_upload_to_storage(_app, *, file_content, object_key, **_kwargs):
        if hasattr(file_content, "seek"):
            file_content.seek(0)
        stored_objects[object_key] = file_content.read()
        return SimpleNamespace(
            bucket="resource-bucket",
            object_key=object_key,
            url=f"https://cdn.example/{object_key}",
        )

    def fake_read_storage_bytes(*, object_key, profile, bucket_name):
        read_calls.append((object_key, bucket_name))
        return stored_objects[object_key]

    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone._enqueue_minimax_clone_task",
        lambda _app, *, voice_bid: True,
    )
    monkeypatch.setattr(
        minimax_voice_clone,
        "upload_to_storage",
        fake_upload_to_storage,
    )
    monkeypatch.setattr(
        minimax_voice_clone,
        "read_storage_bytes",
        fake_read_storage_bytes,
    )
    monkeypatch.setattr(
        minimax_voice_clone,
        "normalize_audio_blob",
        lambda data, filename, purpose: SimpleNamespace(
            audio_bytes=b"WAV",
            duration_ms=12_000,
            extension="wav",
            content_type="audio/wav",
        ),
    )

    class FakeClient:
        def upload_clone_audio(self, audio_bytes, filename, content_type):
            assert audio_bytes == b"WAV"
            return SimpleNamespace(file_id="file-source")

        def upload_prompt_audio(self, audio_bytes, filename, content_type):
            raise AssertionError("prompt upload should not be called")

        def clone_voice(self, **kwargs):
            return SimpleNamespace(
                voice_id=kwargs["voice_id"],
                demo_audio="https://example.test/demo.mp3",
                status_code=0,
                status_msg="success",
                input_sensitive=False,
                input_sensitive_type=None,
                extra_info={},
                trace_id="trace-storage",
            )

    monkeypatch.setattr(
        minimax_voice_clone,
        "MiniMaxVoiceCloneClient",
        lambda: FakeClient(),
    )

    submitted = submit_minimax_voice_clone(
        minimax_clone_app,
        owner_user_bid="creator-1",
        shifu_bid="shifu-1",
        display_name="Teacher Voice",
        voice_id="AiShifu_teacher_storage_1",
        source_audio_bytes=b"RAW-FROM-API",
        source_filename="recording.webm",
        source_content_type="audio/webm",
        source_capture_method="recording",
    )

    with minimax_clone_app.app_context():
        row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid=submitted.voice_bid).one()
        resource = Resource.query.filter_by(
            resource_id=row.source_audio_resource_bid
        ).one()
        source_object_key = resource.oss_name
        minimax_voice_clone._PENDING_AUDIO_BLOBS.pop(resource.resource_id, None)
        minimax_voice_clone._temp_resource_path(resource.resource_id).unlink(
            missing_ok=True
        )

    result = run_minimax_voice_clone(
        minimax_clone_app,
        voice_bid=submitted.voice_bid,
    )

    assert result.status == "ready"
    with minimax_clone_app.app_context():
        row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid=submitted.voice_bid).one()
        assert row.status == TTS_MINIMAX_CLONE_STATUS_READY
        assert read_calls[0] == (source_object_key, "resource-bucket")


def test_execute_clone_processing_uses_row_values_inside_app_context(monkeypatch):
    from flaskr.service.tts import minimax_voice_clone

    in_context = False
    stored_calls: list[dict[str, str]] = []

    class FakeApp:
        def app_context(self):
            class Context:
                def __enter__(self):
                    nonlocal in_context
                    in_context = True
                    return self

                def __exit__(self, *_args):
                    nonlocal in_context
                    in_context = False
                    return False

            return Context()

    class DetachedSensitiveRow:
        def __init__(self):
            self.voice_bid = "voice-detached"
            self.voice_id = "AiShifu_detached_1"
            self.owner_user_bid = "creator-1"
            self.shifu_bid = "shifu-1"
            self.source_audio_resource_bid = "source-resource"
            self.prompt_audio_resource_bid = ""
            self.source_audio_filename = "source.webm"
            self.prompt_audio_filename = ""
            self.billing_reservation_bid = ""
            self.estimated_credits = Decimal("0")

        def __getattribute__(self, name):
            protected = {
                "voice_bid",
                "voice_id",
                "owner_user_bid",
                "source_audio_resource_bid",
                "prompt_audio_resource_bid",
                "source_audio_filename",
                "prompt_audio_filename",
            }
            if name in protected and not in_context:
                raise RuntimeError(f"{name} accessed outside app context")
            return object.__getattribute__(self, name)

    row = DetachedSensitiveRow()

    monkeypatch.setattr(
        minimax_voice_clone,
        "_load_voice_row",
        lambda voice_bid: row,
    )
    monkeypatch.setattr(
        minimax_voice_clone,
        "_read_resource_bytes",
        lambda resource_bid: b"RAW",
    )
    monkeypatch.setattr(
        minimax_voice_clone,
        "normalize_audio_blob",
        lambda data, filename, purpose: SimpleNamespace(
            audio_bytes=b"WAV",
            duration_ms=12_000,
            content_type="audio/wav",
        ),
    )

    def fake_store_resource_bytes(_app, **kwargs):
        stored_calls.append(
            {
                "owner_user_bid": kwargs["owner_user_bid"],
                "filename": kwargs["filename"],
                "object_key": kwargs["object_key"],
            }
        )
        return SimpleNamespace(
            resource_bid="normalized-resource",
            url="/normalized.wav",
            object_key=kwargs["object_key"],
        )

    monkeypatch.setattr(
        minimax_voice_clone,
        "_store_resource_bytes",
        fake_store_resource_bytes,
    )
    monkeypatch.setattr(
        minimax_voice_clone,
        "_record_voice_clone_usage",
        lambda _app, _row, _result: "usage-1",
    )
    monkeypatch.setattr(
        minimax_voice_clone,
        "_cleanup_raw_resources",
        lambda _app, _row: None,
    )
    monkeypatch.setattr(
        minimax_voice_clone,
        "db",
        SimpleNamespace(session=SimpleNamespace(commit=lambda: None)),
    )

    class FakeClient:
        def upload_clone_audio(self, audio_bytes, filename, content_type):
            return SimpleNamespace(file_id="file-source")

        def upload_prompt_audio(self, audio_bytes, filename, content_type):
            raise AssertionError("prompt upload should not be called")

        def clone_voice(self, **kwargs):
            return SimpleNamespace(
                voice_id=kwargs["voice_id"],
                demo_audio="https://example.test/demo.mp3",
                status_code=0,
                status_msg="success",
                input_sensitive=False,
                extra_info={},
                trace_id="trace-detached",
            )

    monkeypatch.setattr(
        minimax_voice_clone,
        "MiniMaxVoiceCloneClient",
        lambda: FakeClient(),
    )

    result = minimax_voice_clone._execute_clone_processing(
        FakeApp(),
        "voice-detached",
    )

    assert result.status == "ready"
    assert stored_calls == [
        {
            "owner_user_bid": "creator-1",
            "filename": "AiShifu_detached_1.wav",
            "object_key": "tts/minimax/voice-clone/voice-detached/normalized/AiShifu_detached_1.wav",
        }
    ]


def test_soft_deleted_minimax_voice_id_can_be_reused(
    minimax_clone_app: Flask,
    monkeypatch,
) -> None:
    from flaskr.service.tts.minimax_voice_clone import submit_minimax_voice_clone
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    _seed_course_wallet_and_rate(minimax_clone_app)
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone._enqueue_minimax_clone_task",
        lambda _app, *, voice_bid: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone._store_resource_bytes",
        lambda app, **kwargs: SimpleNamespace(
            resource_bid=f"res-{kwargs['resource_kind']}-{kwargs['filename']}",
            url=f"/resource/{kwargs['resource_kind']}",
            object_key=f"key/{kwargs['resource_kind']}",
        ),
    )

    first = submit_minimax_voice_clone(
        minimax_clone_app,
        owner_user_bid="creator-1",
        shifu_bid="shifu-1",
        display_name="Teacher Voice",
        voice_id="AiShifu_reusable_1",
        source_audio_bytes=b"RAW",
        source_filename="recording.webm",
        source_content_type="audio/webm",
        source_capture_method="recording",
    )
    with minimax_clone_app.app_context():
        row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid=first.voice_bid).one()
        row.deleted = 1
        dao.db.session.commit()

    second = submit_minimax_voice_clone(
        minimax_clone_app,
        owner_user_bid="creator-1",
        shifu_bid="shifu-1",
        display_name="Teacher Voice 2",
        voice_id="AiShifu_reusable_1",
        source_audio_bytes=b"RAW",
        source_filename="recording.webm",
        source_content_type="audio/webm",
        source_capture_method="recording",
    )

    assert second.voice_bid != first.voice_bid
    assert second.voice_id == "AiShifu_reusable_1"


def test_run_minimax_voice_clone_releases_credit_on_normalization_failure(
    minimax_clone_app: Flask,
    monkeypatch,
) -> None:
    from flaskr.service.tts.minimax_voice_clone import (
        TTS_MINIMAX_CLONE_STATUS_FAILED,
        submit_minimax_voice_clone,
        run_minimax_voice_clone,
    )
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    _seed_course_wallet_and_rate(minimax_clone_app)
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone._enqueue_minimax_clone_task",
        lambda _app, *, voice_bid: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone._store_resource_bytes",
        lambda app, **kwargs: SimpleNamespace(
            resource_bid=f"res-{kwargs['resource_kind']}",
            url=f"/resource/{kwargs['resource_kind']}",
            object_key=f"key/{kwargs['resource_kind']}",
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone._delete_resource_object",
        lambda app, resource_bid: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone.normalize_audio_blob",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("too short")),
    )

    submitted = submit_minimax_voice_clone(
        minimax_clone_app,
        owner_user_bid="creator-1",
        shifu_bid="shifu-1",
        display_name="Teacher Voice",
        voice_id="AiShifu_teacher_2",
        source_audio_bytes=b"RAW",
        source_filename="recording.webm",
        source_content_type="audio/webm",
        source_capture_method="recording",
    )

    result = run_minimax_voice_clone(minimax_clone_app, voice_bid=submitted.voice_bid)

    assert result.status == "failed"
    with minimax_clone_app.app_context():
        row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid=submitted.voice_bid).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
        assert row.status == TTS_MINIMAX_CLONE_STATUS_FAILED
        assert row.billing_status == "released"
        assert "too short" in row.status_msg
        assert wallet.available_credits == Decimal("10.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")


def test_retry_minimax_voice_clone_re_reserves_after_released_failure(
    minimax_clone_app: Flask,
    monkeypatch,
) -> None:
    from flaskr.service.tts import minimax_voice_clone
    from flaskr.service.tts.minimax_voice_clone import (
        retry_minimax_voice_clone,
        run_minimax_voice_clone,
        submit_minimax_voice_clone,
    )
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    _seed_course_wallet_and_rate(minimax_clone_app)
    monkeypatch.setattr(
        minimax_voice_clone,
        "_enqueue_minimax_clone_task",
        lambda _app, *, voice_bid: True,
    )
    monkeypatch.setattr(
        minimax_voice_clone,
        "_store_resource_bytes",
        lambda app, **kwargs: SimpleNamespace(
            resource_bid=f"res-{kwargs['resource_kind']}",
            url=f"/resource/{kwargs['resource_kind']}",
            object_key=f"key/{kwargs['resource_kind']}",
        ),
    )
    monkeypatch.setattr(
        minimax_voice_clone,
        "_delete_resource_object",
        lambda app, resource_bid: None,
    )
    monkeypatch.setattr(
        minimax_voice_clone,
        "normalize_audio_blob",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("too short")),
    )

    submitted = submit_minimax_voice_clone(
        minimax_clone_app,
        owner_user_bid="creator-1",
        shifu_bid="shifu-1",
        display_name="Teacher Voice",
        voice_id="AiShifu_teacher_retry_1",
        source_audio_bytes=b"RAW",
        source_filename="recording.webm",
        source_content_type="audio/webm",
        source_capture_method="recording",
    )
    result = run_minimax_voice_clone(minimax_clone_app, voice_bid=submitted.voice_bid)
    assert result.status == "failed"

    with minimax_clone_app.app_context():
        failed = TTSMiniMaxClonedVoice.query.filter_by(
            voice_bid=submitted.voice_bid
        ).one()
        released_reservation_bid = failed.billing_reservation_bid
        assert failed.billing_status == "released"

    retried = retry_minimax_voice_clone(
        minimax_clone_app,
        owner_user_bid="creator-1",
        voice_bid=submitted.voice_bid,
    )

    assert retried["status"] == "queued"
    with minimax_clone_app.app_context():
        row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid=submitted.voice_bid).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
        assert row.retry_count == 1
        assert row.billing_status == "reserved"
        assert row.billing_reservation_bid
        assert row.billing_reservation_bid != released_reservation_bid
        assert wallet.available_credits == Decimal("7.0000000000")
        assert wallet.reserved_credits == Decimal("3.0000000000")

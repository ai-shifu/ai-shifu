from types import SimpleNamespace

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

import flaskr.dao as dao

if dao.db is None:
    _test_app = Flask("test-context-v2-tts-runtime-voice-bootstrap")
    _test_app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    _db = SQLAlchemy()
    _db.init_app(_test_app)
    dao.db = _db

if not hasattr(dao, "redis_client"):
    dao.redis_client = None


def test_context_v2_tts_processor_uses_runtime_minimax_voice_fallback(monkeypatch):
    from flaskr.dao import db
    from flaskr.service.learn.context_v2 import RunScriptContextV2
    from flaskr.service.shifu.models import DraftShifu
    from flaskr.service.tts.models import (
        TTSMiniMaxClonedVoice,
        TTS_MINIMAX_CLONE_STATUS_QUEUED,
    )

    app = Flask("test-context-v2-tts-runtime-voice")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    captured_kwargs = {}

    class FakeStreamingTTSProcessor:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        FakeStreamingTTSProcessor,
    )

    shifu_bid = "shifu-context-runtime-voice-1"
    stale_voice_id = "notReadyVoice123"

    with app.app_context():
        db.create_all()
        db.session.add(
            DraftShifu(
                shifu_bid=shifu_bid,
                title="Runtime voice test",
                tts_enabled=1,
                tts_provider="minimax",
                tts_model="speech-2.8-turbo",
                tts_voice_id=stale_voice_id,
                tts_speed=1.0,
                tts_pitch=0,
                tts_emotion="",
                deleted=0,
            )
        )
        db.session.add(
            TTSMiniMaxClonedVoice(
                voice_bid="voice-context-runtime-voice-1",
                shifu_bid=shifu_bid,
                voice_id=stale_voice_id,
                status=TTS_MINIMAX_CLONE_STATUS_QUEUED,
                deleted=0,
            )
        )
        db.session.commit()

        ctx = RunScriptContextV2.__new__(RunScriptContextV2)
        ctx.app = app
        ctx._shifu_model = DraftShifu
        ctx._outline_item_info = SimpleNamespace(
            bid="outline-context-runtime-voice-1",
            shifu_bid=shifu_bid,
        )
        ctx._current_attend = SimpleNamespace(
            progress_record_bid="progress-context-runtime-voice-1"
        )
        ctx._user_info = SimpleNamespace(user_id="user-context-runtime-voice-1")

        processor = ctx._try_create_tts_processor("generated-context-runtime-voice-1")

    assert isinstance(processor, FakeStreamingTTSProcessor)
    assert captured_kwargs["voice_id"] == "male-qn-qingse"
    assert captured_kwargs["tts_provider"] == "minimax"
    assert captured_kwargs["tts_model"] == "speech-2.8-turbo"

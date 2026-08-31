"""Verify context v2 TTS runtime voice behavior."""

import time
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask


def test_context_v2_tts_processor_uses_runtime_minimax_voice_fallback(
    monkeypatch: object,
) -> None:
    from flaskr.dao import db
    from flaskr.service.learn.const import INPUT_TYPE_ASK
    from flaskr.service.learn.context_v2 import RunScriptContextV2
    from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
    from flaskr.service.shifu.models import DraftShifu
    from flaskr.service.tts.models import (
        TTS_MINIMAX_CLONE_STATUS_QUEUED,
        TTSMiniMaxClonedVoice,
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
        def __init__(self, **kwargs: object) -> None:
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
        ctx._preview_mode = True
        ctx._input_type = INPUT_TYPE_ASK

        processor = ctx._try_create_tts_processor("generated-context-runtime-voice-1")

    assert isinstance(processor, FakeStreamingTTSProcessor)
    assert captured_kwargs["voice_id"] == "male-qn-qingse"
    assert captured_kwargs["tts_provider"] == "minimax"
    assert captured_kwargs["tts_model"] == "speech-2.8-turbo"
    assert captured_kwargs["usage_scene"] == BILL_USAGE_SCENE_PREVIEW
    assert captured_kwargs["persist_audio"] is False
    assert captured_kwargs["force_sentence_streaming"] is True


def test_ask_stream_drains_first_sentence_audio_before_answer_break() -> None:
    from flaskr.service.learn import context_v2 as context_v2_module
    from flaskr.service.learn.context_v2 import RunScriptContextV2
    from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO

    app = Flask("ask-stream-tts-idle-drain")
    app.config["STREAM_TTS_IDLE_DRAIN_INTERVAL"] = 0.01
    ctx = RunScriptContextV2.__new__(RunScriptContextV2)
    ctx.app = app
    ctx._stop_event = None
    ctx._listen = True
    ctx._input_type = "ask"
    ctx._input = "Why?"
    ctx._last_position = 0
    ctx._preview_mode = False
    ctx._user_info = SimpleNamespace(user_id="user-1")
    ctx._outline_item_info = SimpleNamespace(
        bid="outline-1",
        shifu_bid="shifu-1",
    )
    ctx._current_attend = SimpleNamespace(progress_record_bid="progress-1")
    ctx._trace_args = {}
    ctx._trace = None
    ctx._trace_root_span = None
    ctx._element_index_cursor = 0
    committed: list[bool] = []
    ctx.__dict__["_run_recorder"] = SimpleNamespace(
        commit_pending_step=lambda: committed.append(True)
    )

    content_event = RunMarkdownFlowDTO(
        outline_bid="outline-1",
        generated_block_bid="answer-block-1",
        type=GeneratedType.CONTENT,
        content="The first sentence is ready.",
    )
    break_event = RunMarkdownFlowDTO(
        outline_bid="outline-1",
        generated_block_bid="answer-block-1",
        type=GeneratedType.BREAK,
        content="",
    )
    audio_event = RunMarkdownFlowDTO(
        outline_bid="outline-1",
        generated_block_bid="answer-block-1",
        type=GeneratedType.AUDIO_SEGMENT,
        content="first-sentence-audio",
    )

    def delayed_answer_stream() -> object:
        yield content_event
        time.sleep(0.06)
        yield break_event

    class FakeProcessor:
        next_element_index = 0

        def __init__(self) -> None:
            self.sentence_submitted = False
            self.audio_emitted = False

        def process_chunk(self, content: str) -> object:
            self.sentence_submitted = content.endswith(".")
            if False:
                yield None

        def drain_ready_segments(self) -> object:
            if self.sentence_submitted and not self.audio_emitted:
                self.audio_emitted = True
                yield audio_event

        def finalize(self, *, commit: bool = True) -> object:
            _ = commit
            if False:
                yield None

    processor = FakeProcessor()
    ctx._try_create_tts_processor = lambda *_args, **_kwargs: processor

    with (
        app.app_context(),
        patch.object(
            context_v2_module,
            "handle_input_ask",
            return_value=delayed_answer_stream(),
        ),
        patch.object(context_v2_module, "get_user_profiles", return_value={}),
    ):
        events = list(
            ctx._phase_handle_ask_input(
                app,
                SimpleNamespace(block_position=0),
            )
        )

    assert [event.type for event in events] == [
        GeneratedType.CONTENT,
        GeneratedType.AUDIO_SEGMENT,
        GeneratedType.BREAK,
    ]
    assert committed == [True, True]

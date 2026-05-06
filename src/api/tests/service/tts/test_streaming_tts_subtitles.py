from flask import Flask
from flask_sqlalchemy import SQLAlchemy

import flaskr.dao as dao

if dao.db is None:
    _test_app = Flask("test-streaming-tts-subtitles")
    _test_app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    _db = SQLAlchemy()
    _db.init_app(_test_app)
    dao.db = _db

if not hasattr(dao, "redis_client"):
    dao.redis_client = None


class TestStreamingTtsSubtitles:
    @classmethod
    def setup_class(cls):
        cls.app = Flask("streaming-tts-subtitles")
        cls.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_BINDS={
                "ai_shifu_saas": "sqlite:///:memory:",
                "ai_shifu_admin": "sqlite:///:memory:",
            },
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        dao.db.init_app(cls.app)

        from flaskr.service.tts.models import LearnGeneratedAudio

        cls.LearnGeneratedAudio = LearnGeneratedAudio

        with cls.app.app_context():
            dao.db.create_all()

    def test_streaming_tts_processor_persists_subtitle_cues(self, monkeypatch):
        from types import SimpleNamespace

        from flaskr.dao import db
        from flaskr.service.learn.learn_dtos import GeneratedType
        from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

        with self.app.app_context():
            self.LearnGeneratedAudio.query.delete()
            db.session.commit()

        monkeypatch.setattr(
            "flaskr.service.tts.streaming_tts.is_tts_configured",
            lambda _provider: True,
        )
        monkeypatch.setattr(
            "flaskr.service.tts.streaming_tts.should_use_minimax_http_stream",
            lambda _provider: False,
        )
        monkeypatch.setattr(
            "flaskr.service.tts.streaming_tts.synthesize_text",
            lambda **kwargs: SimpleNamespace(
                audio_data=f"audio:{kwargs['text']}".encode("utf-8"),
                duration_ms=120,
                word_count=2,
            ),
        )
        monkeypatch.setattr(
            "flaskr.service.tts.streaming_tts.concat_audio_best_effort",
            lambda parts: b"".join(parts),
        )
        monkeypatch.setattr(
            "flaskr.service.tts.streaming_tts.get_audio_duration_ms",
            lambda _audio: 240,
        )
        monkeypatch.setattr(
            "flaskr.service.tts.tts_handler.upload_audio_to_oss",
            lambda _app, _audio, audio_bid: (
                f"https://example.com/{audio_bid}.mp3",
                "test-bucket",
            ),
        )
        monkeypatch.setattr(
            "flaskr.service.tts.tts_usage_recorder.record_tts_aggregated_usage",
            lambda **_kwargs: None,
        )
        monkeypatch.setattr(
            "flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage",
            lambda **_kwargs: None,
        )

        with self.app.app_context():
            processor = StreamingTTSProcessor(
                app=self.app,
                generated_block_bid="generated-streaming-subtitles",
                outline_bid="outline-streaming-subtitles",
                progress_record_bid="progress-streaming-subtitles",
                user_bid="user-streaming-subtitles",
                shifu_bid="shifu-streaming-subtitles",
                tts_provider="minimax",
                tts_model="test-model",
            )
            processor._buffer = "First sentence. Second sentence."

            events = list(processor.finalize(commit=True))
        audio_complete_events = [
            event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
        ]
        audio_segment_events = [
            event for event in events if event.type == GeneratedType.AUDIO_SEGMENT
        ]

        assert len(audio_complete_events) == 1
        assert len(audio_segment_events) == 2
        assert [cue.text for cue in audio_segment_events[0].content.subtitle_cues] == [
            "First sentence."
        ]
        assert [cue.text for cue in audio_segment_events[1].content.subtitle_cues] == [
            "First sentence.",
            "Second sentence.",
        ]
        subtitle_cues = audio_complete_events[0].content.subtitle_cues
        assert [cue.text for cue in subtitle_cues] == [
            "First sentence.",
            "Second sentence.",
        ]
        assert [(cue.start_ms, cue.end_ms) for cue in subtitle_cues] == [
            (0, 120),
            (120, 240),
        ]

        with self.app.app_context():
            audio_record = (
                self.LearnGeneratedAudio.query.filter(
                    self.LearnGeneratedAudio.generated_block_bid
                    == "generated-streaming-subtitles"
                )
                .order_by(self.LearnGeneratedAudio.id.desc())
                .first()
            )

        assert audio_record is not None
        assert [cue["text"] for cue in audio_record.subtitle_cues] == [
            "First sentence.",
            "Second sentence.",
        ]

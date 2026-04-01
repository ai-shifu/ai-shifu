from flask import Flask
from flask_sqlalchemy import SQLAlchemy

import flaskr.dao as dao

if dao.db is None:
    _test_app = Flask("test-listen-element-history-subtitles")
    _test_app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    _db = SQLAlchemy()
    _db.init_app(_test_app)
    dao.db = _db

if not hasattr(dao, "redis_client"):
    dao.redis_client = None


class TestListenElementHistorySubtitles:
    @classmethod
    def setup_class(cls):
        cls.app = Flask("listen-element-history-subtitles")
        cls.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_BINDS={
                "ai_shifu_saas": "sqlite:///:memory:",
                "ai_shifu_admin": "sqlite:///:memory:",
            },
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        dao.db.init_app(cls.app)

        from flaskr.service.learn.models import LearnGeneratedElement
        from flaskr.service.tts.models import LearnGeneratedAudio

        cls.LearnGeneratedElement = LearnGeneratedElement
        cls.LearnGeneratedAudio = LearnGeneratedAudio

        with cls.app.app_context():
            dao.db.create_all()

    def test_final_elements_are_hydrated_from_persisted_audio_subtitles(self):
        from flaskr.dao import db
        from flaskr.service.learn.listen_element_history import (
            get_final_elements_for_generated_block,
        )
        from flaskr.service.tts.models import AUDIO_STATUS_COMPLETED

        generated_block_bid = "generated-history-subtitles"

        with self.app.app_context():
            db.session.query(self.LearnGeneratedAudio).delete()
            db.session.query(self.LearnGeneratedElement).delete()
            db.session.commit()

            db.session.add(
                self.LearnGeneratedElement(
                    element_bid="element-history-subtitles",
                    progress_record_bid="progress-history-subtitles",
                    user_bid="user-history-subtitles",
                    generated_block_bid=generated_block_bid,
                    outline_item_bid="outline-history-subtitles",
                    shifu_bid="shifu-history-subtitles",
                    run_session_bid="run-history-subtitles",
                    run_event_seq=1,
                    event_type="element",
                    role="teacher",
                    element_index=0,
                    element_type="text",
                    element_type_code=213,
                    change_type="render",
                    target_element_bid="",
                    is_renderable=0,
                    is_new=1,
                    is_marker=0,
                    sequence_number=1,
                    is_speakable=1,
                    audio_url="",
                    audio_segments="[]",
                    is_navigable=1,
                    is_final=1,
                    content_text="Hello subtitle history.",
                    payload='{"audio": {"position": 0, "audio_url": "", "audio_bid": "", "duration_ms": 0}, "previous_visuals": []}',
                    deleted=0,
                    status=1,
                )
            )
            db.session.add(
                self.LearnGeneratedAudio(
                    audio_bid="audio-history-subtitles",
                    generated_block_bid=generated_block_bid,
                    position=0,
                    progress_record_bid="progress-history-subtitles",
                    user_bid="user-history-subtitles",
                    shifu_bid="shifu-history-subtitles",
                    oss_url="https://example.com/history-subtitles.mp3",
                    duration_ms=640,
                    subtitle_cues=[
                        {
                            "text": "Hello subtitle history.",
                            "start_ms": 0,
                            "end_ms": 640,
                            "segment_index": 0,
                            "position": 0,
                        }
                    ],
                    status=AUDIO_STATUS_COMPLETED,
                )
            )
            db.session.commit()

            elements = get_final_elements_for_generated_block(
                generated_block_bid=generated_block_bid,
                user_bid="user-history-subtitles",
                shifu_bid="shifu-history-subtitles",
            )

        assert len(elements) == 1
        element = elements[0]
        assert element.audio_url == "https://example.com/history-subtitles.mp3"
        assert element.payload is not None
        assert element.payload.audio is not None
        assert element.payload.audio.audio_bid == "audio-history-subtitles"
        assert element.payload.audio.subtitle_cues[0].text == "Hello subtitle history."

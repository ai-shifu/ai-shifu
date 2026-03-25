from flask import Flask
from flask_sqlalchemy import SQLAlchemy

import flaskr.dao as dao

if dao.db is None:
    _test_app = Flask("test-listen-elements-legacy-record")
    _test_app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    _db = SQLAlchemy()
    _db.init_app(_test_app)
    dao.db = _db

if not hasattr(dao, "redis_client"):
    dao.redis_client = None


class TestBuildListenElementsFromLegacyRecord:
    @classmethod
    def setup_class(cls):
        cls.app = Flask("listen-elements-legacy-record")
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

        cls.LearnGeneratedElement = LearnGeneratedElement

        with cls.app.app_context():
            dao.db.create_all()

    def test_prefers_persisted_text_elements_for_audio_positions(self):
        from flaskr.dao import db
        from flaskr.service.learn.learn_dtos import (
            AudioCompleteDTO,
            BlockType,
            ElementType,
            GeneratedBlockDTO,
            LearnRecordDTO,
            LikeStatus,
        )
        from flaskr.service.learn.listen_elements import (
            build_listen_elements_from_legacy_record,
        )

        generated_block_bid = "generated-legacy-persisted-text"

        with self.app.app_context():
            db.session.query(self.LearnGeneratedElement).delete()
            db.session.commit()

            db.session.add_all(
                [
                    self.LearnGeneratedElement(
                        element_bid="el-legacy-persisted-1",
                        progress_record_bid="progress-legacy-persisted",
                        user_bid="user-legacy-persisted",
                        generated_block_bid=generated_block_bid,
                        outline_item_bid="outline-legacy-persisted",
                        shifu_bid="shifu-legacy-persisted",
                        run_session_bid="run-legacy-persisted",
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
                        content_text="Alpha",
                        payload='{"audio": null, "previous_visuals": []}',
                        deleted=0,
                        status=1,
                    ),
                    self.LearnGeneratedElement(
                        element_bid="el-legacy-persisted-2",
                        progress_record_bid="progress-legacy-persisted",
                        user_bid="user-legacy-persisted",
                        generated_block_bid=generated_block_bid,
                        outline_item_bid="outline-legacy-persisted",
                        shifu_bid="shifu-legacy-persisted",
                        run_session_bid="run-legacy-persisted",
                        run_event_seq=2,
                        event_type="element",
                        role="teacher",
                        element_index=1,
                        element_type="text",
                        element_type_code=213,
                        change_type="render",
                        target_element_bid="",
                        is_renderable=0,
                        is_new=1,
                        is_marker=0,
                        sequence_number=2,
                        is_speakable=1,
                        audio_url="",
                        audio_segments="[]",
                        is_navigable=1,
                        is_final=1,
                        content_text="Beta",
                        payload='{"audio": null, "previous_visuals": []}',
                        deleted=0,
                        status=1,
                    ),
                ]
            )
            db.session.commit()

        legacy_record = LearnRecordDTO(
            records=[
                GeneratedBlockDTO(
                    generated_block_bid=generated_block_bid,
                    content="Alpha Beta",
                    like_status=LikeStatus.NONE,
                    block_type=BlockType.CONTENT,
                    user_input="",
                    audios=[
                        AudioCompleteDTO(
                            position=0,
                            audio_url="https://example.com/persisted-0.mp3",
                            audio_bid="audio-persisted-0",
                            duration_ms=320,
                        ),
                        AudioCompleteDTO(
                            position=1,
                            audio_url="https://example.com/persisted-1.mp3",
                            audio_bid="audio-persisted-1",
                            duration_ms=410,
                        ),
                    ],
                )
            ]
        )

        result = build_listen_elements_from_legacy_record(self.app, legacy_record)

        assert len(result.elements) == 2
        assert [element.element_type for element in result.elements] == [
            ElementType.TEXT,
            ElementType.TEXT,
        ]
        assert [element.content_text for element in result.elements] == [
            "Alpha",
            "Beta",
        ]
        assert [element.element_index for element in result.elements] == [0, 1]
        assert [element.audio_url for element in result.elements] == [
            "https://example.com/persisted-0.mp3",
            "https://example.com/persisted-1.mp3",
        ]
        assert [element.payload.audio.audio_bid for element in result.elements] == [
            "audio-persisted-0",
            "audio-persisted-1",
        ]

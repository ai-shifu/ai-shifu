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

    def test_multi_position_audio_is_hydrated_by_speakable_element_order(self):
        from flaskr.dao import db
        from flaskr.service.learn.listen_element_history import (
            get_final_elements_for_generated_block,
        )
        from flaskr.service.tts.models import AUDIO_STATUS_COMPLETED

        generated_block_bid = "generated-history-multi-position"

        def add_element(
            *,
            element_bid: str,
            element_index: int,
            element_type: str,
            content_text: str,
            is_speakable: int,
        ):
            db.session.add(
                self.LearnGeneratedElement(
                    element_bid=element_bid,
                    progress_record_bid="progress-history-multi-position",
                    user_bid="user-history-multi-position",
                    generated_block_bid=generated_block_bid,
                    outline_item_bid="outline-history-multi-position",
                    shifu_bid="shifu-history-multi-position",
                    run_session_bid="run-history-multi-position",
                    run_event_seq=element_index + 1,
                    event_type="element",
                    role="teacher",
                    element_index=element_index,
                    element_type=element_type,
                    element_type_code=213 if element_type == "text" else 201,
                    change_type="render",
                    target_element_bid="",
                    is_renderable=0 if element_type == "text" else 1,
                    is_new=1,
                    is_marker=0 if element_type == "text" else 1,
                    sequence_number=element_index + 1,
                    is_speakable=is_speakable,
                    audio_url="",
                    audio_segments="[]",
                    is_navigable=1,
                    is_final=1,
                    content_text=content_text,
                    payload='{"previous_visuals": []}',
                    deleted=0,
                    status=1,
                )
            )

        def add_audio(*, position: int):
            db.session.add(
                self.LearnGeneratedAudio(
                    audio_bid=f"audio-history-multi-{position}",
                    generated_block_bid=generated_block_bid,
                    position=position,
                    progress_record_bid="progress-history-multi-position",
                    user_bid="user-history-multi-position",
                    shifu_bid="shifu-history-multi-position",
                    oss_url=f"https://example.com/history-multi-{position}.mp3",
                    duration_ms=1000 + position,
                    subtitle_cues=[
                        {
                            "text": f"Line {position}",
                            "start_ms": 0,
                            "end_ms": 1000 + position,
                            "segment_index": 0,
                            "position": position,
                        }
                    ],
                    status=AUDIO_STATUS_COMPLETED,
                )
            )

        with self.app.app_context():
            db.session.query(self.LearnGeneratedAudio).delete()
            db.session.query(self.LearnGeneratedElement).delete()
            db.session.commit()

            add_element(
                element_bid="element-history-multi-text-0",
                element_index=0,
                element_type="text",
                content_text="First spoken line.",
                is_speakable=1,
            )
            add_element(
                element_bid="element-history-multi-visual",
                element_index=1,
                element_type="html",
                content_text="<section>Cover slide</section>",
                is_speakable=0,
            )
            add_element(
                element_bid="element-history-multi-text-1",
                element_index=2,
                element_type="text",
                content_text="Second spoken line.",
                is_speakable=1,
            )
            add_element(
                element_bid="element-history-multi-text-2",
                element_index=3,
                element_type="text",
                content_text="Third spoken line.",
                is_speakable=1,
            )
            add_audio(position=0)
            add_audio(position=1)
            add_audio(position=2)
            db.session.commit()

            elements = get_final_elements_for_generated_block(
                generated_block_bid=generated_block_bid,
                user_bid="user-history-multi-position",
                shifu_bid="shifu-history-multi-position",
            )

        hydrated_audio = [
            element.payload.audio
            for element in elements
            if element.payload is not None and element.payload.audio is not None
        ]
        assert [audio.position for audio in hydrated_audio] == [0, 1, 2]
        assert [audio.audio_bid for audio in hydrated_audio] == [
            "audio-history-multi-0",
            "audio-history-multi-1",
            "audio-history-multi-2",
        ]

    def test_sparse_nonzero_audio_position_hydrates_matching_speakable_order(self):
        from flaskr.dao import db
        from flaskr.service.learn.listen_element_history import (
            get_final_elements_for_generated_block,
        )
        from flaskr.service.tts.models import AUDIO_STATUS_COMPLETED

        generated_block_bid = "generated-history-sparse-position"

        def add_element(
            *,
            element_bid: str,
            element_index: int,
            content_text: str,
        ):
            db.session.add(
                self.LearnGeneratedElement(
                    element_bid=element_bid,
                    progress_record_bid="progress-history-sparse-position",
                    user_bid="user-history-sparse-position",
                    generated_block_bid=generated_block_bid,
                    outline_item_bid="outline-history-sparse-position",
                    shifu_bid="shifu-history-sparse-position",
                    run_session_bid="run-history-sparse-position",
                    run_event_seq=element_index + 1,
                    event_type="element",
                    role="teacher",
                    element_index=element_index,
                    element_type="text",
                    element_type_code=213,
                    change_type="render",
                    target_element_bid="",
                    is_renderable=0,
                    is_new=1,
                    is_marker=0,
                    sequence_number=element_index + 1,
                    is_speakable=1,
                    audio_url="",
                    audio_segments="[]",
                    is_navigable=1,
                    is_final=1,
                    content_text=content_text,
                    payload='{"previous_visuals": []}',
                    deleted=0,
                    status=1,
                )
            )

        with self.app.app_context():
            db.session.query(self.LearnGeneratedAudio).delete()
            db.session.query(self.LearnGeneratedElement).delete()
            db.session.commit()

            add_element(
                element_bid="element-history-sparse-text-0",
                element_index=0,
                content_text="Skipped first line.",
            )
            add_element(
                element_bid="element-history-sparse-text-1",
                element_index=1,
                content_text="Second spoken line.",
            )
            db.session.add(
                self.LearnGeneratedAudio(
                    audio_bid="audio-history-sparse-1",
                    generated_block_bid=generated_block_bid,
                    position=1,
                    progress_record_bid="progress-history-sparse-position",
                    user_bid="user-history-sparse-position",
                    shifu_bid="shifu-history-sparse-position",
                    oss_url="https://example.com/history-sparse-1.mp3",
                    duration_ms=1001,
                    subtitle_cues=[
                        {
                            "text": "Second spoken line.",
                            "start_ms": 0,
                            "end_ms": 1001,
                            "segment_index": 0,
                            "position": 1,
                        }
                    ],
                    status=AUDIO_STATUS_COMPLETED,
                )
            )
            db.session.commit()

            elements = get_final_elements_for_generated_block(
                generated_block_bid=generated_block_bid,
                user_bid="user-history-sparse-position",
                shifu_bid="shifu-history-sparse-position",
            )

        audio_by_element_bid = {
            element.element_bid: element.payload.audio
            for element in elements
            if element.payload is not None
        }

        assert audio_by_element_bid["element-history-sparse-text-0"] is None
        assert audio_by_element_bid["element-history-sparse-text-1"] is not None
        assert audio_by_element_bid["element-history-sparse-text-1"].position == 1
        assert (
            audio_by_element_bid["element-history-sparse-text-1"].audio_bid
            == "audio-history-sparse-1"
        )

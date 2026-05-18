from types import SimpleNamespace

import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

import flaskr.dao as dao

if dao.db is None:
    _test_app = Flask("test-generated-block-tts-av-mode")
    _test_app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    _db = SQLAlchemy()
    _db.init_app(_test_app)
    dao.db = _db

if not hasattr(dao, "redis_client"):
    dao.redis_client = None


def _patch_run_tts_processor(monkeypatch):
    synthesized_texts = []

    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs._resolve_shifu_tts_settings",
        lambda *_args, **_kwargs: (
            "minimax",
            "test-model",
            type(
                "Voice",
                (),
                {
                    "voice_id": "voice",
                    "speed": 1.0,
                    "pitch": 0,
                    "emotion": "",
                    "volume": 1.0,
                },
            )(),
            type("Audio", (), {"format": "mp3", "sample_rate": 24000})(),
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured",
        lambda _provider: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.should_use_minimax_http_stream",
        lambda _provider: False,
    )

    def _fake_synthesize_text(**kwargs):
        synthesized_texts.append(kwargs["text"])
        return SimpleNamespace(
            audio_data=f"fake-audio:{kwargs['text']}".encode("utf-8"),
            duration_ms=123,
            word_count=1,
        )

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.synthesize_text",
        _fake_synthesize_text,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.concat_audio_best_effort",
        lambda parts: b"".join(parts),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.get_audio_duration_ms",
        lambda *_args, **_kwargs: 1000,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_handler.upload_audio_to_oss",
        lambda _app, _audio_bytes, audio_bid: (
            f"https://example.com/{audio_bid}.mp3",
            "test-bucket",
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_aggregated_usage",
        lambda **_kwargs: None,
    )

    return synthesized_texts


class TestGeneratedBlockListenTtsElementFirst:
    @classmethod
    def setup_class(cls):
        cls.app = Flask("generated-block-listen-tts")
        cls.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_BINDS={
                "ai_shifu_saas": "sqlite:///:memory:",
                "ai_shifu_admin": "sqlite:///:memory:",
            },
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        dao.db.init_app(cls.app)

        from flaskr.service.learn.models import (
            LearnGeneratedBlock,
            LearnGeneratedElement,
        )
        from flaskr.service.tts.models import LearnGeneratedAudio

        cls.LearnGeneratedBlock = LearnGeneratedBlock
        cls.LearnGeneratedElement = LearnGeneratedElement
        cls.LearnGeneratedAudio = LearnGeneratedAudio

        with cls.app.app_context():
            dao.db.create_all()

    def test_stream_generated_block_audio_non_listen_uses_run_tts_processor(
        self, monkeypatch
    ):
        from flaskr.dao import db
        from flaskr.service.learn.learn_dtos import GeneratedType
        from flaskr.service.learn.learn_funcs import stream_generated_block_audio

        user_bid = "user-manual-1"
        shifu_bid = "shifu-manual-1"
        generated_block_bid = "gen-manual-1"

        with self.app.app_context():
            db.session.query(self.LearnGeneratedAudio).delete()
            db.session.query(self.LearnGeneratedElement).delete()
            db.session.query(self.LearnGeneratedBlock).delete()
            db.session.commit()

            db.session.add(
                self.LearnGeneratedBlock(
                    generated_block_bid=generated_block_bid,
                    progress_record_bid="progress-manual-1",
                    user_bid=user_bid,
                    block_bid="block-manual-1",
                    outline_item_bid="outline-manual-1",
                    shifu_bid=shifu_bid,
                    type=1,
                    role=1,
                    generated_content="Manual audio backfill.",
                    position=0,
                    block_content_conf="",
                    status=1,
                )
            )
            db.session.commit()

        synthesized_texts = _patch_run_tts_processor(monkeypatch)

        events = list(
            stream_generated_block_audio(
                self.app,
                shifu_bid=shifu_bid,
                generated_block_bid=generated_block_bid,
                user_bid=user_bid,
                preview_mode=False,
                listen=False,
            )
        )

        audio_segment_events = [
            event for event in events if event.type == GeneratedType.AUDIO_SEGMENT
        ]
        audio_complete_events = [
            event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
        ]

        assert synthesized_texts == ["Manual audio backfill."]
        assert [event.content.position for event in audio_segment_events] == [0]
        assert [event.content.position for event in audio_complete_events] == [0]
        assert audio_complete_events[0].content.subtitle_cues[0].text == (
            "Manual audio backfill."
        )

        with self.app.app_context():
            records = (
                self.LearnGeneratedAudio.query.filter(
                    self.LearnGeneratedAudio.generated_block_bid == generated_block_bid,
                    self.LearnGeneratedAudio.user_bid == user_bid,
                    self.LearnGeneratedAudio.shifu_bid == shifu_bid,
                    self.LearnGeneratedAudio.deleted == 0,
                )
                .order_by(self.LearnGeneratedAudio.position.asc())
                .all()
            )
            assert [record.position for record in records] == [0]
            assert records[0].subtitle_cues[0]["text"] == ("Manual audio backfill.")

    def test_stream_generated_block_audio_non_listen_ignores_segmented_listen_cache(
        self, monkeypatch
    ):
        from flaskr.dao import db
        from flaskr.service.learn.learn_dtos import GeneratedType
        from flaskr.service.learn.learn_funcs import stream_generated_block_audio
        from flaskr.service.tts.models import AUDIO_STATUS_COMPLETED

        user_bid = "user-manual-cache-1"
        shifu_bid = "shifu-manual-cache-1"
        generated_block_bid = "gen-manual-cache-1"
        generated_content = "Whole manual audio sentence."

        with self.app.app_context():
            db.session.query(self.LearnGeneratedAudio).delete()
            db.session.query(self.LearnGeneratedElement).delete()
            db.session.query(self.LearnGeneratedBlock).delete()
            db.session.commit()

            db.session.add(
                self.LearnGeneratedBlock(
                    generated_block_bid=generated_block_bid,
                    progress_record_bid="progress-manual-cache-1",
                    user_bid=user_bid,
                    block_bid="block-manual-cache-1",
                    outline_item_bid="outline-manual-cache-1",
                    shifu_bid=shifu_bid,
                    type=1,
                    role=1,
                    generated_content=generated_content,
                    position=0,
                    block_content_conf="",
                    status=1,
                )
            )
            db.session.add_all(
                [
                    self.LearnGeneratedAudio(
                        audio_bid="audio-cache-position-0",
                        generated_block_bid=generated_block_bid,
                        position=0,
                        progress_record_bid="progress-manual-cache-1",
                        user_bid=user_bid,
                        shifu_bid=shifu_bid,
                        oss_url="https://example.com/listen-position-0.mp3",
                        oss_bucket="test-bucket",
                        oss_object_key="tts-audio/listen-position-0.mp3",
                        duration_ms=1000,
                        file_size=10,
                        audio_format="mp3",
                        sample_rate=24000,
                        voice_id="voice",
                        voice_settings={},
                        model="test-model",
                        text_length=len("First page."),
                        segment_count=1,
                        subtitle_cues=[
                            {
                                "text": "First page.",
                                "start_ms": 0,
                                "end_ms": 1000,
                                "segment_index": 0,
                                "position": 0,
                            }
                        ],
                        status=AUDIO_STATUS_COMPLETED,
                        deleted=0,
                    ),
                    self.LearnGeneratedAudio(
                        audio_bid="audio-cache-position-1",
                        generated_block_bid=generated_block_bid,
                        position=1,
                        progress_record_bid="progress-manual-cache-1",
                        user_bid=user_bid,
                        shifu_bid=shifu_bid,
                        oss_url="https://example.com/listen-position-1.mp3",
                        oss_bucket="test-bucket",
                        oss_object_key="tts-audio/listen-position-1.mp3",
                        duration_ms=1000,
                        file_size=10,
                        audio_format="mp3",
                        sample_rate=24000,
                        voice_id="voice",
                        voice_settings={},
                        model="test-model",
                        text_length=len("Second page."),
                        segment_count=1,
                        subtitle_cues=[
                            {
                                "text": "Second page.",
                                "start_ms": 0,
                                "end_ms": 1000,
                                "segment_index": 0,
                                "position": 1,
                            }
                        ],
                        status=AUDIO_STATUS_COMPLETED,
                        deleted=0,
                    ),
                ]
            )
            db.session.commit()

        synthesized_texts = _patch_run_tts_processor(monkeypatch)

        events = list(
            stream_generated_block_audio(
                self.app,
                shifu_bid=shifu_bid,
                generated_block_bid=generated_block_bid,
                user_bid=user_bid,
                preview_mode=False,
                listen=False,
            )
        )

        audio_complete_events = [
            event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
        ]

        assert synthesized_texts == [generated_content]
        assert audio_complete_events[-1].content.audio_url not in {
            "https://example.com/listen-position-0.mp3",
            "https://example.com/listen-position-1.mp3",
        }
        assert audio_complete_events[-1].content.subtitle_cues[0].text == (
            generated_content
        )

    def test_stream_generated_block_audio_listen_uses_text_elements_only(
        self, monkeypatch
    ):
        from flaskr.dao import db
        from flaskr.service.learn.learn_dtos import GeneratedType
        from flaskr.service.learn.learn_funcs import stream_generated_block_audio

        user_bid = "user-1"
        shifu_bid = "shifu-1"
        generated_block_bid = "gen-1"

        with self.app.app_context():
            db.session.query(self.LearnGeneratedAudio).delete()
            db.session.query(self.LearnGeneratedElement).delete()
            db.session.query(self.LearnGeneratedBlock).delete()
            db.session.commit()

            block = self.LearnGeneratedBlock(
                generated_block_bid=generated_block_bid,
                progress_record_bid="progress-1",
                user_bid=user_bid,
                block_bid="block-1",
                outline_item_bid="outline-1",
                shifu_bid=shifu_bid,
                type=1,
                role=1,
                generated_content="First.\n\n<svg><text>v</text></svg>\n\nSecond.",
                position=0,
                block_content_conf="",
                status=1,
            )
            db.session.add(block)
            db.session.add_all(
                [
                    self.LearnGeneratedElement(
                        element_bid="el-text-1",
                        progress_record_bid="progress-1",
                        user_bid=user_bid,
                        generated_block_bid=generated_block_bid,
                        outline_item_bid="outline-1",
                        shifu_bid=shifu_bid,
                        run_session_bid="run-1",
                        run_event_seq=1,
                        event_type="element",
                        role="teacher",
                        element_index=0,
                        element_type="text",
                        change_type="render",
                        is_renderable=0,
                        is_new=1,
                        is_marker=0,
                        sequence_number=1,
                        is_speakable=1,
                        is_navigable=1,
                        is_final=1,
                        content_text="First.",
                        payload="",
                        status=1,
                        deleted=0,
                    ),
                    self.LearnGeneratedElement(
                        element_bid="el-html-1",
                        progress_record_bid="progress-1",
                        user_bid=user_bid,
                        generated_block_bid=generated_block_bid,
                        outline_item_bid="outline-1",
                        shifu_bid=shifu_bid,
                        run_session_bid="run-1",
                        run_event_seq=2,
                        event_type="element",
                        role="teacher",
                        element_index=1,
                        element_type="html",
                        change_type="render",
                        is_renderable=1,
                        is_new=1,
                        is_marker=0,
                        sequence_number=2,
                        is_speakable=0,
                        is_navigable=1,
                        is_final=1,
                        content_text="",
                        payload="",
                        status=1,
                        deleted=0,
                    ),
                    self.LearnGeneratedElement(
                        element_bid="el-text-2",
                        progress_record_bid="progress-1",
                        user_bid=user_bid,
                        generated_block_bid=generated_block_bid,
                        outline_item_bid="outline-1",
                        shifu_bid=shifu_bid,
                        run_session_bid="run-1",
                        run_event_seq=3,
                        event_type="element",
                        role="teacher",
                        element_index=2,
                        element_type="text",
                        change_type="render",
                        is_renderable=0,
                        is_new=1,
                        is_marker=0,
                        sequence_number=3,
                        is_speakable=1,
                        is_navigable=1,
                        is_final=1,
                        content_text="Second.",
                        payload="",
                        status=1,
                        deleted=0,
                    ),
                ]
            )
            db.session.commit()

        synthesized_texts = _patch_run_tts_processor(monkeypatch)

        events = list(
            stream_generated_block_audio(
                self.app,
                shifu_bid=shifu_bid,
                generated_block_bid=generated_block_bid,
                user_bid=user_bid,
                preview_mode=False,
                listen=True,
            )
        )

        complete_positions = [
            event.content.position
            for event in events
            if event.type == GeneratedType.AUDIO_COMPLETE
        ]
        segment_positions = [
            event.content.position
            for event in events
            if event.type == GeneratedType.AUDIO_SEGMENT
        ]

        assert complete_positions == [0, 1]
        assert segment_positions == [0, 1]
        assert synthesized_texts == ["First.", "Second."]
        assert events[-1].type == GeneratedType.DONE
        audio_complete_events = [
            event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
        ]
        assert [
            event.content.stream_element_number for event in audio_complete_events
        ] == [0, 2]
        assert [
            event.content.stream_element_type for event in audio_complete_events
        ] == ["text", "text"]
        assert [cue.text for cue in audio_complete_events[0].content.subtitle_cues] == [
            "First."
        ]
        assert [cue.text for cue in audio_complete_events[1].content.subtitle_cues] == [
            "Second."
        ]
        assert all(
            event.content.av_contract is None
            for event in events
            if event.type == GeneratedType.AUDIO_COMPLETE
        )

        with self.app.app_context():
            records = (
                self.LearnGeneratedAudio.query.filter(
                    self.LearnGeneratedAudio.generated_block_bid == generated_block_bid,
                    self.LearnGeneratedAudio.user_bid == user_bid,
                    self.LearnGeneratedAudio.shifu_bid == shifu_bid,
                    self.LearnGeneratedAudio.deleted == 0,
                )
                .order_by(self.LearnGeneratedAudio.position.asc())
                .all()
            )
            assert [r.position for r in records] == [0, 1]
            assert all(r.oss_url for r in records)
            assert records[0].subtitle_cues[0]["text"] == "First."
            assert records[1].subtitle_cues[0]["text"] == "Second."

    def test_stream_generated_block_audio_listen_preserves_position_after_short_text(
        self, monkeypatch
    ):
        from flaskr.dao import db
        from flaskr.service.learn.learn_dtos import GeneratedType
        from flaskr.service.learn.learn_funcs import stream_generated_block_audio

        user_bid = "user-short-1"
        shifu_bid = "shifu-short-1"
        generated_block_bid = "gen-short-1"

        with self.app.app_context():
            db.session.query(self.LearnGeneratedAudio).delete()
            db.session.query(self.LearnGeneratedElement).delete()
            db.session.query(self.LearnGeneratedBlock).delete()
            db.session.commit()

            block = self.LearnGeneratedBlock(
                generated_block_bid=generated_block_bid,
                progress_record_bid="progress-short-1",
                user_bid=user_bid,
                block_bid="block-short-1",
                outline_item_bid="outline-short-1",
                shifu_bid=shifu_bid,
                type=1,
                role=1,
                generated_content="A\n\nSecond page.",
                position=0,
                block_content_conf="",
                status=1,
            )
            db.session.add(block)
            db.session.add_all(
                [
                    self.LearnGeneratedElement(
                        element_bid="el-short-text-1",
                        progress_record_bid="progress-short-1",
                        user_bid=user_bid,
                        generated_block_bid=generated_block_bid,
                        outline_item_bid="outline-short-1",
                        shifu_bid=shifu_bid,
                        run_session_bid="run-short-1",
                        run_event_seq=1,
                        event_type="element",
                        role="teacher",
                        element_index=0,
                        element_type="text",
                        change_type="render",
                        is_renderable=0,
                        is_new=1,
                        is_marker=0,
                        sequence_number=1,
                        is_speakable=1,
                        is_navigable=1,
                        is_final=1,
                        content_text="A",
                        payload="",
                        status=1,
                        deleted=0,
                    ),
                    self.LearnGeneratedElement(
                        element_bid="el-short-text-2",
                        progress_record_bid="progress-short-1",
                        user_bid=user_bid,
                        generated_block_bid=generated_block_bid,
                        outline_item_bid="outline-short-1",
                        shifu_bid=shifu_bid,
                        run_session_bid="run-short-1",
                        run_event_seq=2,
                        event_type="element",
                        role="teacher",
                        element_index=1,
                        element_type="text",
                        change_type="render",
                        is_renderable=0,
                        is_new=1,
                        is_marker=0,
                        sequence_number=2,
                        is_speakable=1,
                        is_navigable=1,
                        is_final=1,
                        content_text="Second page.",
                        payload="",
                        status=1,
                        deleted=0,
                    ),
                ]
            )
            db.session.commit()

        synthesized_texts = _patch_run_tts_processor(monkeypatch)

        events = list(
            stream_generated_block_audio(
                self.app,
                shifu_bid=shifu_bid,
                generated_block_bid=generated_block_bid,
                user_bid=user_bid,
                preview_mode=False,
                listen=True,
            )
        )

        complete_positions = [
            event.content.position
            for event in events
            if event.type == GeneratedType.AUDIO_COMPLETE
        ]

        assert complete_positions == [1]
        assert synthesized_texts == ["Second page."]
        assert events[-1].type == GeneratedType.DONE

    def test_stream_generated_block_audio_listen_reuses_partial_segment_cache(
        self, monkeypatch
    ):
        from flaskr.dao import db
        from flaskr.service.learn.learn_dtos import GeneratedType
        from flaskr.service.learn.learn_funcs import stream_generated_block_audio
        from flaskr.service.tts.models import AUDIO_STATUS_COMPLETED

        user_bid = "user-cache-1"
        shifu_bid = "shifu-cache-1"
        generated_block_bid = "gen-cache-1"

        with self.app.app_context():
            db.session.query(self.LearnGeneratedAudio).delete()
            db.session.query(self.LearnGeneratedElement).delete()
            db.session.query(self.LearnGeneratedBlock).delete()
            db.session.commit()

            block = self.LearnGeneratedBlock(
                generated_block_bid=generated_block_bid,
                progress_record_bid="progress-cache-1",
                user_bid=user_bid,
                block_bid="block-cache-1",
                outline_item_bid="outline-cache-1",
                shifu_bid=shifu_bid,
                type=1,
                role=1,
                generated_content="First.\n\nSecond.",
                position=0,
                block_content_conf="",
                status=1,
            )
            db.session.add(block)
            db.session.add_all(
                [
                    self.LearnGeneratedElement(
                        element_bid="el-cache-text-1",
                        progress_record_bid="progress-cache-1",
                        user_bid=user_bid,
                        generated_block_bid=generated_block_bid,
                        outline_item_bid="outline-cache-1",
                        shifu_bid=shifu_bid,
                        run_session_bid="run-cache-1",
                        run_event_seq=1,
                        event_type="element",
                        role="teacher",
                        element_index=0,
                        element_type="text",
                        change_type="render",
                        is_renderable=0,
                        is_new=1,
                        is_marker=0,
                        sequence_number=1,
                        is_speakable=1,
                        is_navigable=1,
                        is_final=1,
                        content_text="First.",
                        payload="",
                        status=1,
                        deleted=0,
                    ),
                    self.LearnGeneratedElement(
                        element_bid="el-cache-text-2",
                        progress_record_bid="progress-cache-1",
                        user_bid=user_bid,
                        generated_block_bid=generated_block_bid,
                        outline_item_bid="outline-cache-1",
                        shifu_bid=shifu_bid,
                        run_session_bid="run-cache-1",
                        run_event_seq=2,
                        event_type="element",
                        role="teacher",
                        element_index=1,
                        element_type="text",
                        change_type="render",
                        is_renderable=0,
                        is_new=1,
                        is_marker=0,
                        sequence_number=2,
                        is_speakable=1,
                        is_navigable=1,
                        is_final=1,
                        content_text="Second.",
                        payload="",
                        status=1,
                        deleted=0,
                    ),
                ]
            )
            db.session.add(
                self.LearnGeneratedAudio(
                    audio_bid="audio-cache-0",
                    generated_block_bid=generated_block_bid,
                    position=0,
                    progress_record_bid="progress-cache-1",
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    oss_url="https://example.com/audio-cache-0.mp3",
                    oss_bucket="test-bucket",
                    oss_object_key="tts-audio/audio-cache-0.mp3",
                    duration_ms=1000,
                    file_size=10,
                    audio_format="mp3",
                    sample_rate=24000,
                    voice_id="voice",
                    voice_settings={},
                    model="test-model",
                    text_length=len("First."),
                    segment_count=1,
                    subtitle_cues=[
                        {
                            "text": "First.",
                            "start_ms": 0,
                            "end_ms": 1000,
                            "segment_index": 0,
                            "position": 0,
                        }
                    ],
                    status=AUDIO_STATUS_COMPLETED,
                    deleted=0,
                )
            )
            db.session.commit()

        synthesized_texts = _patch_run_tts_processor(monkeypatch)

        events = list(
            stream_generated_block_audio(
                self.app,
                shifu_bid=shifu_bid,
                generated_block_bid=generated_block_bid,
                user_bid=user_bid,
                preview_mode=False,
                listen=True,
            )
        )

        audio_complete_events = [
            event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
        ]
        assert [event.content.position for event in audio_complete_events] == [0, 1]
        assert [
            event.content.stream_element_number for event in audio_complete_events
        ] == [0, 1]
        assert audio_complete_events[0].content.audio_url == (
            "https://example.com/audio-cache-0.mp3"
        )
        assert synthesized_texts == ["Second."]
        assert events[-1].type == GeneratedType.DONE

        with self.app.app_context():
            records = (
                self.LearnGeneratedAudio.query.filter(
                    self.LearnGeneratedAudio.generated_block_bid == generated_block_bid,
                    self.LearnGeneratedAudio.user_bid == user_bid,
                    self.LearnGeneratedAudio.shifu_bid == shifu_bid,
                    self.LearnGeneratedAudio.deleted == 0,
                )
                .order_by(self.LearnGeneratedAudio.position.asc())
                .all()
            )
            assert [r.position for r in records] == [0, 1]
            assert records[0].audio_bid == "audio-cache-0"

    def test_stream_generated_block_audio_listen_ignores_cache_with_mismatched_subtitles(
        self, monkeypatch
    ):
        from flaskr.dao import db
        from flaskr.service.learn.learn_dtos import GeneratedType
        from flaskr.service.learn.learn_funcs import stream_generated_block_audio
        from flaskr.service.tts.models import AUDIO_STATUS_COMPLETED

        user_bid = "user-cache-subtitle-mismatch-1"
        shifu_bid = "shifu-cache-subtitle-mismatch-1"
        generated_block_bid = "gen-cache-subtitle-mismatch-1"

        with self.app.app_context():
            db.session.query(self.LearnGeneratedAudio).delete()
            db.session.query(self.LearnGeneratedElement).delete()
            db.session.query(self.LearnGeneratedBlock).delete()
            db.session.commit()

            db.session.add(
                self.LearnGeneratedBlock(
                    generated_block_bid=generated_block_bid,
                    progress_record_bid="progress-cache-subtitle-mismatch-1",
                    user_bid=user_bid,
                    block_bid="block-cache-subtitle-mismatch-1",
                    outline_item_bid="outline-cache-subtitle-mismatch-1",
                    shifu_bid=shifu_bid,
                    type=1,
                    role=1,
                    generated_content="First.",
                    position=0,
                    block_content_conf="",
                    status=1,
                )
            )
            db.session.add(
                self.LearnGeneratedElement(
                    element_bid="el-cache-subtitle-mismatch-1",
                    progress_record_bid="progress-cache-subtitle-mismatch-1",
                    user_bid=user_bid,
                    generated_block_bid=generated_block_bid,
                    outline_item_bid="outline-cache-subtitle-mismatch-1",
                    shifu_bid=shifu_bid,
                    run_session_bid="run-cache-subtitle-mismatch-1",
                    run_event_seq=1,
                    event_type="element",
                    role="teacher",
                    element_index=0,
                    element_type="text",
                    change_type="render",
                    is_renderable=0,
                    is_new=1,
                    is_marker=0,
                    sequence_number=1,
                    is_speakable=1,
                    is_navigable=1,
                    is_final=1,
                    content_text="First.",
                    payload="",
                    status=1,
                    deleted=0,
                )
            )
            db.session.add(
                self.LearnGeneratedAudio(
                    audio_bid="audio-cache-subtitle-mismatch-0",
                    generated_block_bid=generated_block_bid,
                    position=0,
                    progress_record_bid="progress-cache-subtitle-mismatch-1",
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    oss_url="https://example.com/stale-subtitle-cache.mp3",
                    oss_bucket="test-bucket",
                    oss_object_key="tts-audio/stale-subtitle-cache.mp3",
                    duration_ms=1000,
                    file_size=10,
                    audio_format="mp3",
                    sample_rate=24000,
                    voice_id="voice",
                    voice_settings={},
                    model="test-model",
                    text_length=len("First."),
                    segment_count=1,
                    subtitle_cues=[
                        {
                            "text": "Other.",
                            "start_ms": 0,
                            "end_ms": 1000,
                            "segment_index": 0,
                            "position": 0,
                        }
                    ],
                    status=AUDIO_STATUS_COMPLETED,
                    deleted=0,
                )
            )
            db.session.commit()

        synthesized_texts = _patch_run_tts_processor(monkeypatch)

        events = list(
            stream_generated_block_audio(
                self.app,
                shifu_bid=shifu_bid,
                generated_block_bid=generated_block_bid,
                user_bid=user_bid,
                preview_mode=False,
                listen=True,
            )
        )

        audio_complete_events = [
            event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
        ]
        assert synthesized_texts == ["First."]
        assert audio_complete_events[0].content.audio_url != (
            "https://example.com/stale-subtitle-cache.mp3"
        )
        assert audio_complete_events[0].content.subtitle_cues[0].text == "First."
        assert events[-1].type == GeneratedType.DONE

    def test_stream_generated_block_audio_listen_raises_when_finalize_has_no_complete(
        self, monkeypatch
    ):
        from flaskr.dao import db
        from flaskr.service.common.models import AppException
        from flaskr.service.learn.learn_funcs import stream_generated_block_audio

        user_bid = "user-finalize-no-complete-1"
        shifu_bid = "shifu-finalize-no-complete-1"
        generated_block_bid = "gen-finalize-no-complete-1"

        with self.app.app_context():
            db.session.query(self.LearnGeneratedAudio).delete()
            db.session.query(self.LearnGeneratedElement).delete()
            db.session.query(self.LearnGeneratedBlock).delete()
            db.session.commit()

            db.session.add(
                self.LearnGeneratedBlock(
                    generated_block_bid=generated_block_bid,
                    progress_record_bid="progress-finalize-no-complete-1",
                    user_bid=user_bid,
                    block_bid="block-finalize-no-complete-1",
                    outline_item_bid="outline-finalize-no-complete-1",
                    shifu_bid=shifu_bid,
                    type=1,
                    role=1,
                    generated_content="First.",
                    position=0,
                    block_content_conf="",
                    status=1,
                )
            )
            db.session.add(
                self.LearnGeneratedElement(
                    element_bid="el-finalize-no-complete-1",
                    progress_record_bid="progress-finalize-no-complete-1",
                    user_bid=user_bid,
                    generated_block_bid=generated_block_bid,
                    outline_item_bid="outline-finalize-no-complete-1",
                    shifu_bid=shifu_bid,
                    run_session_bid="run-finalize-no-complete-1",
                    run_event_seq=1,
                    event_type="element",
                    role="teacher",
                    element_index=0,
                    element_type="text",
                    change_type="render",
                    is_renderable=0,
                    is_new=1,
                    is_marker=0,
                    sequence_number=1,
                    is_speakable=1,
                    is_navigable=1,
                    is_final=1,
                    content_text="First.",
                    payload="",
                    status=1,
                    deleted=0,
                )
            )
            db.session.commit()

        _patch_run_tts_processor(monkeypatch)
        monkeypatch.setattr(
            "flaskr.service.tts.streaming_tts.concat_audio_best_effort",
            lambda _parts: b"",
        )

        with pytest.raises(AppException):
            list(
                stream_generated_block_audio(
                    self.app,
                    shifu_bid=shifu_bid,
                    generated_block_bid=generated_block_bid,
                    user_bid=user_bid,
                    preview_mode=False,
                    listen=True,
                )
            )

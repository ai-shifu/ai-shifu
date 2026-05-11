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

        synthesized_texts = []

        def _fake_yield_tts_segments(*, text, **_kwargs):
            synthesized_texts.append(text)
            yield (0, b"fake-audio", 123, text, 1, 1)

        monkeypatch.setattr(
            "flaskr.service.learn.learn_funcs._yield_tts_segments",
            _fake_yield_tts_segments,
        )
        monkeypatch.setattr(
            "flaskr.service.learn.learn_funcs.assemble_audio_for_upload",
            lambda parts, **_kwargs: type(
                "AssemblyResult",
                (),
                {
                    "audio_data": b"".join(parts),
                    "duration_ms": 1000,
                    "included_segment_indices": tuple(range(len(parts))),
                    "source_segment_count": len(parts),
                    "segment_count": len(parts),
                    "used_fallback": False,
                },
            )(),
        )
        monkeypatch.setattr(
            "flaskr.service.learn.learn_funcs.upload_audio_to_oss",
            lambda _app, _audio_bytes, audio_bid: (
                f"https://example.com/{audio_bid}.mp3",
                "test-bucket",
            ),
        )
        monkeypatch.setattr(
            "flaskr.service.learn.learn_funcs.record_tts_usage",
            lambda *_args, **_kwargs: None,
        )

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
        audio_complete_events = [
            event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
        ]
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

    def test_stream_generated_block_audio_listen_keeps_short_text_positions(
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

        synthesized_texts = []

        def _fake_yield_tts_segments(*, text, **_kwargs):
            synthesized_texts.append(text)
            yield (0, b"fake-audio", 123, text, 1, 1)

        monkeypatch.setattr(
            "flaskr.service.learn.learn_funcs._yield_tts_segments",
            _fake_yield_tts_segments,
        )
        monkeypatch.setattr(
            "flaskr.service.learn.learn_funcs.assemble_audio_for_upload",
            lambda parts, **_kwargs: type(
                "AssemblyResult",
                (),
                {
                    "audio_data": b"".join(parts),
                    "duration_ms": 1000,
                    "included_segment_indices": tuple(range(len(parts))),
                    "source_segment_count": len(parts),
                    "segment_count": len(parts),
                    "used_fallback": False,
                },
            )(),
        )
        monkeypatch.setattr(
            "flaskr.service.learn.learn_funcs.upload_audio_to_oss",
            lambda _app, _audio_bytes, audio_bid: (
                f"https://example.com/{audio_bid}.mp3",
                "test-bucket",
            ),
        )
        monkeypatch.setattr(
            "flaskr.service.learn.learn_funcs.record_tts_usage",
            lambda *_args, **_kwargs: None,
        )

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

        assert complete_positions == [0, 1]
        assert synthesized_texts == ["A", "Second page."]

    def test_finalize_tts_stream_audio_fallback_matches_uploaded_audio(
        self, monkeypatch
    ):
        from types import SimpleNamespace

        from flaskr.service.learn.learn_funcs import _finalize_tts_stream_audio

        monkeypatch.setattr(
            "flaskr.service.learn.learn_funcs.assemble_audio_for_upload",
            lambda parts, **_kwargs: SimpleNamespace(
                audio_data=parts[0],
                duration_ms=123,
                included_segment_indices=(0,),
                source_segment_count=len(parts),
                segment_count=1,
                used_fallback=True,
            ),
        )
        monkeypatch.setattr(
            "flaskr.service.learn.learn_funcs.upload_audio_to_oss",
            lambda _app, _audio_bytes, audio_bid: (
                f"https://example.com/{audio_bid}.mp3",
                "test-bucket",
            ),
        )

        saved_records = []
        monkeypatch.setattr(
            "flaskr.service.learn.learn_funcs.save_audio_record",
            lambda record, commit=True: saved_records.append(record),
        )

        subtitle_cues = [
            {
                "text": "First sentence.",
                "start_ms": 0,
                "end_ms": 123,
                "segment_index": 0,
            },
            {
                "text": "Second sentence.",
                "start_ms": 123,
                "end_ms": 456,
                "segment_index": 1,
            },
        ]

        _oss_url, duration_ms = _finalize_tts_stream_audio(
            self.app,
            audio_parts=[b"first-audio", b"second-audio"],
            segment_durations_ms=[123, 333],
            subtitle_cues=subtitle_cues,
            audio_bid="fallback-audio",
            audio_settings=SimpleNamespace(format="mp3", sample_rate=24000),
            voice_settings=SimpleNamespace(
                voice_id="voice",
                speed=1.0,
                pitch=0,
                emotion="",
                volume=1.0,
            ),
            tts_model="test-model",
            cleaned_text="First sentence. Second sentence.",
            segment_count=2,
            persist_audio=True,
            generated_block_bid="generated-fallback",
            progress_record_bid="progress-fallback",
            user_bid="user-fallback",
            shifu_bid="shifu-fallback",
        )

        assert duration_ms == 123
        assert [cue["text"] for cue in subtitle_cues] == ["First sentence."]
        assert saved_records[0].duration_ms == 123
        assert saved_records[0].segment_count == 1
        assert [cue["text"] for cue in saved_records[0].subtitle_cues] == [
            "First sentence."
        ]

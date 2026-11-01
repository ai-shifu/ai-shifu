"""Verify listen element history subtitles behavior."""

from flask import Flask
from flaskr import dao
from flaskr.dao import db
from flaskr.service.learn.elements.history import (
    get_final_elements_for_generated_block,
)
from flaskr.service.learn.models import LearnGeneratedElement
from flaskr.service.tts.models import AUDIO_STATUS_COMPLETED, LearnGeneratedAudio

from tests.service.learn.listen_element_helpers import ListenScope, subtitle_cues


def _scope(slug: str) -> ListenScope:
    return ListenScope(
        f"history-{slug}", generated_block_bid=f"generated-history-{slug}"
    )


def _add_element(
    scope: ListenScope,
    element_bid: str,
    element_index: int,
    content_text: str,
    *,
    element_type: str = "text",
    is_speakable: int = 1,
    payload: str = '{"previous_visuals": []}',
) -> None:
    """Persist one final element; non-text elements become visual markers."""
    is_text = element_type == "text"
    db.session.add(
        scope.element(
            element_bid=element_bid,
            run_event_seq=element_index + 1,
            element_index=element_index,
            element_type=element_type,
            element_type_code=213 if is_text else 201,
            change_type="render",
            is_renderable=0 if is_text else 1,
            is_marker=0 if is_text else 1,
            sequence_number=element_index + 1,
            is_speakable=is_speakable,
            is_final=1,
            content_text=content_text,
            payload=payload,
        )
    )


def _add_audio(
    scope: ListenScope,
    audio_bid: str,
    position: int,
    duration_ms: int,
    cue_text: str,
    oss_url: str,
) -> None:
    db.session.add(
        LearnGeneratedAudio(
            audio_bid=audio_bid,
            generated_block_bid=scope.generated_block_bid,
            position=position,
            progress_record_bid=scope.progress_bid,
            user_bid=scope.user_bid,
            shifu_bid=scope.shifu_bid,
            oss_url=oss_url,
            duration_ms=duration_ms,
            subtitle_cues=subtitle_cues((cue_text, 0, duration_ms), position=position),
            status=AUDIO_STATUS_COMPLETED,
        )
    )


def _final_elements(scope: ListenScope) -> list:
    db.session.commit()
    return get_final_elements_for_generated_block(
        generated_block_bid=scope.generated_block_bid,
        user_bid=scope.user_bid,
        shifu_bid=scope.shifu_bid,
    )


class TestListenElementHistorySubtitles:
    """Verify listen element history subtitles behavior."""

    @classmethod
    def setup_class(cls) -> None:
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

        with cls.app.app_context():
            dao.db.create_all()

    def setup_method(self) -> None:
        with self.app.app_context():
            db.session.query(LearnGeneratedAudio).delete()
            db.session.query(LearnGeneratedElement).delete()
            db.session.commit()

    def test_final_elements_are_hydrated_from_persisted_audio_subtitles(self) -> None:
        scope = _scope("subtitles")

        with self.app.app_context():
            _add_element(
                scope,
                "element-history-subtitles",
                0,
                "Hello subtitle history.",
                payload=(
                    '{"audio": {"position": 0, "audio_url": "", "audio_bid": "", '
                    '"duration_ms": 0}, "previous_visuals": []}'
                ),
            )
            _add_audio(
                scope,
                "audio-history-subtitles",
                0,
                640,
                "Hello subtitle history.",
                "https://example.com/history-subtitles.mp3",
            )
            elements = _final_elements(scope)

        assert len(elements) == 1
        element = elements[0]
        assert element.audio_url == "https://example.com/history-subtitles.mp3"
        assert element.payload is not None
        assert element.payload.audio is not None
        assert element.payload.audio.audio_bid == "audio-history-subtitles"
        assert element.payload.audio.subtitle_cues[0].text == "Hello subtitle history."

    def test_multi_position_audio_is_hydrated_by_speakable_element_order(self) -> None:
        scope = _scope("multi-position")

        with self.app.app_context():
            _add_element(scope, "element-history-multi-text-0", 0, "First spoken line.")
            _add_element(
                scope,
                "element-history-multi-visual",
                1,
                "<section>Cover slide</section>",
                element_type="html",
                is_speakable=0,
            )
            _add_element(
                scope, "element-history-multi-text-1", 2, "Second spoken line."
            )
            _add_element(scope, "element-history-multi-text-2", 3, "Third spoken line.")
            for position in range(3):
                _add_audio(
                    scope,
                    f"audio-history-multi-{position}",
                    position,
                    1000 + position,
                    f"Line {position}",
                    f"https://example.com/history-multi-{position}.mp3",
                )
            elements = _final_elements(scope)

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

    def test_sparse_nonzero_audio_position_hydrates_matching_speakable_order(
        self,
    ) -> None:
        scope = _scope("sparse-position")

        with self.app.app_context():
            _add_element(
                scope, "element-history-sparse-text-0", 0, "Skipped first line."
            )
            _add_element(
                scope, "element-history-sparse-text-1", 1, "Second spoken line."
            )
            _add_audio(
                scope,
                "audio-history-sparse-1",
                1,
                1001,
                "Second spoken line.",
                "https://example.com/history-sparse-1.mp3",
            )
            elements = _final_elements(scope)

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

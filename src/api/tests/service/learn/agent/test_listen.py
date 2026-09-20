"""Cover the spoken track of a 2.0 lesson.

The rule throughout: a lesson that cannot be spoken is still taught. Every failure here degrades to
silence rather than interrupting the learner, so each one is asserted rather than assumed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flaskr.service.learn.agent import listen

if TYPE_CHECKING:
    import pytest


class _App:
    logger = logging.getLogger("test_listen")


class _Processor:
    """Stands in for the streaming TTS processor: records text, returns audio events."""

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.finalized = False

    def process_chunk(self, text: str) -> list[str]:
        self.spoken.append(text)
        return [f"audio:{text}"]

    def finalize(self, *, commit: bool) -> list[str]:  # noqa: ARG002
        self.finalized = True
        return ["audio:tail"]


def _voice(monkeypatch: pytest.MonkeyPatch, processor: object) -> listen.LessonVoice:
    monkeypatch.setattr(listen, "create_tts_processor", lambda *_a, **_k: processor)
    return listen.LessonVoice(
        _App(),
        shifu_model=object,
        shifu_bid="shifu-bid",
        outline_bid="outline-bid",
        progress_record_bid="progress-bid",
        user_bid="user-bid",
        generated_block_bid="block-bid",
    )


def test_what_the_lesson_says_is_spoken(monkeypatch: pytest.MonkeyPatch) -> None:
    processor = _Processor()
    voice = _voice(monkeypatch, processor)

    assert list(voice.speak("Hello ")) == ["audio:Hello "]
    assert list(voice.speak("world.")) == ["audio:world."]
    assert processor.spoken == ["Hello ", "world."]


def test_the_last_sentence_is_not_lost(monkeypatch: pytest.MonkeyPatch) -> None:
    """Synthesis is usually mid-sentence when the text runs out."""
    processor = _Processor()
    voice = _voice(monkeypatch, processor)
    list(voice.speak("a"))

    assert list(voice.finish()) == ["audio:tail"]
    assert processor.finalized is True


def test_a_turn_that_says_nothing_opens_no_synthesis_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[int] = []
    monkeypatch.setattr(
        listen,
        "create_tts_processor",
        lambda *_a, **_k: created.append(1) or _Processor(),
    )
    voice = listen.LessonVoice(
        _App(),
        shifu_model=object,
        shifu_bid="shifu-bid",
        outline_bid="outline-bid",
        progress_record_bid="progress-bid",
        user_bid="user-bid",
        generated_block_bid="block-bid",
    )

    assert list(voice.speak("")) == []
    assert list(voice.finish()) == []
    assert created == []


def test_a_course_without_tts_is_taught_in_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TTS switched off, or settings that do not validate: the lesson still runs."""
    attempts: list[int] = []
    monkeypatch.setattr(
        listen,
        "create_tts_processor",
        lambda *_a, **_k: attempts.append(1) and None,
    )
    voice = _voice(monkeypatch, None)
    monkeypatch.setattr(
        listen,
        "create_tts_processor",
        lambda *_a, **_k: attempts.append(1) or None,
    )

    assert list(voice.speak("a")) == []
    assert list(voice.speak("b")) == []
    # Asked once, not once per chunk.
    assert len(attempts) == 1


def test_a_provider_failure_does_not_interrupt_the_lesson(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Failing(_Processor):
        def process_chunk(self, _text: str) -> list[str]:
            message = "provider is down"
            raise RuntimeError(message)

    voice = _voice(monkeypatch, _Failing())
    monkeypatch.setattr(listen, "cleanup_session_after", lambda *_a, **_k: None)

    assert list(voice.speak("a")) == []
    # And it stops trying, rather than failing once per chunk for the rest of the turn.
    assert list(voice.speak("b")) == []


def test_a_failure_while_finishing_is_also_survivable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingTail(_Processor):
        def finalize(self, *, commit: bool = False) -> list[str]:  # noqa: ARG002
            message = "synthesis died"
            raise RuntimeError(message)

    voice = _voice(monkeypatch, _FailingTail())
    monkeypatch.setattr(listen, "cleanup_session_after", lambda *_a, **_k: None)
    list(voice.speak("a"))

    assert list(voice.finish()) == []


def test_each_text_piece_gets_its_own_processor_numbered_like_the_piece(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One processor per text piece, keyed the way a 1.0 lesson keys them.

    The element adapter binds audio to the element whose stream number the audio carries. A single
    processor for the whole turn gives every segment the same number, so every page's audio lands
    on one element and the rest are left marked speakable with nothing to play.
    """
    asked: list[dict] = []

    def _factory(_app: object, **kwargs: object) -> object:
        asked.append(kwargs)
        return _Processor()

    monkeypatch.setattr(listen, "create_tts_processor", _factory)
    voice = listen.LessonVoice(
        _App(),
        shifu_model=object,
        shifu_bid="shifu-bid",
        outline_bid="outline-bid",
        progress_record_bid="progress-bid",
        user_bid="user-bid",
        generated_block_bid="block-bid",
    )

    list(voice.speak("first page", stream_type="text", stream_number=0))
    list(voice.speak("still first", stream_type="text", stream_number=0))
    list(voice.speak("<div>card</div>", stream_type="html", stream_number=1))
    list(voice.speak("second page", stream_type="text", stream_number=2))

    assert [(k["stream_element_number"], k["position"]) for k in asked] == [
        (0, 0),
        (2, 1),
    ]
    assert all(k["stream_element_type"] == "text" for k in asked)
    # Usage is recorded by the processor, and a listening lesson billed without this reads as a
    # reading one.
    assert all(k["learning_mode"] == "listen" for k in asked)
    assert asked[0]["generated_block_bid"] == "block-bid"
    assert asked[0]["progress_record_bid"] == "progress-bid"


def test_a_card_is_shown_not_spoken_and_ends_the_passage_before_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reaching a non-text piece finishes the text before it, so its tail is not held back."""
    first = _Processor()
    monkeypatch.setattr(listen, "create_tts_processor", lambda *_a, **_k: first)
    voice = listen.LessonVoice(
        _App(),
        shifu_model=object,
        shifu_bid="shifu-bid",
        outline_bid="outline-bid",
        progress_record_bid="progress-bid",
        user_bid="user-bid",
        generated_block_bid="block-bid",
    )

    list(voice.speak("prose", stream_type="text", stream_number=0))
    events = list(voice.speak("<div>card</div>", stream_type="html", stream_number=1))

    assert first.spoken == ["prose"]
    assert first.finalized is True
    assert "audio:tail" in events

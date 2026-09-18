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

    def finalize(self, *, commit: bool) -> list[str]:
        self.finalized = True
        assert commit is False
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


def test_the_voice_asks_for_the_processor_that_carries_the_slides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without this flag the audio arrives with no AV contract.

    The element adapter has nothing else to rebuild visual boundaries from for a 2.0 turn, so the
    learner would hear the lesson against one unchanging block of text -- a regression that looks
    like nothing at all in the other tests here, since they patch the factory away.
    """
    asked: dict = {}

    def _factory(_app: object, **kwargs: object) -> object:
        asked.update(kwargs)
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

    list(voice.speak("text"))

    assert asked["derive_visuals_from_text"] is True
    # Usage is recorded by the processor, and a listening lesson billed without this reads as a
    # reading one.
    assert asked["learning_mode"] == "listen"
    assert asked["generated_block_bid"] == "block-bid"
    assert asked["progress_record_bid"] == "progress-bid"

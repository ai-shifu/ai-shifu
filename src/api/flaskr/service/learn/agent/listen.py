"""Speak a 2.0 lesson, using the voice the 1.0 lesson already speaks with.

The engine has a listen mode of its own, in which the model decides what to show and what to say.
We do not use it. Measured against 98 real lessons, its verbatim rate for author-marked `===`
content was 64% where ordinary mode reached 99%, and images the author had marked to keep
disappeared. 762 published courses have TTS switched on, so that is not a trade to make for a
smarter segmentation.

Instead the 2.0 engine does what it is good at -- teaching -- and what it says is spoken by the
same pipeline that speaks a 1.0 lesson: text goes in as it is produced, audio segments come out,
and the visual boundaries are read back out of the text afterwards. A learner listening to a 2.0
lesson gets what they get today.

The processor is created lazily, on the first text of a turn, because a turn that says nothing
should not open a synthesis session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.dao import cleanup_session_after
from flaskr.service.learn.lesson_tts import create_tts_processor

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask
    from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO


class LessonVoice:
    """The spoken track of one 2.0 turn.

    Holds the processor for the turn and turns text into audio-segment events. Every method yields
    events to forward to the learner, so a caller reads as: say this, then send what came back.
    """

    def __init__(
        self,
        app: Flask,
        *,
        shifu_model: type,
        shifu_bid: str,
        outline_bid: str,
        progress_record_bid: str,
        user_bid: str,
        generated_block_bid: str,
    ) -> None:
        """Bind what the processor will need, without creating it yet."""
        self._app = app
        self._shifu_model = shifu_model
        self._shifu_bid = shifu_bid
        self._outline_bid = outline_bid
        self._progress_record_bid = progress_record_bid
        self._user_bid = user_bid
        self._generated_block_bid = generated_block_bid
        self._processor: object | None = None
        self._unavailable = False

    def speak(self, text: str) -> Iterator[RunMarkdownFlowDTO]:
        """Send text to be spoken, yielding whatever audio is ready.

        Called as the turn produces text rather than once at the end: a turn is a whole lesson
        segment, and a learner who had to wait for all of it before hearing anything would sit in
        silence for as long as it took to write.
        """
        if not text or self._unavailable:
            return
        processor = self._ensure_processor()
        if processor is None:
            return
        try:
            yield from processor.process_chunk(text)
            # Synthesis runs behind the text, so `process_chunk` can only emit what happens to be
            # ready at the instant it is called. Segments that finish afterwards sit in the
            # processor until something collects them, and a turn that only collected at the end
            # would leave the learner silent through the whole lesson. This is the same pairing a
            # 1.0 lesson uses after every chunk.
            yield from self._drain(processor)
        except Exception as exc:
            self._give_up("speaking this lesson failed", exc)

    def finish(self) -> Iterator[RunMarkdownFlowDTO]:
        """Close the spoken track, yielding the audio still owed.

        The last sentence of a turn is usually mid-synthesis when the text runs out; without this
        the learner would never hear it.
        """
        processor, self._processor = self._processor, None
        if processor is None:
            return
        try:
            yield from processor.finalize(commit=False)
        except Exception as exc:
            self._give_up("finishing the spoken lesson failed", exc)

    @staticmethod
    def _drain(processor: object) -> Iterator[RunMarkdownFlowDTO]:
        """Collect audio that finished since the last chunk.

        Guarded rather than called directly: not every processor the factory returns carries this,
        and a lesson is spoken by whichever one the course's settings produce.
        """
        drain = getattr(processor, "drain_ready_segments", None)
        if drain is None:
            return
        yield from drain()

    def _ensure_processor(self) -> object | None:
        if self._processor is None and not self._unavailable:
            self._processor = create_tts_processor(
                self._app,
                shifu_model=self._shifu_model,
                shifu_bid=self._shifu_bid,
                outline_bid=self._outline_bid,
                progress_record_bid=self._progress_record_bid,
                user_bid=self._user_bid,
                generated_block_bid=self._generated_block_bid,
                learning_mode="listen",
                # The engine's listen mode is off, so its text carries no MarkdownFlow stream
                # parts and the element adapter has no other source of visual boundaries. This
                # processor derives them from the text as it streams and attaches them to its
                # audio events, which is what makes the slides change with the narration.
                derive_visuals_from_text=True,
            )
            if self._processor is None:
                # No TTS configured for this course, or settings that do not validate. Said once,
                # so a silent lesson does not try again on every chunk.
                self._unavailable = True
        return self._processor

    def _give_up(self, what: str, exc: Exception) -> None:
        """Stop speaking this turn, and let the lesson carry on without a voice."""
        self._unavailable = True
        self._processor = None
        self._app.logger.warning("%s: %s", what, exc, exc_info=exc)
        cleanup_session_after(exc, source="agent lesson voice")

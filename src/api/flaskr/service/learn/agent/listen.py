"""Speak a 2.0 lesson, using the voice the 1.0 lesson already speaks with.

The engine has a listen mode of its own, in which the model decides what to show and what to say.
We do not use it. Measured against 98 real lessons, its verbatim rate for author-marked `===`
content was 64% where ordinary mode reached 99%, and images the author had marked to keep
disappeared. 762 published courses have TTS switched on, so that is not a trade to make for a
smarter segmentation.

Instead the 2.0 engine does what it is good at -- teaching -- and what it says is spoken the way a
1.0 lesson is: one synthesis processor per text piece, numbered the way the pieces are, so the
audio for a passage is bound to the element that passage is in. A piece that is not text -- a
card, a code fence, an image -- is shown, not spoken, and ends the passage before it. A learner
listening to a 2.0 lesson gets what they get today.

Processors are created lazily, on the first text of a piece, because a turn that says nothing
should not open a synthesis session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.dao import cleanup_session_after
from flaskr.service.learn.lesson_tts import create_tts_processor
from flaskr.service.learn.stream_tts_finalize import StreamTTSFinalizeDrainer

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask
    from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO


class _FinalizeHost:
    """What the finalize drainer needs from a run: the app, and a cursor it may advance."""

    def __init__(self, app: Flask) -> None:
        self.app = app
        self._element_index_cursor = 0


class LessonVoice:
    """The spoken track of one 2.0 turn.

    Holds the processor for the piece being spoken and turns text into audio-segment events. Every
    method yields events to forward to the learner, so a caller reads as: say this, then send what
    came back.
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
        usage_scene: int | None = None,
    ) -> None:
        """Bind what the processors will need, without creating any yet."""
        self._app = app
        self._shifu_model = shifu_model
        self._shifu_bid = shifu_bid
        self._outline_bid = outline_bid
        self._progress_record_bid = progress_record_bid
        self._user_bid = user_bid
        self._generated_block_bid = generated_block_bid
        # What this lesson's audio is billed and reported as: an author previewing is not a
        # learner taking the course, and counting it as one overstates production usage.
        self._usage_scene = usage_scene
        self._processor: object | None = None
        self._key: tuple[str, int] | None = None
        self._next_position = 0
        self._unavailable = False
        # Finishing a piece waits on the provider for its last sentence. Done in the background,
        # as a 1.0 lesson does it, so the next piece's text is not held up behind it.
        self._finalizer = StreamTTSFinalizeDrainer(
            _FinalizeHost(app), log_prefix="agent lesson voice"
        )

    def speak(
        self, text: str, *, stream_type: str = "text", stream_number: int = 0
    ) -> Iterator[RunMarkdownFlowDTO]:
        """Send one piece of the lesson to be spoken, yielding whatever audio is ready.

        Called as the turn produces text rather than once at the end: a turn is a whole lesson
        segment, and a learner who had to wait for all of it before hearing anything would sit in
        silence for as long as it took to write.

        Only text is spoken. Anything else ends the passage before it, so a card between two
        paragraphs is shown against the audio of the paragraph that introduced it, not the one
        after.
        """
        if not text or self._unavailable:
            return
        try:
            yield from self._switch_to(stream_type, stream_number)
            if self._processor is not None:
                yield from self._processor.process_chunk(text)
            yield from self._collect()
        except Exception as exc:
            self._give_up("speaking this lesson failed", exc)

    def finish(self) -> Iterator[RunMarkdownFlowDTO]:
        """Close the spoken track, yielding the audio still owed.

        The last sentence of a turn is usually mid-synthesis when the text runs out; without this
        the learner would never hear it.
        """
        try:
            self._retire_current()
            yield from self._finalizer.drain(wait=True)
        except Exception as exc:
            self._give_up("finishing the spoken lesson failed", exc)
        finally:
            self._finalizer.close()

    def _switch_to(
        self, stream_type: str, stream_number: int
    ) -> Iterator[RunMarkdownFlowDTO]:
        """Move to the processor for this piece, finishing the previous one.

        The key is the same one a 1.0 lesson switches on: a text piece's number. A non-text piece
        has no processor, so reaching one finishes the passage before it and speaks nothing.
        """
        key = (
            ("text", int(stream_number))
            if (stream_type or "").strip().lower() == "text"
            else None
        )
        if key == self._key:
            return
        self._retire_current()
        self._key = key
        if key is None:
            return
        position = self._next_position
        self._processor = create_tts_processor(
            self._app,
            shifu_model=self._shifu_model,
            shifu_bid=self._shifu_bid,
            outline_bid=self._outline_bid,
            progress_record_bid=self._progress_record_bid,
            user_bid=self._user_bid,
            generated_block_bid=self._generated_block_bid,
            learning_mode="listen",
            position=position,
            stream_element_number=key[1],
            stream_element_type="text",
            usage_scene=self._usage_scene,
        )
        if self._processor is None:
            # No TTS configured for this course, or settings that do not validate. Said once, so
            # a silent lesson does not try again on every piece.
            self._unavailable = True
            return
        self._next_position = position + 1
        yield from self._collect()

    def _retire_current(self) -> None:
        processor, self._processor = self._processor, None
        if processor is not None:
            self._finalizer.submit(processor)

    def _collect(self) -> Iterator[RunMarkdownFlowDTO]:
        """Pick up audio that finished since the last call, from every processor still owed.

        Synthesis runs behind the text, so `process_chunk` can only emit what happens to be ready
        at the instant it is called. Segments that finish afterwards sit in their processor until
        something collects them; a turn that only collected at the end would leave the learner
        silent through the whole lesson. Same pairing as a 1.0 lesson performs after every chunk.
        """
        yield from self._finalizer.drain()
        drain = getattr(self._processor, "drain_ready_segments", None)
        if drain is not None:
            yield from drain()
        yield from self._finalizer.drain()

    def _give_up(self, what: str, exc: Exception) -> None:
        """Stop speaking this turn, and let the lesson carry on without a voice."""
        self._unavailable = True
        self._processor = None
        self._key = None
        self._app.logger.warning("%s: %s", what, exc, exc_info=exc)
        cleanup_session_after(exc, source="agent lesson voice")

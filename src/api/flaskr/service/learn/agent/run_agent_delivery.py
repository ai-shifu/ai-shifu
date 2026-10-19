"""Deliver a 2.0 turn's text and questions the way a 1.0 lesson sends them.

Formatting, speech ordering, and question de-duplication for ``run_agent``.
These helpers hold no session or database state.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from flaskr.service.learn.agent.engine.events import ContentDelta, InteractionRequest
from flaskr.service.learn.agent.legacy_protocol import (
    UnrepresentableInteractionError,
    render_narrated_interaction,
    translate,
)
from flaskr.service.learn.agent.pagination import LessonPager
from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from flask import Flask
    from flaskr.service.learn.agent.echoed_memory import EchoedMemoryFilter
    from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter
    from flaskr.service.learn.agent.listen import LessonVoice
    from flaskr.service.learn.agent.preserve_markers import PreserveMarkerFilter


def _on_this_page(
    events: object,
    *,
    pager: LessonPager,
    voice: LessonVoice | None,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Classify translated lesson text, including a question's prompt, before sending it.

    A prompt can contain visuals too. Flush it before the following controls or block boundary
    so the last buffered line is shown and spoken in the same order as the rest of the lesson.
    """
    for event in events:
        if (
            getattr(event, "type", None) == GeneratedType.CONTENT
            and not event.get_mdflow_stream_parts()
        ):
            text = str(event.content or "")
            if text:
                yield from _pieces(
                    pager.add(text) + pager.flush(),
                    voice=voice,
                    outline_bid=event.outline_bid,
                    generated_block_bid=event.generated_block_bid,
                )
                continue
        yield event


def _paged(
    text: str,
    *,
    pager: LessonPager,
    voice: LessonVoice | None,
    outline_bid: str,
    generated_block_bid: str,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Send one stretch of lesson text in formatted pieces, each spoken after it is shown.

    Text first and then its audio, the order a 1.0 lesson sends them in: the browser treats a
    passage marked speakable with no audio yet as buffering and waits, so audio that arrives ahead
    of the text it belongs to has no element to attach to.
    """
    yield from _pieces(
        pager.add(text),
        voice=voice,
        outline_bid=outline_bid,
        generated_block_bid=generated_block_bid,
    )


# How far back from the end of the narration a question may sit and still count as just asked.
# Long enough for a closing fragment after it, short enough that the same words earlier in the
# lesson are not mistaken for the question now standing in front of the learner.
_ECHO_WINDOW_CHARS = 80


def _condensed(text: str) -> str:
    """Text with each run of whitespace reduced to one space.

    Reduced rather than removed: a space is what separates one word from the next in a written
    language that uses them, and dropping it runs words together, so a match could straddle two
    of them or land inside a third.
    """
    return re.sub(r"\s+", " ", text).strip()


# Scripts that do not put spaces between words: Chinese, Japanese and Korean. A question in one
# of them routinely follows the phrase introducing it with nothing in between, so there is no
# boundary to find, and demanding one would refuse every repetition this was written to catch --
# on exactly the content the duplicate was reported on.
_UNSPACED_SCRIPT = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]"
)


def _joins_a_word(char: str) -> bool:
    """Whether this character would be part of a word written in a space-delimited script."""
    if not char or _UNSPACED_SCRIPT.match(char):
        return False
    return re.match(r"\w", char) is not None


def _stands_alone(asked: str, said: str, start: int) -> bool:
    """Whether `asked` occurs at or after `start` as itself, not buried inside a longer word.

    Matching characters is not the same as matching what was said: a prompt reading `rate` is
    contained in `separate`, and a lesson that had only mentioned separating examples would lose
    the question it meant to ask, leaving the controls with nothing above them.

    The whole of `said` is passed rather than the part being searched, because the character
    before a match is what decides whether it stands alone, and where the search begins mid-word
    that character is still there to be read. Given only the slice, a window opening inside
    `separate` would see nothing to its left and call `rate` a word of its own.
    """
    for match in re.finditer(re.escape(asked), said[start:]):
        at = start + match.start()
        end = at + len(asked)
        before = said[at - 1] if at else ""
        after = said[end] if end < len(said) else ""
        if not _joins_a_word(before) and not _joins_a_word(after):
            return True
    return False


def _already_asked(taught: str, prompt: str) -> bool:
    """Whether the lesson just asked this, in the words it is about to ask it again.

    The model writes the question into the lesson text and then passes it to `interact` as well,
    and both reach the learner: a lesson that had just asked "the first question: can you code?"
    asked "can you code?" again, on its own line above the buttons.

    Two things narrow it, and both exist to protect the question rather than to catch the
    repetition. Only the end of the narration counts, so words used earlier in the turn are not
    mistaken for the question now in front of the learner. And the words must stand on their own,
    so a short prompt is not swallowed by a longer word that happens to contain it.
    """
    asked = _condensed(prompt)
    if not asked:
        return False
    said = _condensed(taught)
    start = max(0, len(said) - (len(asked) + _ECHO_WINDOW_CHARS))
    return _stands_alone(asked, said, start) or _ends_asking(said, asked)


# How much of the narration's closing words a prompt must account for to count as the same
# question, and how long a prompt must be before anything short of an exact repeat is enough. A
# model asking in the narration and again in the prompt drops a few words -- "挑一件你觉得最费时间"
# became "挑一件最费时间" on the general-education course -- while a short prompt resembles too
# many endings to be judged this way at all.
_REWORDED_RATIO = 0.85
_REWORDED_MIN_CHARS = 8
_PUNCTUATION = re.compile(r"[\s\W_]+")
# Where a sentence ends, so a question followed by a short aside is still found.
# Full stop, exclamation and question marks (full-width and ASCII) and an ellipsis, then any
# closing quote or bracket.
_SENTENCE_END = re.compile(
    r"[\u3002\uff01\uff1f!?\u2026]+[\u300d\u300f\u201d\"')\uff09]*"
)


def _ends_asking(said: str, asked: str) -> bool:
    """Whether the narration just asked this question, with at most a few words left out.

    Only words dropped, never changed: every word of the prompt must appear, in order, in the
    stretch of narration it is compared with. A changed word can turn the question around --
    "largest" for "smallest", "最大" for "最小" -- and a prompt dropped as a repeat of a different
    question would leave its controls under the wrong one (review of #2958).

    Compared with the narration's last sentence or two: its very end, or the end of a sentence
    followed by a short aside, within `_ECHO_WINDOW_CHARS`. Never earlier, so a question the lesson
    asked and has since moved on from does not stand in for the one now being put.
    """
    if len(asked) < _REWORDED_MIN_CHARS or not said:
        return False
    window_start = max(0, len(said) - (len(asked) + _ECHO_WINDOW_CHARS))
    ends = {len(said)} | {
        m.end() for m in _SENTENCE_END.finditer(said) if m.end() > window_start
    }
    longest = int(len(asked) / _REWORDED_RATIO) + 1
    for end in ends:
        for length in range(len(asked), min(longest, end) + 1):
            if _only_words_added(asked, said[end - length : end]):
                return True
    return False


def _only_words_added(asked: str, stretch: str) -> bool:
    """Whether `stretch` is `asked` with a few words added and none changed.

    Punctuation and spacing may differ; a model ends the same sentence with a full-width question
    mark in one place and an ASCII one in the other.
    """
    matcher = SequenceMatcher(None, asked, stretch, autojunk=False)
    for tag, a_start, a_end, _b_start, _b_end in matcher.get_opcodes():
        if tag in ("replace", "delete") and _PUNCTUATION.sub("", asked[a_start:a_end]):
            return False
    return matcher.ratio() >= _REWORDED_RATIO


def _question(
    event: InteractionRequest,
    *,
    pager: LessonPager,
    voice: LessonVoice | None,
    outline_bid: str,
    generated_block_bid: str,
    app: Flask,
    user_bid: str,
    taught: str,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Deliver a question as a 1.0 lesson does: its prompt with the text, then its controls."""
    try:
        translated = translate(
            event, outline_bid=outline_bid, generated_block_bid=generated_block_bid
        )
    except UnrepresentableInteractionError:
        # The controls would ask something other than the model did, so they are not sent. The
        # question still is, as text, so the learner has something to answer.
        app.logger.warning(
            "interaction cannot be rendered as MarkdownFlow: user_bid=%s outline_bid=%s",
            user_bid,
            outline_bid,
            exc_info=True,
        )
        prompt = (
            event.spec.prompt if event.spec.prompt and event.spec.prompt.strip() else ""
        )
        translated = (
            [
                RunMarkdownFlowDTO(
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                    type=GeneratedType.CONTENT,
                    content=prompt,
                )
            ]
            if prompt
            else []
        )
    # A question put again after an unusable answer is already on the learner's screen; sending
    # its text again added the same line under it each time.
    # Only prose counts as having asked it aloud. A copy inside an unfinished visual or code
    # block was not spoken and must not suppress the independent question prompt.
    dedup_pager = LessonPager()
    asked_prose = "".join(
        text
        for text, stream_type, _ in dedup_pager.add(taught) + dedup_pager.flush()
        if stream_type == "text"
    )
    prompts = [
        d
        for d in translated
        if d.type == GeneratedType.CONTENT
        and not event.asked_before
        and not _already_asked(asked_prose, str(d.content or ""))
    ]
    controls = [d for d in translated if d.type != GeneratedType.CONTENT]
    # Flush releases a buffered line but keeps the classifier inside unfinished HTML or code.
    # The prompt is a separate block, so it must not inherit the narration's syntax state.
    yield from _pieces(
        pager.start_block(),
        voice=voice,
        outline_bid=outline_bid,
        generated_block_bid=generated_block_bid,
    )
    yield from _on_this_page(prompts, pager=pager, voice=voice)
    if voice is not None:
        yield from voice.finish()
    yield RunMarkdownFlowDTO(
        outline_bid=outline_bid,
        generated_block_bid=generated_block_bid,
        type=GeneratedType.BREAK,
        content="",
    )
    yield from controls


def _narrated_question(
    span: str,
    *,
    voice: LessonVoice | None,
    outline_bid: str,
    generated_block_bid: str,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Send a question the model wrote into its narration as the question it meant to be.

    Its original notation is preserved, with a localized hint added only when a text control
    lacks one. It arrives as the turn's question rather than as a line of prose.

    The engine did not ask, so no answer is pending for it and the learner's reply reaches the
    model as a remark to react to. That is a lesser wrong than a lesson that sprints past a
    question it has just put on the screen.

    Ordered as `_question` orders it: the text before it is already out, so its audio is finished
    and its block closed, and the question is written after both.
    """
    if voice is not None:
        yield from voice.finish()
    yield RunMarkdownFlowDTO(
        outline_bid=outline_bid,
        generated_block_bid=generated_block_bid,
        type=GeneratedType.BREAK,
        content="",
    )
    yield RunMarkdownFlowDTO(
        outline_bid=outline_bid,
        generated_block_bid=generated_block_bid,
        type=GeneratedType.INTERACTION,
        content=render_narrated_interaction(span),
    )


def _without_markers(
    events: Iterable[object],
    markers: PreserveMarkerFilter,
    syntax: InteractionSyntaxFilter,
    echoes: EchoedMemoryFilter,
) -> Generator[object, None, None]:
    """Pass the turn's events through, with the script's verbatim markers taken out of its text.

    A piece that is nothing but markers, or a fragment held back until more text arrives, is not
    passed on at all; the filter releases what it holds at the end of the turn.
    """
    for event in events:
        if not isinstance(event, ContentDelta):
            yield event
            continue
        text = syntax.feed(markers.feed(echoes.feed(event.text)))
        if text or event.prepared_content is not None:
            # Even fully buffered text carries the pre-display commit barrier.
            # A later filter flush must not expose its correction before saving it.
            yield (
                event if text == event.text else event.model_copy(update={"text": text})
            )


def _say(
    text: str,
    *,
    pager: LessonPager,
    voice: LessonVoice | None,
    outline_bid: str,
    generated_block_bid: str,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Send lesson text through the shared formatter in every learning mode."""
    yield from _paged(
        text,
        pager=pager,
        voice=voice,
        outline_bid=outline_bid,
        generated_block_bid=generated_block_bid,
    )


def _pieces(
    pieces: list[tuple[str, str, int]],
    *,
    voice: LessonVoice | None,
    outline_bid: str,
    generated_block_bid: str,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Send formatted pieces the way a 1.0 lesson sends them: each typed and numbered, then spoken."""
    for content, stream_type, number in pieces:
        yield RunMarkdownFlowDTO(
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
            type=GeneratedType.CONTENT,
            content=content,
        ).set_mdflow_stream_parts([(content, stream_type, number)])
        if voice is not None:
            yield from voice.speak(
                content, stream_type=stream_type, stream_number=number
            )

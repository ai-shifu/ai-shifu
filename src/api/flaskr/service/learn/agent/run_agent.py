"""Teach one lesson turn with the 2.0 engine, speaking the events 1.0 already produces.

This is the whole of a turn as the host sees it: pick up where the learner left off, decide what
this turn is a response to, run it, and hand back `RunMarkdownFlowDTO` events. What consumes those
-- persisting elements, TTS, the SSE frames -- is the existing 1.0 machinery, unchanged.

Three orderings here are not stylistic:

* **The session is saved before the turn's last event goes out.** The engine streams as it works,
  so a caller that forwarded a terminal event before the write leaves the learner believing a turn
  succeeded that the next request will not find -- answers, pending questions and the finished flag
  all revert.
* **Memory is staged, not committed, and staged before that save.** `stage_memory` writes through
  the profile writer without committing, and `save_agent_session` owns the transaction, so the two
  land together or not at all. A memory write that survived a failed session save would describe a
  learner who never said it.
* **The engine is given no memory store.** It runs on the bridge's producer thread, which has no
  app context and has no business doing synchronous database work. It emits `MemoryUpdated` and the
  host writes it here instead.

Nothing calls this yet: routing a lesson to it is the next change.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any

from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.learn.agent.engine.engine import (
    ContinueTurn,
    InteractionResponseTurn,
    MessageTurn,
    StartTurn,
)
from flaskr.service.learn.agent.engine.events import (
    ContentDelta,
    InteractionRequest,
    MemoryUpdated,
    TurnDone,
)
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter
from flaskr.service.learn.agent.legacy_protocol import (
    UnrepresentableInteractionError,
    translate,
)
from flaskr.service.learn.agent.lesson_record import (
    active_progress_record,
    apply_outline_progression,
    claim_for_writing,
    mark_lesson_finished,
    record_turn_content,
    retire_unused_block,
    stage_turn_block,
)
from flaskr.service.learn.agent.listen import LessonVoice
from flaskr.service.learn.agent.pagination import LessonPager
from flaskr.service.learn.agent.preserve_markers import PreserveMarkerFilter
from flaskr.service.learn.agent.session_store import (
    StoredSessionUnusable,
    load_agent_session,
    save_agent_session,
)
from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO
from flaskr.service.learn.learn_funcs import resolve_outline_progression
from flaskr.service.learn.memory import (
    MemoryUpdate,
    VariableMemoryUpdate,
    load_memory,
    stage_memory,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
from flaskr.util.uuid import generate_id

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Generator, Iterable

    from flask import Flask
    from flaskr.service.learn.agent.engine.engine import Engine, TurnInput
    from flaskr.service.learn.agent.engine.events import Event
    from flaskr.service.learn.agent.engine.session import Session


def learner_values(user_input: str | dict | None) -> list[str]:
    """Flatten what the browser sent into the values the learner chose or typed.

    Every lesson input arrives as a map, including free text: the study client normalises a plain
    string to `{"input": ["..."]}` before sending it. Values are kept apart rather than joined,
    because a multi-select answer is several of them and the engine matches each against the
    option it came from.
    """
    if isinstance(user_input, str):
        return [user_input] if user_input.strip() else []
    if not isinstance(user_input, dict):
        return []
    values: list[str] = []
    for value in user_input.values():
        if isinstance(value, list):
            values.extend(str(item) for item in value if item is not None)
        elif value is not None:
            values.append(str(value))
    return [value for value in values if value.strip()]


def _open_turn(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    generated_block_bid: str,
    position: int,
) -> str:
    """Settle where this turn's rows belong, before any of them are written.

    Committed here rather than with the turn, because the element rows the stream writes reference
    both of these while the turn is still running: the progress record is what history retrieval
    starts from, and the block is what the element pipeline reads that record off.
    """
    with app_context_scope(app), unit_of_work():
        record = active_progress_record(
            app, user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
        )
        stage_turn_block(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            progress_record_bid=record.progress_record_bid,
            generated_block_bid=generated_block_bid,
            position=position,
        )
        return record.progress_record_bid


def _turn_input(session: Session, values: list[str]) -> TurnInput:
    """Decide what this turn is: a start, an answer, a remark, or simply carrying on.

    A session holding a pending interaction answers it, even with nothing: the engine refuses every
    other turn type while one is pending, so anything else ends the turn with an error and leaves
    the question unasked. An empty answer is not usable, which makes the engine ask it again --
    which is what a learner who pressed send on an empty box should see.

    On the first turn the learner's words join the opening prompt, because that is what the engine
    does with a `MessageTurn` there. Elsewhere, input with nothing pending is a remark to react to.
    """
    # Everything but an interaction answer is prose, so several values become one message the way
    # the 1.0 path joins them.
    text = ",".join(values)
    if not session.started:
        return MessageTurn(text=text) if text else StartTurn()
    if session.pending:
        return InteractionResponseTurn(values=list(values))
    if text:
        return MessageTurn(text=text)
    return ContinueTurn()


def _load_or_start(
    app: Flask,
    engine: Engine,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    script: str,
    preview_mode: bool,
) -> Callable[[], Any]:
    """Build the coroutine factory the bridge runs on its producer thread.

    Reading happens out here because it needs the app context this thread has; the session itself
    is built in there, because everything the engine touches has to be created on the loop that
    will drive it.

    What the course knows about the learner is read on every turn rather than once at the start.
    The engine has no memory store to read it for itself, and a stored session carries only the
    snapshot taken when it was last saved, so an author editing a learner's profile would otherwise
    never reach the lesson already in progress.
    """
    try:
        stored = load_agent_session(
            app, user_bid, outline_bid, preview_mode=preview_mode
        )
    except StoredSessionUnusable:
        # Written by code whose sessions this one cannot read. Starting over loses the
        # conversation, which is the point of comparing versions rather than parsing hopefully.
        stored = None
    user_memory = load_memory(app, user_bid, shifu_bid).as_variables()

    async def make_session() -> Session:
        if stored is not None:
            stored.user_memory = dict(user_memory)
            return stored
        # `listen_mode=False` always. Listening is delivered by the host's spoken track, not by
        # the engine's own listen mode -- which we do not use, and which a session would keep
        # switched on for every later read-mode turn once it had been stored with it.
        session = await engine.new_session(script, user_id=user_bid, listen_mode=False)
        session.user_memory = dict(user_memory)
        return session

    return make_session


def run_agent_lesson(
    app: Flask,
    *,
    engine: Engine,
    script: str,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    user_input: str | dict | None = None,
    listen: bool = False,
    preview_mode: bool = False,
    shifu_model: type | None = None,
    heartbeat_interval: float = 0.5,
    iter_turn: Callable[..., Any] | None = None,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Run one turn of a 2.0 lesson and yield the 1.0 events it produces.

    `iter_turn` is injectable so a test can drive the turn without a thread; the default is the
    bridge, which runs the engine on its own loop and yields events as they arrive.
    """
    from flaskr.service.learn.agent.bridge import iter_turn as bridge_iter_turn

    run_turn_on_thread = iter_turn or bridge_iter_turn
    make_session = _load_or_start(
        app,
        engine,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        script=script,
        preview_mode=preview_mode,
    )
    # One turn is one generated block: TTS audio and element rows hang off this identifier, and a
    # turn is the smallest unit this engine produces that a learner sees as a whole.
    generated_block_bid = uuid.uuid4().hex
    values = learner_values(user_input)
    # Resolved before the turn runs, and remembered: what it identifies is both where this turn's
    # elements will hang and the thing a reset marks, so a turn can tell afterwards whether the
    # lesson it started in is still the one it is finishing.
    # A preview writes no learner progress. The author is the same person as the learner and the
    # lesson identifier is the same, so a progress record, a block or a completion written here
    # would land in that learner's own history -- their preview turns showing up as lessons they
    # took. Their session is still stored, under its own key, so the preview resumes.
    #
    # It still gets an identifier, just an unwritten one -- the same shape the 1.0 run gives a
    # preview, which builds a progress record and never adds it to the session. The spoken track
    # hangs each piece of audio off one, so without it an author previewing a lesson in listening
    # mode heard nothing at all.
    progress_record_bid = (
        generate_id(app)
        if preview_mode
        else _open_turn(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
            position=0,
        )
    )
    session_holder: dict[str, Session] = {}

    def make_events() -> AsyncIterator[Event]:
        async def events() -> AsyncIterator[Event]:
            session = await make_session()
            session_holder["session"] = session
            async for event in engine.run_turn(session, _turn_input(session, values)):
                yield event

        return events()

    voice = (
        LessonVoice(
            app,
            shifu_model=shifu_model,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            progress_record_bid=progress_record_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            usage_scene=BILL_USAGE_SCENE_PREVIEW if preview_mode else None,
        )
        if listen and progress_record_bid
        else None
    )
    # Paging is what listening needs: it is how a page's audio finds the text it belongs to. A
    # reading lesson has no audio to bind and keeps the single-element shape it has today.
    pager = LessonPager() if listen else None
    try:
        yield from _stream_turn(
            app,
            run_turn_on_thread=run_turn_on_thread,
            voice=voice,
            pager=pager,
            make_events=make_events,
            session_holder=session_holder,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            preview_mode=preview_mode,
            progress_record_bid=progress_record_bid,
            generated_block_bid=generated_block_bid,
            heartbeat_interval=heartbeat_interval,
        )
    except BaseException:
        # The turn died before it could record what it taught -- an engine error, or the learner
        # closing the page. The block reserved for it would otherwise stay behind as an empty
        # assistant turn. GeneratorExit is caught too: a disconnect is the common case.
        if not preview_mode:
            _retire_block(app, generated_block_bid=generated_block_bid)
        raise


def _retire_block(app: Flask, *, generated_block_bid: str) -> None:
    try:
        with app_context_scope(app), unit_of_work():
            retire_unused_block(generated_block_bid=generated_block_bid)
    except Exception:
        # Cleanup must not replace the failure that brought us here.
        app.logger.warning(
            "could not retire the unused block %s", generated_block_bid, exc_info=True
        )


def _on_this_page(
    events: object,
    *,
    pager: LessonPager | None,
    voice: LessonVoice | None,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Put any lesson text that reached here unpaged on the page the lesson is on.

    Paged text and unpaged text cannot share a turn. The unpaged kind is assembled into one
    element holding the whole lesson, which then sits beside the paged ones marked speakable,
    never finalised, and retired at the end without telling the browser -- so the learner waits on
    audio for it that will never come. A single unpaged line is enough to do it, and there was
    one: the prompt beside a question.

    Rather than tagging each place that can produce lesson text and relying on the next one to
    remember, everything leaving here is checked.
    """
    for event in events:
        if (
            pager is not None
            and getattr(event, "type", None) == GeneratedType.CONTENT
            and not event.get_mdflow_stream_parts()
        ):
            text = str(event.content or "")
            if text:
                event.set_mdflow_stream_parts([(text, "text", pager.number)])
                yield event
                if voice is not None:
                    # The question beside a set of choices is often the only place the model
                    # asks it; a listener who does not hear it has nothing to answer.
                    yield from voice.speak(
                        text, stream_type="text", stream_number=pager.number
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
    return _stands_alone(asked, said, start)


def _question(
    event: InteractionRequest,
    *,
    pager: LessonPager | None,
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
    prompts = [
        d
        for d in translated
        if d.type == GeneratedType.CONTENT
        and not _already_asked(taught, str(d.content or ""))
    ]
    controls = [d for d in translated if d.type != GeneratedType.CONTENT]
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

    It goes out exactly as the model wrote it. A 1.0 script carries its interactions in this same
    notation and the browser renders it the same way, so nothing is rebuilt; what changes is that
    it arrives as the turn's question rather than as a line of its prose.

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
        content=span,
    )


def _without_markers(
    events: Iterable[object],
    markers: PreserveMarkerFilter,
    syntax: InteractionSyntaxFilter,
) -> Generator[object, None, None]:
    """Pass the turn's events through, with the script's verbatim markers taken out of its text.

    A piece that is nothing but markers, or a fragment held back until more text arrives, is not
    passed on at all; the filter releases what it holds at the end of the turn.
    """
    for event in events:
        if not isinstance(event, ContentDelta):
            yield event
            continue
        text = syntax.feed(markers.feed(event.text))
        if text:
            yield event if text == event.text else ContentDelta(text=text)


def _say(
    text: str,
    *,
    pager: LessonPager | None,
    voice: LessonVoice | None,
    outline_bid: str,
    generated_block_bid: str,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Send lesson text the way this turn sends it: paged when listening, plain otherwise."""
    if pager is not None:
        yield from _paged(
            text,
            pager=pager,
            voice=voice,
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
        )
        return
    yield RunMarkdownFlowDTO(
        outline_bid=outline_bid,
        generated_block_bid=generated_block_bid,
        type=GeneratedType.CONTENT,
        content=text,
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


def _outline_progression(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str,
    preview_mode: bool,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Report what the finished lesson changed in the outline, and write it down.

    A preview changes nothing: the author is looking at a lesson, not taking one, and a preview
    that ticked lessons off would rewrite the author's own progress through their course.

    A failure here is not allowed to take the lesson down with it. The learner has finished it and
    the turn is already saved; losing the outline update costs them a tick in the sidebar, while
    raising would cost them the end of the lesson.

    Nothing is reported that was not written. A reset that lands between the turn's commit and
    this one leaves no live record to complete, and the changes are dropped rather than recorded;
    telling the browser about them anyway would show a completion the database does not hold.
    """
    if preview_mode:
        return
    try:
        updates = resolve_outline_progression(
            app, shifu_bid=shifu_bid, outline_bid=outline_bid, preview_mode=preview_mode
        )
        if not updates:
            return
        applied = apply_outline_progression(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            progress_record_bid=progress_record_bid,
            updates=updates,
        )
    except Exception:
        app.logger.warning(
            "could not advance the outline: user_bid=%s outline_bid=%s",
            user_bid,
            outline_bid,
            exc_info=True,
        )
        return
    if not applied:
        return
    for update in updates:
        yield RunMarkdownFlowDTO(
            outline_bid=update.outline_bid,
            generated_block_bid="",
            type=GeneratedType.OUTLINE_ITEM_UPDATE,
            content=update,
        )


def _stream_turn(
    app: Flask,
    *,
    run_turn_on_thread: Callable[..., Any],
    voice: LessonVoice | None,
    pager: LessonPager | None,
    make_events: Callable[[], Any],
    session_holder: dict[str, Session],
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    preview_mode: bool,
    progress_record_bid: str,
    generated_block_bid: str,
    heartbeat_interval: float,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Stream one turn's events, translating and persisting as they arrive."""
    pending_memory: list[MemoryUpdated] = []
    taught: list[str] = []
    persisted = False
    # The script's verbatim markers come back in the engine's text; they are syntax, not lesson.
    markers = PreserveMarkerFilter()
    # A question the model typed into its narration instead of asking for one. Held aside while
    # the turn runs: what becomes of it depends on whether the model also called the tool.
    syntax = InteractionSyntaxFilter()
    asked = False

    for event in _without_markers(
        run_turn_on_thread(make_events, heartbeat_interval=heartbeat_interval),
        markers,
        syntax,
    ):
        if isinstance(event, ContentDelta):
            taught.append(event.text)
            if pager is not None:
                # A listening lesson is read page by page, and the audio for a page is bound to
                # the element that page's text is in. Sent as one undivided element, only one
                # page's audio survives that binding and every other page is left marked speakable
                # with nothing to play -- which the browser waits on rather than skipping.
                yield from _paged(
                    event.text,
                    pager=pager,
                    voice=voice,
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                )
                continue

        if isinstance(event, MemoryUpdated):
            # Held rather than written now: the turn may still fail, and a memory write that
            # outlived a failed session save would describe a learner who never said it.
            pending_memory.append(event)
            continue

        if not isinstance(event, ContentDelta):
            # Anything that is not lesson text ends the text before it. The formatter holds the
            # last line until it sees its end, and the marker filter a trailing fragment; released
            # only at the end of the turn, the lesson's closing sentence landed after the
            # question's controls, so the last thing in the learner's history was text rather
            # than the question -- and the browser, seeing no question to answer, asked the
            # lesson to continue with nothing.
            tail = syntax.feed(markers.flush()) + syntax.flush()
            if tail:
                taught.append(tail)
                yield from _say(
                    tail,
                    pager=pager,
                    voice=voice,
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                )
            if pager is not None:
                yield from _pieces(
                    pager.flush(),
                    voice=voice,
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                )
        if isinstance(event, InteractionRequest):
            # The question comes after the lesson text as its own block, the way a 1.0 lesson
            # delivers it: the question's own prompt joins the text, then the text's audio is
            # finished and its block finalised, so every row of it is written before the
            # question's controls. History is ordered by the moment of writing, and a history
            # whose last row was not the question read to the browser as a lesson to continue --
            # which it did, with nothing, on every reload.
            asked = True
            yield from _question(
                event,
                pager=pager,
                voice=voice,
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                app=app,
                taught="".join(taught),
                user_bid=user_bid,
            )
            continue

        # Only a `TurnDone` ends a turn. An `ErrorEvent` may not: a blank answer to a pending
        # question emits one and then re-asks the question and ends the turn properly, so treating
        # it as terminal would write the turn twice and stage its block twice.
        if isinstance(event, TurnDone) and voice is not None:
            # Whatever is still mid-synthesis when the text runs out, which is usually the last
            # sentence of the turn.
            yield from voice.finish()

        if isinstance(event, TurnDone) and not persisted:
            session = session_holder.get("session")
            if session is not None:
                persisted = True
                kept = _persist(
                    app,
                    session,
                    memory=pending_memory,
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                    preview_mode=preview_mode,
                    progress_record_bid=progress_record_bid,
                    generated_block_bid=generated_block_bid,
                    taught="".join(taught),
                )
                pending_memory = []
                if session.finished and kept:  # not for a turn a reset discarded
                    # Before the terminal event, because the browser stops reading the stream on
                    # it. These are the only thing that ticks the lesson off in the outline, ends
                    # the chapter it belonged to, and hands the learner on to what is next -- and
                    # the only thing that tells the page the lesson is over, without which it
                    # goes on asking for a continuation that does not exist.
                    yield from _outline_progression(
                        app,
                        user_bid=user_bid,
                        shifu_bid=shifu_bid,
                        outline_bid=outline_bid,
                        progress_record_bid=progress_record_bid,
                        preview_mode=preview_mode,
                    )

        finished = bool(getattr(session_holder.get("session"), "finished", False))
        if isinstance(event, TurnDone) and not asked and not finished and syntax.spans:
            # The model typed a question rather than asking for one. Sent before the event that
            # ends the turn, so it is the last thing written: a turn ending on text is the host's
            # signal to carry on, and carrying on would run the lesson past the question the
            # learner is still reading.
            #
            # Not on a lesson the model has just finished. The engine refuses a turn on a
            # finished session, so the question could never be answered, and the lesson is over
            # in any case -- a question typed on the way out is not one to put to the learner.
            # Only the last span is asked: a turn holds one question, and it is the one the
            # narration ends on.
            yield from _narrated_question(
                syntax.spans[-1],
                voice=voice,
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
            )

        try:
            yield from _on_this_page(
                translate(
                    event,
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                ),
                pager=pager,
                voice=voice,
            )
        except UnrepresentableInteractionError:
            # The controls would ask something other than the model did, so they are not sent. The
            # question still is: `translate` builds it first and loses it with the raise, and a
            # learner shown neither has nothing to answer while the session keeps waiting for one.
            app.logger.warning(
                "interaction cannot be rendered as MarkdownFlow: user_bid=%s outline_bid=%s",
                user_bid,
                outline_bid,
                exc_info=True,
            )
            prompt = getattr(event, "spec", None) and event.spec.prompt
            if prompt and prompt.strip():
                yield from _on_this_page(
                    [
                        RunMarkdownFlowDTO(
                            outline_bid=outline_bid,
                            generated_block_bid=generated_block_bid,
                            type=GeneratedType.CONTENT,
                            content=prompt,
                        )
                    ],
                    pager=pager,
                    voice=voice,
                )

    # A turn can end without a `TurnDone`: the engine emits a bare `ErrorEvent` and returns for
    # the failures it cannot continue past. What the turn produced still has to be written, or the
    # learner replays an exchange that already happened.
    if not persisted:
        # A turn that died has no `TurnDone`, so nothing above will have asked what the model
        # typed. Putting it back as text loses nothing: it is what the model wrote, and the
        # learner is being shown a failure rather than a question either way.
        tail = syntax.feed(markers.flush()) + syntax.flush() + "".join(syntax.spans)
        if tail:
            taught.append(tail)
            yield from _say(
                tail,
                pager=pager,
                voice=voice,
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
            )
    if pager is not None and not persisted:
        yield from _pieces(
            pager.flush(),
            voice=voice,
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
        )
    if voice is not None and not persisted:
        # Speech buffered when the turn died would otherwise never reach the learner, while the
        # synthesis already submitted carries on with nowhere to go.
        yield from voice.finish()
    session = session_holder.get("session")
    if not persisted and session is not None:
        _persist(
            app,
            session,
            memory=pending_memory,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            preview_mode=preview_mode,
            progress_record_bid=progress_record_bid,
            generated_block_bid=generated_block_bid,
            taught="".join(taught),
        )


class _TurnDiscardedError(Exception):
    """The lesson was reset while this turn ran, so nothing it produced may be written."""


def _persist(
    app: Flask,
    session: Session,
    *,
    memory: list[MemoryUpdated],
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    preview_mode: bool,
    progress_record_bid: str,
    generated_block_bid: str,
    taught: str,
) -> bool:
    """Write what the turn produced, memory first so it commits with the session.

    `stage_memory` stages without committing and `save_agent_session` owns the transaction, so the
    two land together. Ordering them the other way would commit the session and leave the memory
    staged for whoever commits next.

    Returns whether the turn was kept. A lesson reset while the turn ran discards it, and the
    caller has to know: the outline changes that follow a finished lesson would otherwise be
    applied on behalf of a turn that wrote nothing, putting back the completion the learner had
    just cleared and carrying them past the lesson they had asked to take again.
    """

    def stage_everything() -> None:
        """Everything this turn writes, inside the session's own transaction.

        The claim comes first and holds a lock until the transaction commits, so a reset either
        happens before it -- and this turn writes nothing -- or after, when it can see the session
        and clear it. Staging anything ahead of that check would leave it in the session for
        whoever commits next, a write from a turn that was meant to be discarded.
        """
        record = None
        if not preview_mode:
            record = claim_for_writing(
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                progress_record_bid=progress_record_bid,
            )
            if record is None:
                raise _TurnDiscardedError

        # Session-scoped facts stay in the session, which `save_agent_session` serializes. Writing
        # them to the profile would leak a turn's working notes into preview, Ask and follow-up
        # prompts, and outlive the session that made sense of them. The `remember` tool defaults to
        # session scope, so this is the common case, not the rare one.
        durable = [update for update in memory if update.scope == "user"]
        if durable:
            stage_memory(
                app,
                user_bid,
                shifu_bid,
                MemoryUpdate(
                    variables=[
                        VariableMemoryUpdate(
                            key=update.key,
                            value="" if update.value is None else str(update.value),
                        )
                        for update in durable
                    ]
                ),
            )
        if record is not None:
            record_turn_content(generated_block_bid=generated_block_bid, content=taught)
            if session.finished:
                mark_lesson_finished(record)

    try:
        save_agent_session(
            app,
            session,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            preview_mode=preview_mode,
            stage=stage_everything,
        )
    except _TurnDiscardedError:
        app.logger.info(
            "discarding a turn whose lesson was reset while it ran: "
            "user_bid=%s outline_bid=%s",
            user_bid,
            outline_bid,
        )
        return False
    return True

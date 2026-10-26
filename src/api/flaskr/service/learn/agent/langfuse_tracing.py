"""Own Langfuse policy and presentation for MarkdownFlow course requests."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Self

from flaskr.api.langfuse_markdownflow import MarkdownFlowTrace
from flaskr.service.learn.learn_dtos import GeneratedType

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator

    from flaskr.api.markdownflow import Event, Session
    from flaskr.service.learn.agent.run_agent import TurnOutcome
    from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO

logger = logging.getLogger(__name__)

TEACHING_SUMMARY_GENERATION_NAME = "agent_teaching_summary"
MEMORY_ADMISSION_GENERATION_NAME = "agent_memory_admission"


def _latest_ancestor(model: type, *, outline_bid: str, shifu_bid: str) -> object:
    return (
        model.query.filter_by(
            deleted=0, outline_item_bid=outline_bid, shifu_bid=shifu_bid
        )
        .order_by(model.id.desc())
        .first()
    )


def _lesson_context(
    outline_model: type, *, outline: object, shifu: object
) -> dict[str, object]:
    """Read names from the same draft or published records used for execution."""
    ancestors: list[str] = []
    seen = {outline.outline_item_bid}
    parent_bid = (getattr(outline, "parent_bid", "") or "").strip()
    for _ in range(12):
        if not parent_bid or parent_bid in seen:
            break
        seen.add(parent_bid)
        parent = _latest_ancestor(
            outline_model, outline_bid=parent_bid, shifu_bid=outline.shifu_bid
        )
        if parent is None:
            break
        ancestors.append((parent.title or "").strip() or parent.outline_item_bid)
        parent_bid = (getattr(parent, "parent_bid", "") or "").strip()
    return {
        "course_title": (shifu.title or "").strip() or shifu.shifu_bid,
        "lesson_title": (outline.title or "").strip() or outline.outline_item_bid,
        "chapter_path": list(reversed(ancestors)),
        "chapter_path_truncated": bool(parent_bid and parent_bid not in seen),
        "course_record_id": shifu.id,
        "outline_record_id": outline.id,
    }


def _lesson_name(
    scene: str,
    course: str,
    chapters: list[str],
    lesson: str,
    *,
    truncated: bool = False,
) -> str:
    """Preserve both title identities within the SDK's propagation limit."""
    scene, course, lesson = (
        " ".join(value.split()) for value in (scene, course, lesson)
    )
    chapter_parts = ["...", *chapters] if truncated else chapters
    chapter_path = "/".join(" ".join(value.split()) for value in chapter_parts)
    parts = [scene, course, *([chapter_path] if chapter_path else []), lesson]
    name = "/".join(parts)
    if len(name) <= 180:
        return name
    available = 180 - len(scene) - (3 if chapter_path else 2)
    course_budget = min(len(course), 64)
    lesson_budget = min(len(lesson), 80)
    chapter_budget = min(len(chapter_path), available - course_budget - lesson_budget)
    remaining = available - course_budget - lesson_budget - chapter_budget
    extra_course = min(len(course) - course_budget, remaining)
    course_budget += extra_course
    lesson_budget += min(len(lesson) - lesson_budget, remaining - extra_course)

    def shorten(value: str, budget: int) -> str:
        if len(value) <= budget:
            return value
        prefix = (budget - 3 + 1) // 2
        suffix = budget - 3 - prefix
        return value[:prefix] + "..." + (value[-suffix:] if suffix else "")

    return "/".join(
        [
            scene,
            shorten(course, course_budget),
            *([shorten(chapter_path, chapter_budget)] if chapter_path else []),
            shorten(lesson, lesson_budget),
        ]
    )


def _request_input(
    user_input: str | dict | None, *, regenerate: bool, started: bool = True
) -> object:
    from flaskr.service.learn.agent.run_agent import learner_values

    return (
        user_input
        if learner_values(user_input)
        else {
            "action": "regenerate" if regenerate else "continue" if started else "start"
        }
    )


class CourseTrace(MarkdownFlowTrace):
    """Keep course observability outside lesson resolution, billing and execution."""

    def __init__(
        self,
        *,
        user_bid: str,
        shifu_bid: str,
        outline_bid: str,
        user_input: str | dict | None,
        preview_mode: bool,
        debug: bool,
        listen: bool,
        learning_mode: str | None,
        regenerate: bool,
    ) -> None:
        """Collect request facts, opening a trace only after lesson access succeeds."""
        self._user_bid = user_bid
        self._shifu_bid = shifu_bid
        self._outline_bid = outline_bid
        self._request_input = _request_input(user_input, regenerate=regenerate)
        self._scene = "debug" if debug else "preview" if preview_mode else "learn"
        self._mode = (
            learning_mode
            if learning_mode in {"read", "listen", "classroom"}
            else "listen"
            if listen
            else "read"
        )
        self._titles: dict[str, object] = {}
        self._content_revision: int | None = None
        self._first_turn = True
        self._initialized = False

    def resolved(
        self,
        *,
        outline_model: type,
        outline: object,
        shifu: object,
        content_revision: int | None,
    ) -> None:
        """Collect names from the already-authorized physical lesson and course rows."""
        self._content_revision = content_revision
        try:
            self._titles = _lesson_context(outline_model, outline=outline, shifu=shifu)
        except Exception:
            logger.warning("Could not resolve MarkdownFlow trace titles")

    def __enter__(self) -> Self:
        """Start the root after the host has resolved and authorized its lesson."""
        if not self._initialized:
            super().__init__(
                name=_lesson_name(
                    self._scene,
                    str(self._titles.get("course_title") or self._shifu_bid),
                    self._titles.get("chapter_path") or [],
                    str(self._titles.get("lesson_title") or self._outline_bid),
                    truncated=bool(self._titles.get("chapter_path_truncated")),
                ),
                user_id=self._user_bid,
                input=self._request_input,
                metadata={
                    "shifu_bid": self._shifu_bid,
                    "outline_item_bid": self._outline_bid,
                    "scene": self._scene,
                    "learning_mode": self._mode,
                    "content_revision": self._content_revision,
                    **self._titles,
                },
            )
            self._initialized = True
        return super().__enter__()

    def prepare_turn(
        self,
        *,
        user_input: str | dict | None,
        regenerate: bool,
        teaching_brief: str,
        content_revision: int | None,
    ) -> Callable[[Session], None]:
        """Open the turn and return its native-session context binding callback."""
        first, self._first_turn = self._first_turn, False
        self.start_turn(
            metadata={"outline_item_bid": self._outline_bid},
            input=_request_input(user_input, regenerate=regenerate),
        )

        def loaded(session: Session) -> None:
            self.set_context(
                session_id=getattr(session, "id", ""),
                script=session.script.script,
                teaching_brief=teaching_brief,
                metadata={
                    "native_turn": session.turn,
                    "content_revision": content_revision,
                },
            )
            turn_input = _request_input(
                user_input, regenerate=regenerate, started=session.started
            )
            self.current.update(input=turn_input)
            if first:
                self.set_input(turn_input)

        return loaded

    def bind_execution(
        self, progress_record_bid: str, generated_block_bid: str
    ) -> None:
        """Associate the current turn with its host-owned attempt and block."""
        self.current.update(
            metadata={
                "progress_record_bid": progress_record_bid,
                "generated_block_bid": generated_block_bid,
            }
        )

    def after_save(
        self,
        *,
        session: Session | None = None,
        reason: str | None = None,
        finished: bool = False,
        discarded: bool = False,
    ) -> None:
        """Record authoritative saved state before publishing any resulting events."""
        if session is not None:
            finished = bool(session.finished)
            if reason is None:
                reason = "interaction" if session.pending else "end"
        self.mark_outcome(
            "discarded"
            if discarded
            else "completed"
            if finished
            else "waiting"
            if reason == "interaction"
            else "end"
            if reason is not None
            else "error"
        )

    def observe(self, events: Iterator[Event]) -> Iterator[Event]:
        """Forward native events while keeping their diagnostics in Langfuse."""
        try:
            for event in events:
                self.event(event)
                yield event
        finally:
            close = getattr(events, "close", None)
            if close is not None:
                close()

    def capture(
        self, events: Generator[RunMarkdownFlowDTO, None, TurnOutcome | None]
    ) -> Generator[RunMarkdownFlowDTO, None, TurnOutcome | None]:
        """Collect public lesson content and preserve the runner's result and cleanup."""
        iterator = iter(events)
        try:
            while True:
                try:
                    event = next(iterator)
                except StopIteration as stopped:
                    self.complete_turn(self._outcome)
                    return stopped.value
                if event.type in {
                    GeneratedType.CONTENT,
                    GeneratedType.INTERACTION,
                } and isinstance(event.content, str):
                    self.append_output(event.content)
                yield event
        finally:
            close = getattr(iterator, "close", None)
            if close is not None:
                close()

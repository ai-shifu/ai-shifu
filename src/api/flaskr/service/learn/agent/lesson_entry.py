"""Build what a 2.0 turn needs from a lesson request, and hand back 1.0's events.

`run_agent_lesson` takes an engine and a script; this is where those come from. It reads the
lesson the learner is on, resolves the model the same way the 1.0 run does, opens the Langfuse
trace the gateway requires, and closes it however the turn ends.

This is the seam the lesson stream routes through, so it is deliberately thin: everything that
decides what a turn means lives in `run_agent`, and everything that happens to its events lives in
the 1.0 element pipeline, unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.api.llm.model_selection import selection_metadata, selection_model
from flaskr.dao.uow import app_context_scope
from flaskr.service.common.models import raise_error
from flaskr.service.learn.agent.engine.engine import Engine
from flaskr.service.learn.agent.gateway_model import GatewayModel
from flaskr.service.learn.agent.legacy_protocol import unrenderable_reason
from flaskr.service.learn.agent.rewind import RewindUnavailableError, plan_rewind
from flaskr.service.learn.agent.run_agent import learner_values, run_agent_lesson
from flaskr.service.learn.exceptions import PaidError
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import UNIT_TYPE_VALUE_NORMAL
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from flask import Flask
    from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO


class LessonNotTeachable(Exception):  # noqa: N818 - an outcome, not a failure
    """A lesson with nothing for the 2.0 engine to teach.

    Raised rather than streamed as an empty turn so the caller can fall back to 1.0, which is what
    an allowlisted course with an empty or missing outline should get.
    """


# How far up the outline a brief is looked for. Deeper than any course structure in use, and
# short enough that malformed data costs a few queries rather than a lesson.
_ANCESTOR_LIMIT = 12


def _models(preview_mode: bool) -> tuple[type, type]:
    """Pick the draft or published tables, the way the 1.0 run context does."""
    if preview_mode:
        return DraftOutlineItem, DraftShifu
    return PublishedOutlineItem, PublishedShifu


def _latest(model: type, **filters: object) -> object | None:
    """Return the newest undeleted row: these tables keep every version of a row."""
    query = model.query.filter_by(deleted=0, **filters)
    return query.order_by(model.id.desc()).first()


def _resolve(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    preview_mode: bool,
) -> tuple[str, str, LLMSettings]:
    """Read the script, the author's teaching brief, and the model settings for this lesson.

    Model resolution follows 1.0: use the course selection with runtime fallback.
    """
    outline_model, shifu_model = _models(preview_mode)
    # Bound to the course as well as the lesson: an allowlisted course paired with another
    # course's outline would otherwise teach that course's script under this course's settings.
    outline = _latest(outline_model, outline_item_bid=outline_bid, shifu_bid=shifu_bid)
    if outline is None or not (outline.content or "").strip():
        message = f"outline {outline_bid!r} has no script in course {shifu_bid!r}"
        raise LessonNotTeachable(message)

    shifu = _latest(shifu_model, shifu_bid=shifu_bid)
    _require_access(
        app, user_bid=user_bid, shifu=shifu, outline=outline, preview_mode=preview_mode
    )

    course_model = selection_model(shifu)
    brief = _teaching_brief(outline_model, outline=outline, shifu=shifu)
    return (
        outline.content,
        brief,
        LLMSettings(
            model=course_model,
            temperature=shifu.llm_temperature,
            usage_metadata=selection_metadata(shifu),
        ),
    )


def _teaching_brief(outline_model: type, *, outline: object, shifu: object) -> str:
    """Return the author's teaching brief for this lesson, or an empty string.

    A brief says who is being taught, in what voice, with what emphasis: the audience is
    final-year students, the voice is a reviewer's, keep it brief and do not explain the
    method. It is not the lesson; the script is. A 1.0 lesson has always been
    taught with one, and a course moved onto 2.0 without it is taught in a different voice than
    its author wrote for.

    Nearest wins, and only one: the lesson's own, else the nearest ancestor that has one, else
    the course's. That is what 1.0 does -- it returns the first it finds rather than joining
    them -- and matching it is the point. Two engines composing an author's briefs differently
    would teach the same course differently, which is the thing this whole step is avoiding.
    """
    own = (getattr(outline, "llm_system_prompt", "") or "").strip()
    if own:
        return own
    # Up the outline: a chapter's brief covers the lessons inside it. Bounded by the walk always
    # moving to a parent, and by a limit besides, so a cycle in the data cannot hang a lesson.
    seen = {outline.outline_item_bid}
    parent_bid = (getattr(outline, "parent_bid", "") or "").strip()
    for _ in range(_ANCESTOR_LIMIT):
        if not parent_bid or parent_bid in seen:
            break
        seen.add(parent_bid)
        parent = _latest(
            outline_model, outline_item_bid=parent_bid, shifu_bid=outline.shifu_bid
        )
        if parent is None:
            break
        brief = (getattr(parent, "llm_system_prompt", "") or "").strip()
        if brief:
            return brief
        parent_bid = (getattr(parent, "parent_bid", "") or "").strip()
    return (getattr(shifu, "llm_system_prompt", "") or "").strip()


def _has_bought(*, user_bid: str, shifu_bid: str) -> bool:
    """Whether this learner holds a successful order for this course."""
    return (
        Order.query.filter(
            Order.user_bid == user_bid,
            Order.shifu_bid == shifu_bid,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.deleted == 0,
        )
        .order_by(Order.id.desc())
        .first()
        is not None
    )


def _require_access(
    app: Flask,
    *,
    user_bid: str,
    shifu: object | None,
    outline: object,
    preview_mode: bool,
) -> None:
    """Refuse a paid lesson the learner has not bought.

    The 1.0 path gates this inside its run context, which the agent path does not build, so the
    same rule is applied here. Without it, putting a paid course on the allowlist would hand its
    content to anyone signed in.

    Only full lessons are gated: a trial lesson is meant to be readable before buying, which is
    what it is for.
    """
    if preview_mode or shifu is None:
        return
    if getattr(outline, "type", None) != UNIT_TYPE_VALUE_NORMAL:
        return
    if (shifu.price or 0) <= 0:
        return
    if not _has_bought(user_bid=user_bid, shifu_bid=shifu.shifu_bid):
        app.logger.info(
            "refusing an unpaid agent lesson: user_bid=%s shifu_bid=%s",
            user_bid,
            shifu.shifu_bid,
        )
        raise PaidError


def agent_lesson_events(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    user_input: str | dict | None = None,
    listen: bool = False,
    preview_mode: bool = False,
    heartbeat_interval: float = 0.5,
    reload_generated_block_bid: str | None = None,
    reload_element_bid: str | None = None,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Teach an allowlisted lesson until it waits or ends, yielding the events 1.0 produces.

    One request, as many turns as it takes: a turn that ends with content still to come is
    followed by the next in the same stream, the way a 1.0 request runs block after block until a
    question or the end of the lesson. A lesson that will not end is stopped by the engine's own
    limit on turns per lesson, which ends it as finished; a cap here would instead close the
    stream mid-lesson, which the browser cannot tell from a finished request.

    `listen` reaches the spoken track, not the engine: the engine's own listen mode stays off, and
    what it teaches is spoken by the pipeline that speaks a 1.0 lesson. See `agent/listen.py`.

    The reload identifiers take the lesson back to an earlier turn first, as a 1.0 reload does
    (see `agent.rewind`). A lesson that cannot be taken back says so rather than going to 1.0.
    """
    rewind = None
    anchor = reload_element_bid or reload_generated_block_bid
    if anchor:
        # Preview keeps no turn blocks to go back to.
        if preview_mode:
            raise_error("server.learn.agentRewindUnavailable")
        try:
            with app_context_scope(app):
                rewind = plan_rewind(
                    user_bid=user_bid,
                    outline_bid=outline_bid,
                    anchor=anchor,
                    answering=bool(learner_values(user_input)),
                )
        except RewindUnavailableError:
            raise_error("server.learn.agentRewindUnavailable")
    script, brief, settings = _resolve(
        app,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        preview_mode=preview_mode,
    )

    trace, span = create_trace_with_root_span(
        client=get_langfuse_client(),
        trace_payload={
            "name": "agent_lesson",
            "user_id": user_bid,
            "metadata": {
                "shifu_bid": shifu_bid,
                "outline_item_bid": outline_bid,
                "flow_engine": "2.0",
            },
        },
        root_span_payload={"name": "agent_lesson_turn"},
    )
    engine = Engine(
        GatewayModel(
            app,
            settings.model,
            user_id=user_bid,
            span=span,
            usage_metadata=settings.usage_metadata,
            # An author previewing is not a learner taking the course; counting their turns as
            # production overstates what the course actually cost to teach.
            **({"usage_scene": BILL_USAGE_SCENE_PREVIEW} if preview_mode else {}),
        ),
        # No memory store: the engine runs on the bridge's producer thread, which has no app
        # context. The host consumes its `MemoryUpdated` events and writes them instead.
        memory_store=None,
        model_settings={"temperature": settings.temperature},
        # A question this host cannot render goes back to the model to be asked again. Let
        # through, it reached the learner as text with no controls under it, the lesson waited
        # for an answer that could not be given, and each return to the lesson asked it again.
        interaction_check=unrenderable_reason,
        # Every lesson here is written in MarkdownFlow, and a MarkdownFlow lesson pauses only where
        # its author put a button. Left to decide, the model added pauses the author never wrote:
        # 17 "继续" buttons over 4 lessons of the general-education course (2026-09-24), 6 of
        # them in a lesson whose script has no question at all.
        pauses_from_notation=True,
    )
    end_reason = "error"
    try:
        while True:
            outcome = yield from run_agent_lesson(
                app,
                engine=engine,
                script=script,
                teaching_brief=brief,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                user_input=user_input,
                listen=listen,
                preview_mode=preview_mode,
                shifu_model=_models(preview_mode)[1],
                heartbeat_interval=heartbeat_interval,
                rewind=rewind,
            )
            # A turn that ran out of content with the lesson not over is followed by the next,
            # as the host's own "continue": the learner's input and the rewind belonged to the
            # first turn only. The browser is not asked to do this. It never sees the boundary
            # -- a turn's end that is not the lesson's is kept off the stream -- so a lesson
            # left there stayed "in progress" until the learner came back to it, and only then
            # went on. A turn that ended the same way having said nothing is not followed: the
            # model has nothing to add and did not say so, and asking again would only loop.
            if outcome is None or outcome.reason != "end" or not outcome.taught:
                break
            user_input, rewind = None, None
        end_reason = "completed"
    except RewindUnavailableError:
        # The session the rows point back into is gone (unreadable, or never stored).
        raise_error("server.learn.agentRewindUnavailable")
    except GeneratorExit:
        # The learner closed the page mid-turn. Still an ending, and one worth telling apart from
        # a failure when reading traces later.
        end_reason = "disconnected"
        raise
    finally:
        # However the turn ended, an unfinished trace leaves its cost and latency unattributed.
        finalize_langfuse_trace(
            trace=trace,
            root_span=span,
            root_span_payload={"metadata": {"end_reason": end_reason}},
        )

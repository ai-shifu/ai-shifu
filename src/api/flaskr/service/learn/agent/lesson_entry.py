"""Build what a 2.0 turn needs from a lesson request, and hand back 1.0's events.

`run_agent_lesson` takes an engine and a script; this is where those come from. It reads the
lesson the learner is on, resolves the model the same way the 1.0 run does, opens the Langfuse
trace the gateway requires, and closes it however the turn ends.

This is the seam the lesson stream routes through, so it is deliberately thin: everything that
decides what a turn means lives in `run_agent`, and everything that happens to its events lives in
the 1.0 element pipeline, unchanged.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from flaskr.api.llm.model_selection import selection_metadata, selection_model
from flaskr.api.markdownflow import Engine, GatewayModel
from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common.models import AppError, raise_error
from flaskr.service.learn.agent.langfuse_tracing import (
    MEMORY_ADMISSION_GENERATION_NAME,
    TEACHING_GENERATION_NAME,
    CourseTrace,
)
from flaskr.service.learn.agent.legacy_protocol import unrenderable_reason
from flaskr.service.learn.agent.lesson_source import (
    resolve_lesson_source,
    resolve_requested_lesson_source,
)
from flaskr.service.learn.agent.memory_admission import make_request_check
from flaskr.service.learn.agent.rewind import RewindUnavailableError, plan_rewind
from flaskr.service.learn.agent.run_agent import learner_values, run_agent_lesson
from flaskr.service.learn.agent.session_store import stage_lesson_attempt_source
from flaskr.service.learn.exceptions import PaidError
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.memory.api import COURSE_REFERENCE_PREFIX, SHARED_ANSWER_PREFIX
from flaskr.service.metering.api import UsageContext
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.order.consts import LEARN_STATUS_COMPLETED, ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.profile.api import get_global_profile_keys
from flaskr.service.shifu.consts import UNIT_TYPE_VALUE_NORMAL
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from flask import Flask
    from flaskr.service.learn.agent.debug_session import DebugSessionStore
    from flaskr.service.learn.agent.lesson_source import ResolvedLessonSource
    from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO


class DiscardedTurnError(AppError):
    """A turn whose save a concurrent reset or rewind rejected; nothing it showed may be kept.

    The stream ends it quietly: the learner asked for the replacement, so the old turn just
    stops, without an error and without anything of it written.
    """


class LessonNotTeachable(Exception):  # noqa: N818 - an outcome, not a failure
    """A lesson with nothing for the 2.0 engine to teach.

    Raised rather than streamed as an empty turn so the caller can complete the lesson instead
    (`complete_empty_lesson`).
    """


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
    require_script: bool = True,
    on_resolved: Callable[..., None] | None = None,
    lesson_version: ResolvedLessonSource | None = None,
) -> tuple[str, str, LLMSettings, int | None, bool]:
    """Read the script, the author's teaching brief, and the model settings for this lesson.

    Model resolution follows 1.0: use the course selection with runtime fallback.
    """
    outline_model, shifu_model = _models(preview_mode)
    if lesson_version is None:
        outline = _latest(
            outline_model, outline_item_bid=outline_bid, shifu_bid=shifu_bid
        )
        shifu = _latest(shifu_model, shifu_bid=shifu_bid)
        from flaskr.service.learn.learn_funcs import get_current_lesson_outline

        current = get_current_lesson_outline(
            shifu_bid=shifu_bid, outline_bid=outline_bid, preview_mode=preview_mode
        )
        content_revision = (
            current.content_revision
            if current and outline and current.id == outline.id
            else None
        )
        _require_access(
            app,
            user_bid=user_bid,
            shifu=shifu,
            outline=outline,
            preview_mode=preview_mode,
        )
    else:
        outline, shifu = lesson_version.outline, lesson_version.course
        outline_model = type(outline)
        content_revision = lesson_version.source.content_revision
    if outline is None or (require_script and not (outline.content or "").strip()):
        message = f"outline {outline_bid!r} has no script in course {shifu_bid!r}"
        raise LessonNotTeachable(message)

    course_model = selection_model(shifu)
    brief = _teaching_brief(shifu)
    if on_resolved is not None:
        on_resolved(
            outline_model=outline_model,
            outline=outline,
            shifu=shifu,
            content_revision=content_revision,
        )
    return (
        outline.content or "",
        brief,
        LLMSettings(
            model=course_model,
            temperature=shifu.llm_temperature,
            usage_metadata=selection_metadata(shifu),
        ),
        content_revision,
        bool(getattr(shifu, "use_learner_language", 0)),
    )


def complete_empty_lesson(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    preview_mode: bool,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Complete a lesson that has no script, handing the learner on to the next one.

    Access is checked before marking the shared progress complete.
    """
    from flaskr.service.learn.agent.lesson_record import (
        active_progress_record,
        claim_for_writing,
        mark_lesson_finished,
    )
    from flaskr.service.learn.agent.run_agent import _outline_progression

    with app_context_scope(app):
        lesson_version = resolve_lesson_source(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            preview_mode=preview_mode,
        )
        require_requested_lesson_access(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            preview_mode=preview_mode,
        )
        if (lesson_version.outline.content or "").strip():
            # The selected version can change between detecting no script and completing it.
            return
        with unit_of_work():
            progress_record_bid = lesson_version.progress_record_bid
            if not progress_record_bid:
                progress = active_progress_record(
                    app, user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
                )
                progress_record_bid = progress.progress_record_bid
                db.session.flush()
            record = claim_for_writing(
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                progress_record_bid=progress_record_bid,
            )
            if record is None or not stage_lesson_attempt_source(
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                source=lesson_version.source,
                complete_without_script=record.status != LEARN_STATUS_COMPLETED,
            ):
                with unit_of_work(discard=True):
                    return
            already_completed = record.status == LEARN_STATUS_COMPLETED
            if not already_completed:
                mark_lesson_finished(record)
    if already_completed:
        # Reopened after it was completed: its outline updates and next-lesson button are
        # already recorded and come back through history, as with any finished lesson.
        return
    yield from _outline_progression(
        app,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        progress_record_bid=progress_record_bid,
        preview_mode=preview_mode,
    )


def _teaching_brief(shifu: object) -> str:
    """Return the course's teaching instructions for every lesson."""
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
    same rule is applied here. Without it, enabling 2.0 for a paid course would hand its
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


def require_requested_lesson_access(
    app: Flask, *, user_bid: str, shifu_bid: str, outline_bid: str, preview_mode: bool
) -> None:
    """Check the entry's purchase requirements independently of the attempt's source."""
    requested = resolve_requested_lesson_source(
        shifu_bid=shifu_bid, outline_bid=outline_bid, preview_mode=preview_mode
    )
    _require_access(
        app,
        user_bid=user_bid,
        shifu=requested.course,
        outline=requested.outline,
        preview_mode=preview_mode,
    )


def _resolve_ordinary_lesson(
    app: Flask, *, user_bid: str, shifu_bid: str, outline_bid: str, preview_mode: bool
) -> ResolvedLessonSource:
    """Admit the selected entry before resolving the active learning attempt."""
    scope = {"user_bid": user_bid, "shifu_bid": shifu_bid, "outline_bid": outline_bid}
    with app_context_scope(app):
        require_requested_lesson_access(app, **scope, preview_mode=preview_mode)
        return resolve_lesson_source(app, **scope, preview_mode=preview_mode)


def agent_lesson_events(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    user_input: str | dict | None = None,
    listen: bool = False,
    learning_mode: str | None = None,
    preview_mode: bool = False,
    heartbeat_interval: float = 0.5,
    reload_generated_block_bid: str | None = None,
    reload_element_bid: str | None = None,
    script_override: str | None = None,
    debug_store: DebugSessionStore | None = None,
    preview_variables: dict[str, object] | None = None,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Teach a lesson selected for 2.0 until it waits or ends, yielding the events 1.0 produces.

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
    lesson_version = (
        _resolve_ordinary_lesson(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            preview_mode=preview_mode,
        )
        if debug_store is None
        else None
    )
    rewind = None
    anchor = reload_element_bid or reload_generated_block_bid
    if anchor:
        try:
            with app_context_scope(app):
                if debug_store is not None:
                    if script_override is None:
                        raise_error("server.learn.agentRewindUnavailable")
                    rewind = debug_store.plan_rewind(
                        script=script_override,
                        block_bid=reload_generated_block_bid or anchor,
                        answering=bool(learner_values(user_input)),
                        element_bid=reload_element_bid,
                    )
                else:
                    rewind = plan_rewind(
                        user_bid=user_bid,
                        outline_bid=outline_bid,
                        anchor=anchor,
                        answering=bool(learner_values(user_input)),
                        **(
                            {}
                            if lesson_version is None
                            else {
                                "shifu_bid": shifu_bid,
                                "progress_record_bid": lesson_version.progress_record_bid,
                            }
                        ),
                    )
        except RewindUnavailableError:
            raise_error("server.learn.agentRewindUnavailable")
    tracing = CourseTrace(
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_input=user_input,
        preview_mode=preview_mode,
        debug=debug_store is not None,
        listen=listen,
        learning_mode=learning_mode,
        regenerate=rewind is not None,
    )
    script, brief, settings, content_revision, use_learner_language = _resolve(
        app,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        preview_mode=preview_mode,
        require_script=debug_store is None,
        on_resolved=tracing.resolved,
        lesson_version=lesson_version,
    )
    if debug_store is not None:
        if not preview_mode or script_override is None:
            msg = "editor debug requires a draft script and preview mode"
            raise ValueError(msg)
        script = script_override

    usage_scene = BILL_USAGE_SCENE_PREVIEW if preview_mode else BILL_USAGE_SCENE_PROD
    # Auxiliary requests belong to the same lesson as teaching. Without the course identity,
    # the shared settlement path cannot find the course owner or report its lesson costs.
    usage_context = UsageContext(
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        usage_scene=usage_scene,
        learning_mode=(
            learning_mode
            if learning_mode in {"read", "listen", "classroom"}
            else "listen"
            if listen
            else "read"
        ),
    )
    models: list[GatewayModel] = []

    def gateway(**kwargs: object) -> GatewayModel:
        model = GatewayModel(
            app,
            settings.model,
            user_id=user_bid,
            span=tracing.model_parent,
            usage_context=usage_context,
            usage_metadata=settings.usage_metadata,
            # An author previewing is not a learner taking the course; counting their turns as
            # production overstates what the course actually cost to teach.
            usage_scene=usage_scene,
            **kwargs,
        )
        models.append(model)
        return model

    def bind_turn_usage(progress_record_bid: str, generated_block_bid: str) -> None:
        nonlocal lesson_version
        if lesson_version is not None and lesson_version.progress_record_bid is None:
            lesson_version = replace(
                lesson_version, progress_record_bid=progress_record_bid
            )
        # The host has opened the actual attempt and block, but its native producer
        # has not started. Rebind all auxiliary models on automatic continuation too.
        context = replace(
            usage_context,
            progress_record_bid=progress_record_bid,
            generated_block_bid=generated_block_bid,
        )
        for model in models:
            model.set_usage_context(context)

    with tracing:
        try:
            system_keys = get_global_profile_keys()
            engine = Engine(
                gateway(generation_name=TEACHING_GENERATION_NAME),
                # No memory store: the engine runs on the bridge's producer thread, which has no app
                # context. The host consumes its `MemoryUpdated` events and writes them instead.
                memory_store=None,
                memory_admission=True,
                memory_context_limit=32_768,
                memory_recall=True,
                # Off: recall results are small, and rewriting them every turn marks their keys
                # stale, which changes the instructions and defeats the provider prefix cache.
                recall_history_compaction=False,
                exercise_statistics=True,
                feedback_contract=True,
                memory_reserved_keys=system_keys,
                # Retained lessons can have active system bindings. The engine
                # allows these only on a matching authored control.
                allowed_authored_question_keys=system_keys,
                memory_readonly_prefixes=(
                    COURSE_REFERENCE_PREFIX,
                    SHARED_ANSWER_PREFIX,
                ),
                memory_request_check=make_request_check(
                    gateway(
                        generation_name=MEMORY_ADMISSION_GENERATION_NAME,
                    )
                ),
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
            while True:
                debug_options = (
                    {"debug_store": debug_store, "preview_variables": preview_variables}
                    if debug_store is not None
                    else {}
                )
                outcome = yield from tracing.capture(
                    run_agent_lesson(
                        app,
                        engine=engine,
                        script=script,
                        teaching_brief=brief,
                        content_revision=content_revision,
                        use_learner_language=use_learner_language,
                        user_bid=user_bid,
                        shifu_bid=shifu_bid,
                        outline_bid=outline_bid,
                        user_input=user_input,
                        listen=listen,
                        preview_mode=preview_mode,
                        shifu_model=(
                            type(lesson_version.course)
                            if lesson_version is not None
                            else _models(preview_mode)[1]
                        ),
                        **(
                            {}
                            if lesson_version is None
                            else {"lesson_version": lesson_version}
                        ),
                        heartbeat_interval=heartbeat_interval,
                        rewind=rewind,
                        on_turn_opened=bind_turn_usage,
                        tracing=tracing,
                        **debug_options,
                    )
                )
                if outcome is not None and outcome.discarded:
                    # A reset or rewind replaced this turn while it ran, so its save was
                    # refused. Nothing it showed may be kept, and it must not be carried on:
                    # a "continue" from here would start the learner's new attempt from the
                    # old stream. However the turn itself ended, it ends here, quietly.
                    try:
                        raise_error("server.common.unknownError")
                    except AppError as error:
                        raise DiscardedTurnError(error.message, error.code) from None
                if outcome is not None and outcome.reason is None:
                    # The engine can return a bare ErrorEvent after a provider failure. It has
                    # already saved the usable session, but the legacy stream has no error DTO;
                    # raising here lets the outer SSE layer show the failure instead of
                    # silently ending a lesson that remains in progress.
                    if outcome.error_code == "input_budget_exceeded":
                        raise_error("server.learn.agentInputBudgetExceeded")
                    # Otherwise the model failed (a provider error, timeout or exhausted
                    # recovery). The learner sees the friendly "unavailable" message for the
                    # unknown error below; the outage must still reach the alerting stream.
                    # The engine names the failure by its code and exception class, both free
                    # of provider details.
                    app.logger.error(
                        "lesson turn failed in the engine: shifu_bid=%s outline_bid=%s "
                        "preview=%s engine_code=%s engine_error=%s",
                        shifu_bid,
                        outline_bid,
                        preview_mode,
                        outcome.error_code,
                        outcome.error_type,
                    )
                    raise_error("server.common.unknownError")
                # A turn that ran out of content with the lesson not over is followed by the next,
                # as the host's own "continue": the learner's input and the rewind belonged to the
                # first turn only. The browser is not asked to do this. It never sees the boundary
                # -- a turn's end that is not the lesson's is kept off the stream -- so a lesson
                # left there stayed "in progress" until the learner came back to it, and only then
                # went on. A turn that ended the same way having said nothing is not followed: the
                # model has nothing to add and did not say so, and asking again would only loop.
                if outcome is None or outcome.reason != "end" or not outcome.taught:
                    break
                if debug_store is not None:
                    # The request seed predates the writes this turn just saved.
                    # Automatic continuation should resume from the saved memory.
                    preview_variables = None
                user_input, rewind = None, None
        except RewindUnavailableError:
            # The session the rows point back into is gone (unreadable, or never stored).
            raise_error("server.learn.agentRewindUnavailable")

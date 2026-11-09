"""Answer one follow-up question beside the lesson.

A follow-up runs under its own semaphore and never advances the lesson. It needs
the lesson lookup, the learner's progress record, the course prompt and a
Langfuse trace, which this module supplies before calling ``handle_input_ask``.
"""

from __future__ import annotations

import time
from contextlib import closing
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from flaskr.api.langfuse import (
    LangfuseObservationHandle,
    LangfuseTraceHandle,
    MockClient,
    create_advancement_trace_id,
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
    get_request_id,
    normalize_langfuse_input_value,
    normalize_langfuse_output_value,
)
from flaskr.dao import db
from flaskr.dao.uow import require_transaction_owner, unit_of_work
from flaskr.service.common import raise_error
from flaskr.service.common.models import raise_param_error
from flaskr.service.learn.agent.lesson_record import (
    claim_for_writing,
    find_active_progress_record,
)
from flaskr.service.learn.agent.lesson_source import (
    resolve_lesson_source,
    resolve_requested_lesson_source,
)
from flaskr.service.learn.agent.session_store import (
    StoredSessionUnusable,
    active_session_id,
    load_agent_session,
    load_lesson_attempt_source,
    stage_lesson_attempt_source,
)
from flaskr.service.learn.ask.context import (
    claim_follow_up_anchor,
    resolve_course_system_prompt,
)
from flaskr.service.learn.ask.handler import (
    handle_input_ask,
    require_follow_up_enabled,
    resolve_text_follow_up_info,
)
from flaskr.service.learn.ask.memory_writer import (
    FollowUpMemoryPatch,
    stage_follow_up_memory,
)
from flaskr.service.learn.const import INPUT_TYPE_ASK
from flaskr.service.learn.elements.queries import _load_latest_active_element_row
from flaskr.service.learn.exceptions import PaidError
from flaskr.service.learn.langfuse_naming import (
    build_langfuse_span_name,
    build_langfuse_trace_name,
)
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.learn.preview_permissions import require_shifu_preview_permission
from flaskr.service.memory.api import load_memory
from flaskr.service.order.consts import (
    LEARN_STATUS_NOT_STARTED,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import UNIT_TYPE_VALUE_NORMAL
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_struct_manager import (
    ShifuOutlineItemDto,
    get_outline_item_dto,
    get_shifu_struct,
)
from flaskr.service.shifu.struct_utils import find_node_with_parents
from flaskr.service.user.repository import UserAggregate, load_user_aggregate
from flaskr.util import generate_id
from sqlalchemy import or_

if TYPE_CHECKING:
    import threading
    from collections.abc import Callable, Generator

    from flask import Flask
    from flaskr.service.learn.agent.session_store import LessonAttemptSource
    from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO
    from flaskr.service.learn.utils_v2 import FollowUpInfo
    from flaskr.service.shifu.shifu_history_manager import HistoryItem


class FollowUpCancelledError(Exception):
    """The learner closed the stream; nothing more is written for this question."""


_PENDING_ANCHOR_WAIT_SECONDS = 15
_PENDING_ANCHOR_POLL_SECONDS = 0.2


@dataclass(frozen=True)
class _FollowUpAnchor:
    """The requested teaching anchor and the attempt that owns it."""

    element_bid: str
    block_bid: str
    position: int | None
    progress_bid: str
    pending: bool


@dataclass
class AskContext:
    """The lesson state ``handle_input_ask`` reads.

    Attribute names match what ``handle_input_ask`` reads from the context it is given.
    """

    app: Flask
    _struct: HistoryItem
    _shifu_info: DraftShifu | PublishedShifu
    _source: LessonAttemptSource
    _listen: bool
    _learning_mode: str
    _stop_event: threading.Event | None
    _legacy_script: str | None = None
    _langfuse_output_chunks: list[str] = field(default_factory=list)
    _system_prompts: dict[str, str | None] = field(default_factory=dict)

    @property
    def _source_preview_mode(self) -> bool:
        return self._source.preview_mode

    @property
    def _outline_model(self) -> type[DraftOutlineItem | PublishedOutlineItem]:
        return DraftOutlineItem if self._source_preview_mode else PublishedOutlineItem

    @property
    def _shifu_model(self) -> type[DraftShifu | PublishedShifu]:
        return DraftShifu if self._source_preview_mode else PublishedShifu

    def outline_path(self, outline_item_bid: str) -> list[HistoryItem]:
        """Return the course path down to a lesson, or refuse an unknown lesson."""
        path = find_node_with_parents(self._struct, outline_item_bid)
        if not path:
            raise_error("server.shifu.lessonNotFoundInCourse")
        return path

    def get_system_prompt(self, outline_item_bid: str) -> str | None:
        """Return the nearest inherited Course Prompt for a lesson."""
        if outline_item_bid not in self._system_prompts:
            self._system_prompts[outline_item_bid] = resolve_course_system_prompt(
                self.app,
                shifu_bid=self._shifu_info.shifu_bid,
                outline_item_bid=outline_item_bid,
                preview_mode=self._source_preview_mode,
                allow_retired_draft=True,
                outline_path=self.outline_path(outline_item_bid),
                outline_model=self._outline_model,
                shifu_model=self._shifu_model,
            )
        return self._system_prompts[outline_item_bid]

    def _get_outline_row_id(self, outline_item_bid: str) -> int | None:
        node = find_node_with_parents(self._struct, outline_item_bid)
        if node and getattr(node[-1], "id", None):
            return int(node[-1].id)
        return None

    def append_langfuse_output(self, value: object) -> None:
        """Buffer answer text for the trace finalized when the question ends."""
        text = normalize_langfuse_output_value(value)
        if text:
            self._langfuse_output_chunks.append(text)


def follow_up_events(
    app: Flask,
    *,
    user_bid: str,
    outline_bid: str,
    user_input: str | dict | list | None,
    reload_generated_block_bid: str | None,
    reload_element_bid: str | None,
    listen: bool,
    learning_mode: str,
    preview_mode: bool,
    stop_event: threading.Event | None,
    shifu_bid: str | None = None,
    bind_block: Callable[[LearnGeneratedBlock], None] | None = None,
    stage_elements: Callable[[], None] | None = None,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Stream the answer to one follow-up question and save its history rows.

    Writes to lesson history and memory commit together when the stream finishes.
    """
    require_transaction_owner("streaming a follow-up")
    user_info = load_user_aggregate(user_bid)
    if not user_info:
        raise_error("USER.USER_NOT_FOUND")
    if not outline_bid:
        raise_error("server.shifu.lessonNotFoundInCourse")
    if shifu_bid is None:
        shifu_bid = get_outline_item_dto(app, outline_bid, preview_mode).shifu_bid
    requested = resolve_requested_lesson_source(
        shifu_bid=shifu_bid, outline_bid=outline_bid, preview_mode=preview_mode
    )
    outline_item_info = ShifuOutlineItemDto(
        bid=outline_bid,
        shifu_bid=shifu_bid,
        position=requested.outline.position,
        title=requested.outline.title,
        type=requested.outline.type,
        children=[],
    )
    tracing = _FollowUpTrace.admit(
        app, user_info, outline_item_info, user_input, preview_mode
    )
    context = None
    try:
        if not preview_mode:
            _require_purchase(user_bid, requested.course, requested.outline)
        resolved = resolve_lesson_source(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            preview_mode=preview_mode,
        )
        struct = resolved.structure or get_shifu_struct(
            app, shifu_bid, resolved.source.preview_mode
        )
        normalized_mode = str(learning_mode or "").strip().lower()
        if normalized_mode not in {"read", "listen", "classroom"}:
            normalized_mode = "listen" if listen else "read"
        legacy_script = None
        if resolved.source.outline_row_id is None:
            try:
                stored = load_agent_session(app, user_bid, outline_bid)
            except StoredSessionUnusable:
                stored = None
            # Unknown provenance does not authorize keys added in a later publication.
            legacy_script = stored.script.script if stored is not None else ""
        context = AskContext(
            app=app,
            _struct=struct,
            _shifu_info=resolved.course,
            _source=resolved.source,
            _listen=listen,
            _learning_mode=normalized_mode,
            _stop_event=stop_event,
            _legacy_script=legacy_script,
        )
        scope = {
            "user_bid": user_info.user_id,
            "shifu_bid": shifu_bid,
            "outline_bid": outline_item_info.bid,
        }
        anchor = _resolve_anchor(
            reload_generated_block_bid,
            reload_element_bid,
            **scope,
        )
        if anchor.pending:
            anchor = _wait_for_pending_anchor(
                app,
                context,
                anchor,
                **scope,
                expected_progress_bid=resolved.progress_record_bid,
            )
        follow_up_info = resolve_text_follow_up_info(
            app, context, outline_item_info, is_preview=preview_mode
        )
        require_follow_up_enabled(follow_up_info)
        attend = _current_attend(
            app,
            context,
            user_info,
            outline_bid=outline_item_info.bid,
            anchor_progress_bid=anchor.progress_bid,
            expected_progress_bid=resolved.progress_record_bid,
        )
        tracing.args["metadata"]["progress_record_bid"] = attend.progress_record_bid
        tracing.start(
            session_id=_trace_session_id(
                app,
                user_info.user_id,
                outline_item_info.bid,
            )
        )
        yield from _answer(
            app,
            context,
            user_info=user_info,
            outline_item_info=outline_item_info,
            progress_record_bid=attend.progress_record_bid,
            follow_up_info=follow_up_info,
            user_input=user_input,
            last_position=(
                attend.block_position if anchor.position is None else anchor.position
            ),
            anchor_element_bid=anchor.element_bid,
            anchor_block_bid=anchor.block_bid,
            trace_args=tracing.args,
            trace=tracing.trace,
            root_span=tracing.root_span,
            preview_mode=preview_mode,
            bind_block=bind_block,
            stage_elements=stage_elements,
        )
    except (FollowUpCancelledError, GeneratorExit):
        # The learner walked away; the trace is left as it stands.
        raise
    except Exception as error:
        tracing.finalize(context, error=error)
        raise
    tracing.finalize(context)


@dataclass
class _FollowUpTrace:
    """One Langfuse trace per follow-up question, grouped by the lesson's session.

    Like a lesson advancement, a question gets its own trace id when admitted and
    its root only once the learner's progress is resolved. Its Langfuse Session is
    the native id of the lesson's live 2.0 session, the same one the lesson's turns
    use; a question asked before that session exists has none. Until the root
    exists, and if the SDK fails, no-op handles carry the same trace id, so usage
    records stay correlated and telemetry failures never interrupt the answer.
    """

    app: Flask
    args: dict
    trace_id: str
    trace: object
    root_span: object
    started: bool = False
    finalized: bool = False

    @classmethod
    def admit(
        cls,
        app: Flask,
        user_info: UserAggregate,
        outline_item_info: ShifuOutlineItemDto,
        user_input: object,
        preview_mode: bool,
    ) -> _FollowUpTrace:
        chapter_title = outline_item_info.title
        trace_scene = "lesson_preview_runtime" if preview_mode else "lesson_runtime"
        trace_id = create_advancement_trace_id()
        args: dict = {
            "user_id": user_info.user_id,
            "name": build_langfuse_trace_name(chapter_title, trace_scene),
            "metadata": {
                "scene": trace_scene,
                "chapter_title": chapter_title,
                "outline_item_bid": outline_item_info.bid,
                "shifu_bid": outline_item_info.shifu_bid,
                "preview_mode": int(bool(preview_mode)),
                "request_id": get_request_id(),
            },
            "input": normalize_langfuse_input_value(user_input),
            "input_type": INPUT_TYPE_ASK,
        }
        return cls(
            app=app,
            args=args,
            trace_id=trace_id,
            trace=LangfuseTraceHandle(MockClient(), trace_id),
            root_span=LangfuseObservationHandle(MockClient(), trace_id),
        )

    def start(self, *, session_id: str | None = None) -> None:
        """Create the root once; a session id groups it with the lesson's other traces."""
        if self.started:
            return
        self.started = True
        if session_id:
            self.args["session_id"] = session_id
        metadata = self.args["metadata"]
        try:
            self.trace, self.root_span = create_trace_with_root_span(
                client=get_langfuse_client(),
                trace_payload={"id": self.trace_id, **self.args},
                root_span_payload={
                    "name": build_langfuse_span_name(
                        metadata["chapter_title"], metadata["scene"], "root"
                    )
                },
            )
        except Exception as telemetry_error:
            self.app.logger.warning(
                "Langfuse follow-up trace creation failed (%s)",
                type(telemetry_error).__name__,
            )

    def finalize(
        self, context: AskContext | None, *, error: Exception | None = None
    ) -> None:
        """End the root once; a failure before the session is known still leaves a trace."""
        if self.finalized:
            return
        self.finalized = True
        self.start()
        output = "".join(context._langfuse_output_chunks) or None if context else None
        root_payload: dict = {"input": self.args.get("input"), "output": output}
        if error is not None:
            root_payload.update(
                level="ERROR",
                status_message=type(error).__name__,
                metadata={"runtime_outcome": "error"},
            )
        try:
            finalize_langfuse_trace(
                trace=self.trace,
                root_span=self.root_span,
                trace_payload={**self.args, "output": output},
                root_span_payload=root_payload,
            )
        except Exception as telemetry_error:
            self.app.logger.warning(
                "Langfuse follow-up trace finalization failed (%s)",
                type(telemetry_error).__name__,
            )


def _trace_session_id(app: Flask, user_bid: str, outline_bid: str) -> str | None:
    """Return the lesson's native session id for tracing; a failed lookup only loses grouping."""
    try:
        return active_session_id(user_bid, outline_bid)
    except Exception as session_error:
        app.logger.warning(
            "Follow-up Langfuse session lookup failed (%s)",
            type(session_error).__name__,
        )
        return None


def _resolve_anchor(
    reload_generated_block_bid: str | None,
    reload_element_bid: str | None,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
) -> _FollowUpAnchor:
    """Bind a stored anchor to its attempt; allow a not-yet-committed anchor."""
    anchor_element_bid = reload_element_bid or ""
    anchor_progress_bid = ""
    anchor_position = None
    pending = False
    if anchor_element_bid:
        anchor = _load_latest_active_element_row(anchor_element_bid)
        pending = anchor is None
        if anchor is not None:
            if (
                anchor.user_bid != user_bid
                or anchor.shifu_bid != shifu_bid
                or anchor.outline_item_bid != outline_bid
                or not anchor.progress_record_bid
            ):
                raise_param_error("anchor_element_bid")
            reload_generated_block_bid = anchor.generated_block_bid
            anchor_progress_bid = anchor.progress_record_bid
            anchor_position = int(anchor.element_index or 0)
        elif (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.event_type == "element",
                or_(
                    LearnGeneratedElement.element_bid == anchor_element_bid,
                    LearnGeneratedElement.target_element_bid == anchor_element_bid,
                ),
            ).first()
            is not None
        ):
            raise_param_error("anchor_element_bid")
    if reload_generated_block_bid:
        block = LearnGeneratedBlock.query.filter_by(
            generated_block_bid=reload_generated_block_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
        ).first()
        if block is not None:
            if block.deleted or block.status != 1 or not block.progress_record_bid:
                raise_param_error("anchor_element_bid")
            if anchor_progress_bid and block.progress_record_bid != anchor_progress_bid:
                raise_param_error("anchor_element_bid")
            return _FollowUpAnchor(
                anchor_element_bid,
                block.generated_block_bid,
                block.position,
                block.progress_record_bid,
                pending,
            )
        # AskBlock sends the selected element ID in both reload fields.
        if pending and reload_generated_block_bid != anchor_element_bid:
            raise_param_error("anchor_element_bid")
    return _FollowUpAnchor(
        anchor_element_bid, "", anchor_position, anchor_progress_bid, pending
    )


def _wait_for_pending_anchor(
    app: Flask,
    context: AskContext,
    anchor: _FollowUpAnchor,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    expected_progress_bid: str | None,
) -> _FollowUpAnchor:
    """Wait for the streamed teaching element in the attempt already selected."""
    if not expected_progress_bid or (
        anchor.progress_bid and anchor.progress_bid != expected_progress_bid
    ):
        raise_param_error("anchor_element_bid")
    require_transaction_owner("waiting for a follow-up anchor")
    deadline = time.monotonic() + _PENDING_ANCHOR_WAIT_SECONDS
    while True:
        _stop_if_requested(app, context)
        # End the read snapshot between polls so another worker's teaching
        # commit can become visible, before staging any follow-up writes.
        with unit_of_work(discard=True):
            current = _resolve_anchor(
                anchor.block_bid,
                anchor.element_bid,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
            )
            if (anchor.block_bid and current.block_bid != anchor.block_bid) or (
                current.progress_bid and current.progress_bid != expected_progress_bid
            ):
                raise_param_error("anchor_element_bid")
            if not current.pending:
                if not current.block_bid:
                    raise_param_error("anchor_element_bid")
                # An unstarted placeholder can get its source while we wait.
                # The settled anchor must still use the version admitted above.
                pinned = load_lesson_attempt_source(
                    user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
                )
                if pinned is not None and pinned != context._source:
                    raise_param_error("anchor_element_bid")
        if not current.pending:
            if context._source.preview_mode:
                require_shifu_preview_permission(app, user_bid, shifu_bid)
            return current
        delay = min(_PENDING_ANCHOR_POLL_SECONDS, deadline - time.monotonic())
        if delay <= 0:
            raise_param_error("anchor_element_bid")
        if context._stop_event is not None:
            context._stop_event.wait(delay)
        else:
            time.sleep(delay)


def _require_purchase(
    user_bid: str,
    shifu_info: DraftShifu | PublishedShifu,
    outline_info: DraftOutlineItem | PublishedOutlineItem,
) -> None:
    if (
        outline_info.type != UNIT_TYPE_VALUE_NORMAL
        or not shifu_info.price
        or shifu_info.price <= 0
    ):
        return
    if (
        Order.query.filter(
            Order.user_bid == user_bid,
            Order.shifu_bid == shifu_info.shifu_bid,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.deleted == 0,
        ).first()
        is None
    ):
        raise PaidError


def _current_attend(
    app: Flask,
    context: AskContext,
    user_info: UserAggregate,
    *,
    outline_bid: str,
    anchor_progress_bid: str,
    expected_progress_bid: str | None,
) -> LearnProgressRecord:
    """Use the same active attempt as teaching or open an unstarted placeholder."""
    shifu_bid = context._shifu_info.shifu_bid
    user_bid = user_info.user_id
    record = find_active_progress_record(
        user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
    )
    if expected_progress_bid and (
        record is None or record.progress_record_bid != expected_progress_bid
    ):
        raise FollowUpCancelledError
    if anchor_progress_bid and (
        record is None or record.progress_record_bid != anchor_progress_bid
    ):
        raise_param_error("anchor_element_bid")
    if record is not None:
        return record

    with unit_of_work():
        for item in context.outline_path(outline_bid):
            if item.type != "outline":
                continue
            record = find_active_progress_record(
                user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=item.bid
            )
            if record is None:
                record = LearnProgressRecord(
                    outline_item_bid=item.bid,
                    shifu_bid=shifu_bid,
                    user_bid=user_bid,
                    status=LEARN_STATUS_NOT_STARTED,
                    progress_record_bid=generate_id(app),
                    block_position=0,
                )
                db.session.add(record)
        db.session.flush()
    return record


def _answer(
    app: Flask,
    context: AskContext,
    *,
    user_info: UserAggregate,
    outline_item_info: ShifuOutlineItemDto,
    progress_record_bid: str,
    follow_up_info: FollowUpInfo,
    user_input: str | dict | list | None,
    last_position: int,
    anchor_element_bid: str,
    anchor_block_bid: str,
    trace_args: dict,
    trace: object,
    root_span: object,
    preview_mode: bool,
    bind_block: Callable[[LearnGeneratedBlock], None] | None,
    stage_elements: Callable[[], None] | None,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    question = user_input
    if isinstance(question, dict):
        question = question.get("input", "")
    if isinstance(question, list):
        question = ",".join(question)
    question = question or ""
    _stop_if_requested(app, context)
    app.logger.info("Ask input normalized: input_chars=%s", len(question))

    runtime_profiles = load_memory(
        app,
        user_info.user_id,
        outline_item_info.shifu_bid,
        reference_text=context.get_system_prompt(outline_item_info.bid) or "",
        include_course_variables=True,
    ).as_variables()
    memory_patch = FollowUpMemoryPatch()
    pending_blocks: list[LearnGeneratedBlock] = []

    def defer_block(block: LearnGeneratedBlock) -> None:
        pending_blocks.append(block)
        if bind_block is not None:
            bind_block(block)

    events = handle_input_ask(
        app,
        context,
        user_info,
        progress_record_bid,
        question,
        outline_item_info,
        trace_args,
        trace,
        preview_mode,
        last_position,
        anchor_element_bid=anchor_element_bid,
        parent_observation=root_span,
        runtime_profiles=runtime_profiles,
        memory_patch=memory_patch,
        follow_up_info=follow_up_info,
        defer_block=defer_block,
    )
    with closing(events):
        for event in events:
            _stop_if_requested(app, context)
            with unit_of_work(discard=True):
                if context._source.preview_mode and event.type != GeneratedType.ASK:
                    require_shifu_preview_permission(
                        app, user_info.user_id, outline_item_info.shifu_bid
                    )
            yield event

    _stop_if_requested(app, context)
    scope = {
        "user_bid": user_info.user_id,
        "shifu_bid": outline_item_info.shifu_bid,
        "outline_bid": outline_item_info.bid,
    }
    with unit_of_work():
        if claim_for_writing(**scope, progress_record_bid=progress_record_bid) is None:
            raise FollowUpCancelledError
        if anchor_element_bid or anchor_block_bid:
            _require_writable_anchor(
                anchor_element_bid,
                anchor_block_bid,
                **scope,
                progress_record_bid=progress_record_bid,
            )
        if context._source.preview_mode:
            require_shifu_preview_permission(
                app, user_info.user_id, outline_item_info.shifu_bid
            )
        if not stage_lesson_attempt_source(**scope, source=context._source):
            raise FollowUpCancelledError
        db.session.add_all(pending_blocks)
        if stage_elements is not None:
            stage_elements()
        if memory_patch.variables:
            stage_follow_up_memory(
                app,
                **scope,
                progress_record_bid=progress_record_bid,
                patch=memory_patch,
            )
        db.session.flush()


def _require_writable_anchor(
    anchor_element_bid: str,
    anchor_block_bid: str,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str,
) -> None:
    if anchor_element_bid:
        # Asking can start while teaching is still streaming. The element must
        # be durable by the time we save, or there is nothing to replay the
        # accepted follow-up under if that teaching turn never lands.
        if (
            claim_follow_up_anchor(
                anchor_element_bid,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                progress_record_bid=progress_record_bid,
            )
            is None
        ):
            previous_anchor = (
                LearnGeneratedElement.query.filter(
                    LearnGeneratedElement.user_bid == user_bid,
                    LearnGeneratedElement.shifu_bid == shifu_bid,
                    LearnGeneratedElement.outline_item_bid == outline_bid,
                    LearnGeneratedElement.progress_record_bid == progress_record_bid,
                    or_(
                        LearnGeneratedElement.element_bid == anchor_element_bid,
                        LearnGeneratedElement.target_element_bid == anchor_element_bid,
                    ),
                )
                .with_for_update()
                .first()
            )
            if previous_anchor is not None:
                raise FollowUpCancelledError
            raise_param_error("anchor_element_bid")
        return
    block = (
        LearnGeneratedBlock.query.filter_by(
            generated_block_bid=anchor_block_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            progress_record_bid=progress_record_bid,
            status=1,
            deleted=0,
        )
        .with_for_update()
        .first()
        if anchor_block_bid
        else None
    )
    if block is None:
        raise FollowUpCancelledError


def _stop_if_requested(app: Flask, context: AskContext) -> None:
    if context._stop_event is not None and context._stop_event.is_set():
        app.logger.info("follow-up cancelled by stop_event")
        raise FollowUpCancelledError
